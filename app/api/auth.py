"""Authentication API endpoints."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.config import get_settings, resolve_context_chapters
from app.database import get_db
from app.models import User, UserEvent
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    clear_auth_cookie,
    get_current_user_or_default,
    require_admin,
    set_auth_cookie,
)
from app.core.events import record_event
from app.core.safety_fuses import ensure_hosted_user_capacity, hosted_signup_lock

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=128)


class InviteRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=100)
    nickname: str = Field(min_length=1, max_length=150)


REQUIRED_FEEDBACK_KEYS = {"overall_rating", "issues"}


class FeedbackRequest(BaseModel):
    answers: dict


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    # Pre-launch hosted is invite-only by design; selfhost uses the default user flow.
    raise HTTPException(
        status_code=405,
        detail=(
            "Registration disabled in hosted mode; use invite code login"
            if settings.deploy_mode == "hosted"
            else "Registration disabled in selfhost mode"
        ),
    )


@router.post("/invite", response_model=TokenResponse, status_code=201)
def invite_register(body: InviteRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Register via invite code + nickname (hosted mode only)."""
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        raise HTTPException(status_code=405, detail="Invite registration disabled in selfhost mode")

    if not settings.invite_code:
        raise HTTPException(status_code=503, detail="Invite registration not configured")

    if body.invite_code != settings.invite_code:
        raise HTTPException(status_code=403, detail="Invalid invite code")

    # Generate a unique internal username from nickname
    nickname = body.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=422, detail="nickname cannot be empty")

    with hosted_signup_lock(db):
        # Durable re-login: if this nickname already exists, treat invite as a login.
        #
        # This prevents users from being forced into new accounts when JWT expires, and
        # prevents quota resets on re-login.
        existing = db.query(User).filter(User.nickname == nickname).order_by(User.created_at.asc()).first()
        if existing is not None:
            if not existing.is_active:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
            existing_username = existing.username
            db.rollback()
            token = create_access_token({"sub": existing_username})
            set_auth_cookie(response, request, token)
            return TokenResponse(access_token=token)

        ensure_hosted_user_capacity(db)

        suffix = secrets.token_hex(4)
        max_prefix = max(1, 150 - (1 + len(suffix)))
        username = f"{nickname[:max_prefix]}_{suffix}"

        user = User(
            username=username,
            nickname=nickname,
            hashed_password=hash_password(secrets.token_hex(16)),
            generation_quota=settings.initial_quota,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    record_event(db, user.id, "signup")

    # Seed demo novel for new user (best-effort; failure doesn't block signup).
    try:
        from app.core.seed_demo import seed_demo_novel
        seed_demo_novel(db, user)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to seed demo novel for user %s", user.id)

    token = create_access_token({"sub": user.username})
    set_auth_cookie(response, request, token)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(request: Request, response: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        from app.core.auth import _get_or_create_default_user
        user = _get_or_create_default_user(db)
        token = create_access_token({"sub": user.username})
        set_auth_cookie(response, request, token)
        return TokenResponse(access_token=token)

    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    token = create_access_token({"sub": user.username})
    set_auth_cookie(response, request, token)
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_auth_cookie(response)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user_or_default)):
    return current_user


@router.get("/quota", response_model=QuotaResponse)
def get_quota(current_user: User = Depends(get_current_user_or_default)):
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


EVENT_CATALOG = {
    "signup": {
        "description": "User registered via invite code",
        "funnel_position": 1,
        "question": "How many people entered the product?",
    },
    "novel_upload": {
        "description": "User uploaded a novel (.txt file parsed into chapters)",
        "funnel_position": 2,
        "question": "Activation rate: signup → first upload",
    },
    "bootstrap_run": {
        "description": "Bootstrap pipeline completed (auto-extracts entities/relationships from novel text)",
        "funnel_position": 3,
        "question": "Do users run the auto-extraction after uploading?",
        "meta_keys": {"mode": "bootstrap mode (initial/reextract/index_refresh)", "entities_found": "int", "relationships_found": "int"},
    },
    "draft_confirm": {
        "description": "User accepted AI-generated draft entities/relationships/systems into their world model",
        "funnel_position": 4,
        "question": "Adoption rate: what fraction of AI-generated drafts do users keep?",
        "meta_keys": {"type": "entity|relationship|system", "count": "number confirmed in this batch"},
    },
    "draft_reject": {
        "description": "User rejected (deleted) AI-generated drafts",
        "funnel_position": 4,
        "question": "Rejection rate: complement of adoption rate — signals generation quality",
        "meta_keys": {"type": "entity|relationship|system", "count": "number rejected in this batch"},
    },
    "world_generate": {
        "description": "User generated world model drafts from a text description (设定集 generation)",
        "funnel_position": 4,
        "question": "Are users using the text-to-world-model feature?",
    },
    "world_edit": {
        "description": "User manually created or edited a world model element (not bootstrap/AI-generated)",
        "funnel_position": 5,
        "question": "Differentiation signal: do users understand and engage with the world model?",
        "meta_keys": {"action": "create_entity|update_entity|create_relationship|update_relationship|create_system|update_system"},
    },
    "generation": {
        "description": "Novel continuation generated successfully (the core value-delivery moment)",
        "funnel_position": 6,
        "question": "Core loop: are users actually generating text?",
        "meta_keys": {"variants": "number of variants generated", "stream": "true if via streaming endpoint"},
    },
    "chapter_save": {
        "description": "User saved/updated a chapter (may incorporate generated content)",
        "funnel_position": 7,
        "question": "Retention signal: are users integrating generated content into their novel?",
        "meta_keys": {"chapter": "chapter number"},
    },
}


@router.get("/admin/funnel")
def get_funnel(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Self-describing analytics endpoint. Response includes event definitions,
    aggregated funnel data, and recent raw events — paste into any AI for analysis."""
    # Funnel aggregation
    rows = (
        db.query(UserEvent.event, sa_func.count(UserEvent.id), sa_func.count(sa_func.distinct(UserEvent.user_id)))
        .group_by(UserEvent.event)
        .all()
    )
    total_users = db.query(sa_func.count(User.id)).scalar() or 0
    funnel = {event: {"total": count, "unique_users": users} for event, count, users in rows}

    # Daily breakdown (last 30 days)
    import datetime
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    daily_rows = (
        db.query(
            UserEvent.event,
            sa_func.date(UserEvent.created_at).label("day"),
            sa_func.count(UserEvent.id),
        )
        .filter(UserEvent.created_at >= cutoff)
        .group_by(UserEvent.event, "day")
        .all()
    )
    daily = {}
    for event, day, count in daily_rows:
        daily.setdefault(event, {})[str(day)] = count

    # Recent raw events (last 100) for pattern inspection
    recent = (
        db.query(UserEvent)
        .order_by(UserEvent.created_at.desc())
        .limit(100)
        .all()
    )
    recent_events = [
        {"user_id": e.user_id, "event": e.event, "novel_id": e.novel_id, "meta": e.meta, "created_at": str(e.created_at)}
        for e in recent
    ]

    return {
        "analysis_prompt": (
            "You are analyzing product analytics for a novel-writing AI tool. "
            "The core loop is: signup → upload novel → bootstrap (auto-extract world model) → "
            "review drafts (confirm/reject) → edit world model → generate continuation → save chapter. "
            "Use event_catalog for event definitions. Identify drop-off points, adoption rates, "
            "and actionable recommendations."
        ),
        "event_catalog": EVENT_CATALOG,
        "total_users": total_users,
        "funnel_summary": funnel,
        "daily_breakdown_last_30d": daily,
        "recent_events": recent_events,
    }
