"""Authentication API endpoints."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import resolve_context_chapters
from app.core.auth import clear_auth_cookie, get_current_user_or_default, issue_user_session
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    nickname: str | None = None
    role: str
    is_active: bool
    preferences: dict | None = None

    model_config = {"from_attributes": True}


@router.post("/login", response_model=TokenResponse)
def login(request: Request, response: Response, user: User = Depends(get_current_user_or_default)):
    return TokenResponse(access_token=issue_user_session(response=response, request=request, user=user))


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_auth_cookie(response)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user_or_default)):
    return current_user


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
    current_user.preferences = {**(current_user.preferences or {}), **filtered}
    db.commit()
    db.refresh(current_user)
    return current_user
