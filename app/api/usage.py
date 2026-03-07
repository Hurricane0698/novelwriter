# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Usage API — token cost tracking endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import TokenUsage, User
from app.core.auth import get_current_user_or_default

router = APIRouter(prefix="/api/usage", tags=["usage"], dependencies=[Depends(get_current_user_or_default)])


def _usage_query(db: Session, user: User):
    q = db.query(TokenUsage)
    if get_settings().deploy_mode == "hosted":
        q = q.filter(TokenUsage.user_id == user.id)
    return q


@router.get("/summary")
async def usage_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_default)):
    """Total tokens, total cost, breakdown by model and node."""
    totals = _usage_query(db, current_user).with_entities(
        func.coalesce(func.sum(TokenUsage.prompt_tokens), 0),
        func.coalesce(func.sum(TokenUsage.completion_tokens), 0),
        func.coalesce(func.sum(TokenUsage.total_tokens), 0),
        func.coalesce(func.sum(TokenUsage.cost_estimate), 0.0),
    ).first()

    by_model = (
        _usage_query(db, current_user)
        .with_entities(
            TokenUsage.model,
            func.sum(TokenUsage.total_tokens),
            func.sum(TokenUsage.cost_estimate),
        )
        .group_by(TokenUsage.model)
        .all()
    )

    by_node = (
        _usage_query(db, current_user)
        .with_entities(
            TokenUsage.node_name,
            func.sum(TokenUsage.total_tokens),
            func.sum(TokenUsage.cost_estimate),
        )
        .group_by(TokenUsage.node_name)
        .all()
    )

    return {
        "total_prompt_tokens": totals[0],
        "total_completion_tokens": totals[1],
        "total_tokens": totals[2],
        "total_cost_usd": round(totals[3], 6),
        "by_model": [
            {"model": m, "total_tokens": int(t), "cost_usd": round(c, 6)}
            for m, t, c in by_model
        ],
        "by_node": [
            {"node": n or "unknown", "total_tokens": int(t), "cost_usd": round(c, 6)}
            for n, t, c in by_node
        ],
    }


@router.get("/recent")
async def recent_usage(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    """Recent usage records."""
    records = (
        _usage_query(db, current_user)
        .order_by(TokenUsage.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": r.id,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
            "cost_estimate": r.cost_estimate,
            "endpoint": r.endpoint,
            "node_name": r.node_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
