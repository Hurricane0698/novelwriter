# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Shared FastAPI dependencies for API routers."""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_or_default
from app.database import get_db
from app.models import Novel, User


def verify_novel_access(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
) -> Novel:
    novel = db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

    return novel
