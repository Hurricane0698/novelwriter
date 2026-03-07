"""Tests for app/core/cache.py — CacheManager singleton and operations."""

import pytest
from unittest.mock import MagicMock
from app.core.cache import CacheManager


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton between tests to avoid cross-test pollution."""
    CacheManager._instance = None
    yield
    CacheManager._instance = None


def test_singleton():
    a = CacheManager()
    b = CacheManager()
    assert a is b


# --- Lore cache ---


def test_get_lore_miss():
    cm = CacheManager()
    assert cm.get_lore(999) is None


def test_set_get_lore_hit():
    cm = CacheManager()
    fake_lore = MagicMock()
    cm.set_lore(1, fake_lore)
    assert cm.get_lore(1) is fake_lore


# --- Invalidation ---


def test_invalidate_novel_clears_lore():
    cm = CacheManager()
    cm.set_lore(1, MagicMock())
    cm.invalidate_novel(1)
    assert cm.get_lore(1) is None


def test_invalidate_nonexistent_novel_no_error():
    cm = CacheManager()
    cm.invalidate_novel(999)  # should not raise


def test_invalidate_preserves_other_novels():
    cm = CacheManager()
    lore2 = MagicMock()
    cm.set_lore(1, MagicMock())
    cm.set_lore(2, lore2)
    cm.invalidate_novel(1)
    assert cm.get_lore(1) is None
    assert cm.get_lore(2) is lore2
