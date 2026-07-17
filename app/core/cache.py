# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Cache/derived-state invalidation hooks for novel-level mutations."""

__all__ = ["invalidate_novel_language_caches"]


def invalidate_novel_language_caches(db, novel_id: int) -> None:
    """Invalidate derived state affected by a Novel.language change.

    Must be called whenever Novel.language is mutated. The window index
    revision is advanced because tokenizer inputs depend on language.

    Caller must commit the surrounding transaction and schedule a rebuild if
    they want the index refreshed immediately.
    """
    from app.models import Novel
    from app.core.indexing.lifecycle import mark_window_index_inputs_changed
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel is not None:
        mark_window_index_inputs_changed(novel)
