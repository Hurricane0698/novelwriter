# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared FastAPI dependencies for API routers."""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import get_current_user_or_default
from app.database import get_db
from app.models import Novel, User


def verify_novel_access(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
) -> Novel:
    """Ensure `novel_id` exists and is accessible to the current user.

    - hosted: strict owner_id isolation (404 for cross-user to avoid existence leaks)
    - selfhost: single-user local mode; ignore owner_id for local DB resilience
    """
    novel = db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

    settings = get_settings()
    if settings.deploy_mode == "hosted" and novel.owner_id != current_user.id:
        # Must not leak existence across users.
        raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")
    return novel
