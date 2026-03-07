"""Canonical visibility constants and helpers for the WorldModel layer.

Zero internal dependencies — safe to import from schemas, core, and api.
"""

from typing import Literal

WorldVisibility = Literal["active", "reference", "hidden"]

VIS_ACTIVE: WorldVisibility = "active"
VIS_REFERENCE: WorldVisibility = "reference"
VIS_HIDDEN: WorldVisibility = "hidden"

ALLOWED_VISIBILITIES = frozenset({VIS_ACTIVE, VIS_REFERENCE, VIS_HIDDEN})


def normalize_visibility(v: object) -> object:
    """Normalize common user/LLM variants (e.g. ``"Active "``, ``None``) before
    strict ``Literal`` validation.  Returns the cleaned value — does **not**
    enforce validity itself.
    """
    if v is None:
        return v
    if isinstance(v, str):
        return v.strip().lower()
    return v
