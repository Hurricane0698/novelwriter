"""Authentication API endpoints."""

import base64
import hashlib
import json
import logging
import secrets
from typing import Any
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings, resolve_context_chapters
from app.database import get_db
from app.models import Novel, User
from app.core.auth import (
    AUTH_PROVIDER_GITHUB,
    DEFAULT_OAUTH_STATE_TTL_SECONDS,
    activate_hosted_user_for_invite_code,
    authenticate_hosted_user_by_nickname_password,
    clear_auth_cookie,
    create_oauth_state_token,
    decode_oauth_state_token,
    get_current_user_optional,
    get_current_user_or_default,
    issue_user_session,
    request_is_secure,
    normalize_invite_code,
    reconcile_abandoned_quota_reservations,
    resolve_or_provision_hosted_user_for_identity,
    require_admin,
)
from app.core.events import (
    PUBLIC_CLIENT_EVENT_NAMES,
    build_hosted_beta_funnel_report,
    normalize_event_meta,
    public_event_forbids_novel_id,
    public_event_requires_novel_id,
    record_event,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=128)


class InviteActivationRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=100)
    nickname: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=8, max_length=128)
    anonymous_id: str | None = Field(default=None, max_length=64)
    attribution: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


REQUIRED_FEEDBACK_KEYS = {"overall_rating", "issues"}


class FeedbackRequest(BaseModel):
    answers: dict


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthOptionsResponse(BaseModel):
    deploy_mode: str
    invite_login_enabled: bool
    github_login_enabled: bool


class PublicAnalyticsEventRequest(BaseModel):
    event: str = Field(min_length=1, max_length=64)
    anonymous_id: str | None = Field(default=None, max_length=64)
    novel_id: int | None = Field(default=None, ge=1)
    meta: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class UserResponse(BaseModel):
    id: int
    username: str
    nickname: str | None = None
    role: str
    is_active: bool
    generation_quota: int = 0
    feedback_submitted: bool = False
    preferences: dict | None = None

    model_config = {"from_attributes": True}


class QuotaResponse(BaseModel):
    generation_quota: int
    feedback_submitted: bool


DEFAULT_POST_LOGIN_REDIRECT = "/library"
GITHUB_OAUTH_STATE_COOKIE_NAME = "novwr_github_oauth_state"
GITHUB_OAUTH_PKCE_COOKIE_NAME = "novwr_github_oauth_pkce"
GITHUB_OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_OAUTH_USER_URL = "https://api.github.com/user"
GITHUB_OAUTH_SCOPE = "read:user"
GITHUB_OAUTH_CALLBACK_PATH = "/api/auth/github/callback"


def _build_signup_event_meta(
    *,
    provider: str,
    anonymous_id: str | None = None,
    attribution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = normalize_event_meta(attribution)
    meta["admission_provider"] = provider
    normalized_anonymous_id = (anonymous_id or "").strip()[:64]
    if normalized_anonymous_id:
        meta["anonymous_id"] = normalized_anonymous_id
    return meta


def _validate_public_event_scope(
    *,
    db: Session,
    current_user: User | None,
    event_name: str,
    novel_id: int | None,
) -> None:
    if public_event_requires_novel_id(event_name):
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "analytics_project_event_auth_required",
                    "message": "Authentication is required for project-scoped analytics events",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        if novel_id is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "analytics_novel_id_required",
                    "message": "novel_id is required for this analytics event",
                },
            )
        owned_novel = (
            db.query(Novel.id)
            .filter(Novel.id == novel_id, Novel.owner_id == current_user.id)
            .first()
        )
        if owned_novel is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "analytics_novel_not_found",
                    "message": "Novel not found",
                },
            )
        return

    if public_event_forbids_novel_id(event_name) and novel_id is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "analytics_novel_id_forbidden",
                "message": "novel_id is not allowed for this analytics event",
            },
        )


@dataclass(frozen=True)
class GitHubOAuthIdentity:
    provider_user_id: str
    login: str
    display_name: str
    email: str | None = None


def resolve_safe_post_login_redirect(value: str | None) -> str:
    candidate = (value or "").strip()
    if not candidate or "\\" in candidate or "\x00" in candidate:
        return DEFAULT_POST_LOGIN_REDIRECT

    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return DEFAULT_POST_LOGIN_REDIRECT
    if not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return DEFAULT_POST_LOGIN_REDIRECT
    if parsed.path.startswith("/login") or parsed.path.startswith("/api"):
        return DEFAULT_POST_LOGIN_REDIRECT
    return candidate


def _github_oauth_is_configured() -> bool:
    settings = get_settings()
    return bool(settings.github_oauth_client_id.strip() and settings.github_oauth_client_secret.strip())


def _hosted_github_login_is_enabled() -> bool:
    settings = get_settings()
    return (
        settings.deploy_mode == "hosted"
        and settings.hosted_github_login_enabled
        and _github_oauth_is_configured()
    )


def _set_github_oauth_cookie(
    response: Response,
    request: Request,
    *,
    key: str,
    value: str,
) -> None:
    response.set_cookie(
        key=key,
        value=value,
        max_age=DEFAULT_OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=request_is_secure(request),
        samesite="lax",
        path=GITHUB_OAUTH_CALLBACK_PATH,
    )


def _clear_github_oauth_cookies(response: Response) -> None:
    response.delete_cookie(key=GITHUB_OAUTH_STATE_COOKIE_NAME, path=GITHUB_OAUTH_CALLBACK_PATH)
    response.delete_cookie(key=GITHUB_OAUTH_PKCE_COOKIE_NAME, path=GITHUB_OAUTH_CALLBACK_PATH)


def _build_login_redirect_url(*, oauth_error: str | None = None, redirect_to: str | None = None) -> str:
    params: dict[str, str] = {}
    if oauth_error:
        params["oauth_error"] = oauth_error
    safe_redirect = resolve_safe_post_login_redirect(redirect_to)
    if safe_redirect != DEFAULT_POST_LOGIN_REDIRECT:
        params["redirect_to"] = safe_redirect
    if not params:
        return "/login"
    return f"/login?{urlencode(params)}"


def _redirect_to_login_with_error(*, oauth_error: str, redirect_to: str | None = None) -> RedirectResponse:
    response = RedirectResponse(
        url=_build_login_redirect_url(oauth_error=oauth_error, redirect_to=redirect_to),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    _clear_github_oauth_cookies(response)
    return response


def _build_github_callback_uri(request: Request) -> str:
    settings = get_settings()
    configured_redirect = settings.github_oauth_redirect_uri.strip()
    if configured_redirect:
        return configured_redirect
    return str(request.url_for("github_oauth_callback"))


def _generate_github_pkce_verifier() -> str:
    # RFC 7636 allows 43-128 characters from the unreserved URL charset.
    return secrets.token_urlsafe(64)


def _build_github_pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _build_github_authorize_url(
    request: Request,
    *,
    redirect_to: str,
) -> tuple[str, str, str]:
    settings = get_settings()
    nonce = secrets.token_urlsafe(32)
    state_token = create_oauth_state_token(
        provider=AUTH_PROVIDER_GITHUB,
        redirect_to=redirect_to,
        nonce=nonce,
    )
    code_verifier = _generate_github_pkce_verifier()
    params = urlencode(
        {
            "client_id": settings.github_oauth_client_id.strip(),
            "redirect_uri": _build_github_callback_uri(request),
            "scope": GITHUB_OAUTH_SCOPE,
            "state": state_token,
            "allow_signup": "true",
            "code_challenge": _build_github_pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{GITHUB_OAUTH_AUTHORIZE_URL}?{params}", state_token, code_verifier


def _github_json_request(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "NovWr",
    }
    if headers:
        request_headers.update(headers)

    body = None
    if data is not None:
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = urlencode(data).encode("utf-8")

    req = UrlRequest(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub OAuth HTTP {exc.code}: {response_body[:200]}") from exc
    except URLError as exc:
        raise RuntimeError("GitHub OAuth request failed") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("GitHub OAuth response was not a JSON object")
    return payload


def exchange_github_code_for_identity(
    *,
    request: Request,
    code: str,
    code_verifier: str,
) -> GitHubOAuthIdentity:
    settings = get_settings()
    token_payload = _github_json_request(
        GITHUB_OAUTH_TOKEN_URL,
        method="POST",
        data={
            "client_id": settings.github_oauth_client_id.strip(),
            "client_secret": settings.github_oauth_client_secret.strip(),
            "code": code,
            "redirect_uri": _build_github_callback_uri(request),
            "code_verifier": code_verifier,
        },
    )
    oauth_error = token_payload.get("error")
    if isinstance(oauth_error, str) and oauth_error:
        raise RuntimeError(f"GitHub OAuth token exchange failed: {oauth_error}")

    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("GitHub OAuth token response did not include an access token")

    profile_payload = _github_json_request(
        GITHUB_OAUTH_USER_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    provider_user_id = profile_payload.get("id")
    login = str(profile_payload.get("login") or "").strip()
    email_value = profile_payload.get("email")
    email = str(email_value).strip() if isinstance(email_value, str) else None
    display_name = str(profile_payload.get("name") or login).strip() or login

    if provider_user_id in (None, "") or not login:
        raise RuntimeError("GitHub OAuth profile response was missing a stable user identity")

    return GitHubOAuthIdentity(
        provider_user_id=str(provider_user_id),
        login=login,
        display_name=display_name,
        email=email or None,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    # Pre-launch hosted auth is admission-gated at the login surface; selfhost uses the default user flow.
    hosted_message = "Registration disabled in hosted mode; use invite activation + nickname/password login"
    if settings.hosted_github_login_enabled:
        hosted_message = "Registration disabled in hosted mode; use invite activation, nickname/password login, or GitHub login"
    raise HTTPException(
        status_code=405,
        detail=(
            hosted_message
            if settings.deploy_mode == "hosted"
            else "Registration disabled in selfhost mode"
        ),
    )


@router.get("/options", response_model=AuthOptionsResponse)
def auth_options():
    settings = get_settings()
    return AuthOptionsResponse(
        deploy_mode=settings.deploy_mode,
        invite_login_enabled=settings.deploy_mode == "hosted" and settings.hosted_invite_login_enabled,
        github_login_enabled=_hosted_github_login_is_enabled(),
    )


@router.post("/events", status_code=202)
def record_public_event(
    body: PublicAnalyticsEventRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    settings = get_settings()
    if settings.deploy_mode != "hosted":
        raise HTTPException(
            status_code=405,
            detail={"code": "analytics_events_disabled", "message": "Hosted analytics events are unavailable in selfhost mode"},
        )
    if body.event not in PUBLIC_CLIENT_EVENT_NAMES:
        raise HTTPException(
            status_code=422,
            detail={"code": "analytics_event_unsupported", "message": "Unsupported analytics event"},
        )

    _validate_public_event_scope(
        db=db,
        current_user=current_user,
        event_name=body.event,
        novel_id=body.novel_id,
    )

    meta = normalize_event_meta(body.meta)
    anonymous_id = (body.anonymous_id or "").strip() or None
    if current_user is None and not anonymous_id and not meta.get("anonymous_id"):
        raise HTTPException(
            status_code=422,
            detail={"code": "analytics_anonymous_id_required", "message": "anonymous_id is required for unauthenticated analytics events"},
        )

    record_event(
        db,
        current_user.id if current_user is not None else None,
        body.event,
        novel_id=body.novel_id,
        meta=meta,
        anonymous_id=anonymous_id,
    )
    return {"ok": True}


@router.post("/invite", response_model=TokenResponse, status_code=201)
def invite_activate(body: InviteActivationRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Activate a hosted account via invite code on first use."""
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        raise HTTPException(
            status_code=405,
            detail={"code": "invite_login_disabled", "message": "Invite activation disabled in selfhost mode"},
        )

    if not settings.hosted_invite_login_enabled:
        raise HTTPException(
            status_code=503,
            detail={"code": "invite_login_unconfigured", "message": "Invite activation not configured"},
        )

    invite_attribution = dict(body.attribution)
    try:
        normalized_invite_code = normalize_invite_code(body.invite_code)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail={"code": "invite_code_invalid", "message": "Invalid invite code"},
        ) from None

    invite_entry = settings.hosted_invite_code_lookup.get(normalized_invite_code)
    if invite_entry is not None:
        if invite_entry.channel and not invite_attribution.get("channel"):
            invite_attribution["channel"] = invite_entry.channel
        if invite_entry.invite_batch and not invite_attribution.get("invite_batch"):
            invite_attribution["invite_batch"] = invite_entry.invite_batch

    user = activate_hosted_user_for_invite_code(
        db,
        invite_code=normalized_invite_code,
        nickname=body.nickname,
        password=body.password,
        signup_meta=_build_signup_event_meta(
            provider="invite",
            anonymous_id=body.anonymous_id,
            attribution=invite_attribution,
        ),
    )
    token = issue_user_session(response=response, request=request, user=user)
    return TokenResponse(access_token=token)


@router.get("/github/start", include_in_schema=False)
def github_oauth_start(request: Request, redirect_to: str | None = None):
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        raise HTTPException(status_code=405, detail="GitHub OAuth disabled in selfhost mode")

    safe_redirect = resolve_safe_post_login_redirect(redirect_to)
    if settings.deploy_mode == "hosted" and not settings.hosted_github_login_enabled:
        return _redirect_to_login_with_error(
            oauth_error="github_oauth_disabled",
            redirect_to=safe_redirect,
        )
    if not _github_oauth_is_configured():
        return _redirect_to_login_with_error(
            oauth_error="github_oauth_not_configured",
            redirect_to=safe_redirect,
        )

    authorize_url, state_token, code_verifier = _build_github_authorize_url(
        request,
        redirect_to=safe_redirect,
    )
    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    _set_github_oauth_cookie(
        response,
        request,
        key=GITHUB_OAUTH_STATE_COOKIE_NAME,
        value=state_token,
    )
    _set_github_oauth_cookie(
        response,
        request,
        key=GITHUB_OAUTH_PKCE_COOKIE_NAME,
        value=code_verifier,
    )
    return response


@router.get("/github/callback", name="github_oauth_callback", include_in_schema=False)
def github_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        raise HTTPException(status_code=405, detail="GitHub OAuth disabled in selfhost mode")
    if settings.deploy_mode == "hosted" and not settings.hosted_github_login_enabled:
        return _redirect_to_login_with_error(oauth_error="github_oauth_disabled")
    if not _github_oauth_is_configured():
        return _redirect_to_login_with_error(oauth_error="github_oauth_not_configured")

    try:
        cookie_state = request.cookies.get(GITHUB_OAUTH_STATE_COOKIE_NAME)
        if not state or not cookie_state or state != cookie_state:
            raise ValueError("GitHub OAuth state mismatch")
        state_payload = decode_oauth_state_token(token=state, provider=AUTH_PROVIDER_GITHUB)
        redirect_to = resolve_safe_post_login_redirect(state_payload["redirect_to"])
        code_verifier = request.cookies.get(GITHUB_OAUTH_PKCE_COOKIE_NAME)
        if not code_verifier:
            raise ValueError("GitHub OAuth PKCE verifier missing")
    except ValueError:
        return _redirect_to_login_with_error(oauth_error="github_oauth_state_invalid")

    if error:
        oauth_error = "github_oauth_access_denied" if error == "access_denied" else "github_oauth_failed"
        return _redirect_to_login_with_error(oauth_error=oauth_error, redirect_to=redirect_to)
    if not code:
        return _redirect_to_login_with_error(oauth_error="github_oauth_failed", redirect_to=redirect_to)

    try:
        identity = exchange_github_code_for_identity(
            request=request,
            code=code,
            code_verifier=code_verifier,
        )
        user, _created = resolve_or_provision_hosted_user_for_identity(
            db,
            provider=AUTH_PROVIDER_GITHUB,
            provider_user_id=identity.provider_user_id,
            nickname=identity.display_name,
            username_seed=identity.login,
            provider_login=identity.login,
            provider_email=identity.email,
            signup_meta=_build_signup_event_meta(
                provider=AUTH_PROVIDER_GITHUB,
                attribution={
                    "entry_path": "github_oauth",
                    "redirect_to": redirect_to,
                },
            ),
        )
    except HTTPException as exc:
        if exc.status_code == 503 and isinstance(exc.detail, dict) and exc.detail.get("code") == "hosted_user_cap_reached":
            return _redirect_to_login_with_error(
                oauth_error="github_oauth_signup_blocked",
                redirect_to=redirect_to,
            )
        if exc.status_code == 403:
            return _redirect_to_login_with_error(
                oauth_error="github_oauth_account_disabled",
                redirect_to=redirect_to,
            )
        logger.warning("GitHub OAuth callback returned HTTP %s", exc.status_code)
        return _redirect_to_login_with_error(oauth_error="github_oauth_failed", redirect_to=redirect_to)
    except Exception:
        logger.exception("GitHub OAuth callback failed")
        return _redirect_to_login_with_error(oauth_error="github_oauth_failed", redirect_to=redirect_to)

    response = RedirectResponse(url=redirect_to, status_code=status.HTTP_303_SEE_OTHER)
    _clear_github_oauth_cookies(response)
    issue_user_session(response=response, request=request, user=user)
    return response


@router.post("/login", response_model=TokenResponse)
def login(request: Request, response: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        from app.core.auth import _get_or_create_default_user
        user = _get_or_create_default_user(db)
        token = issue_user_session(response=response, request=request, user=user)
        return TokenResponse(access_token=token)

    user = authenticate_hosted_user_by_nickname_password(
        db,
        nickname=form.username,
        password=form.password,
    )
    token = issue_user_session(response=response, request=request, user=user)
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_auth_cookie(response)


@router.get("/me", response_model=UserResponse)
def me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    if reconcile_abandoned_quota_reservations(db, user_id=current_user.id) > 0:
        db.refresh(current_user)
    return current_user


@router.get("/quota", response_model=QuotaResponse)
def get_quota(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    if reconcile_abandoned_quota_reservations(db, user_id=current_user.id) > 0:
        db.refresh(current_user)
    return QuotaResponse(
        generation_quota=current_user.generation_quota,
        feedback_submitted=current_user.feedback_submitted,
    )


class PreferencesRequest(BaseModel):
    preferences: dict


ALLOWED_PREFERENCE_KEYS = {"num_versions", "temperature", "context_chapters", "target_chars"}


@router.patch("/preferences", response_model=UserResponse)
def update_preferences(
    body: PreferencesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Update user preferences (generation defaults). Only known keys are stored."""
    filtered = {k: v for k, v in body.preferences.items() if k in ALLOWED_PREFERENCE_KEYS}
    if "context_chapters" in filtered:
        raw_context_chapters = filtered["context_chapters"]
        if isinstance(raw_context_chapters, int):
            filtered["context_chapters"] = resolve_context_chapters(raw_context_chapters)
    existing = current_user.preferences or {}
    existing.update(filtered)
    current_user.preferences = existing
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/feedback", response_model=QuotaResponse)
def submit_feedback(
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Submit feedback to unlock bonus quota. Requires all structured answers."""
    settings = get_settings()

    if current_user.feedback_submitted:
        return QuotaResponse(
            generation_quota=current_user.generation_quota,
            feedback_submitted=True,
        )

    missing = REQUIRED_FEEDBACK_KEYS - set(body.answers.keys())
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required feedback fields: {', '.join(sorted(missing))}")

    # overall_rating must be a non-empty string
    if not isinstance(body.answers.get("overall_rating"), str) or not body.answers["overall_rating"].strip():
        raise HTTPException(status_code=422, detail="overall_rating cannot be empty")

    # issues must be a non-empty list
    issues = body.answers.get("issues")
    if not isinstance(issues, list) or len(issues) == 0:
        raise HTTPException(status_code=422, detail="issues must be a non-empty list")

    # Conditional required: bug_description when "bugs" in issues
    if "bugs" in issues:
        bug_desc = body.answers.get("bug_description", "")
        if not isinstance(bug_desc, str) or not bug_desc.strip():
            raise HTTPException(status_code=422, detail="bug_description is required when 'bugs' is selected")

    # Conditional required: other_description when "other" in issues
    if "other" in issues:
        other_desc = body.answers.get("other_description", "")
        if not isinstance(other_desc, str) or not other_desc.strip():
            raise HTTPException(status_code=422, detail="other_description is required when 'other' is selected")

    # Calculate bonus: base + suggestion bonus if suggestion qualifies
    bonus = settings.feedback_bonus_quota
    suggestion = body.answers.get("suggestion", "")
    if isinstance(suggestion, str):
        trimmed = "".join(suggestion.split())
        if len(trimmed) >= 20 and len(set(trimmed)) >= 6:
            bonus += settings.feedback_suggestion_bonus_quota

    current_user.feedback_submitted = True
    current_user.feedback_answers = body.answers
    current_user.generation_quota += bonus
    db.commit()
    db.refresh(current_user)
    return QuotaResponse(
        generation_quota=current_user.generation_quota,
        feedback_submitted=current_user.feedback_submitted,
    )


class FeedbackExportItem(BaseModel):
    user_id: int
    nickname: str | None = None
    generation_quota: int
    feedback_answers: dict | None = None
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/admin/feedback", response_model=list[FeedbackExportItem])
def export_feedback(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Export all submitted feedback (admin only)."""
    users = db.query(User).filter(User.feedback_submitted == True).all()  # noqa: E712
    return [
        FeedbackExportItem(
            user_id=u.id,
            nickname=u.nickname,
            generation_quota=u.generation_quota,
            feedback_answers=u.feedback_answers,
            created_at=str(u.created_at),
        )
        for u in users
    ]


@router.get("/admin/funnel")
def get_funnel(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Self-describing hosted writer beta analytics payload for admin analysis."""
    return build_hosted_beta_funnel_report(db)
