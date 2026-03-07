# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""
LoreManager: Millisecond-level entity-triggered context injection.

Performance target: <10ms for 100K entries using Aho-Corasick automaton.

Session Safety: This class does NOT store db: Session. The automaton/state
can be cached, and db is passed only to methods that need data access.
"""

import ahocorasick
import re
import uuid
from dataclasses import dataclass
from typing import List, Dict, Optional, Set, Tuple

from sqlalchemy.orm import Session, joinedload

from app.models import LoreEntry
from app.config import get_settings


@dataclass(frozen=True)
class LoreEntrySnapshot:
    """Detached-safe snapshot of lore entry fields used during injection."""

    title: str
    content: str
    entry_type: str
    token_budget: int
    priority: int


class LoreManager:
    """
    Manages Lorebook entries and keyword matching using Aho-Corasick automaton.

    The automaton is built per-novel and cached. Rebuild is triggered on:
    - Entry creation/deletion
    - Keyword modification
    - Entry enable/disable toggle

    Session Safety: db is NOT stored. Pass db to methods that need data access.
    This allows the instance to be safely cached across requests.
    """

    def __init__(self, novel_id: int):
        """Initialize LoreManager without db (session-safe for caching)."""
        self.novel_id = novel_id
        self.settings = get_settings()
        # Case-insensitive keywords use this automaton (lowercased).
        self._automaton: Optional[ahocorasick.Automaton] = None
        # Case-sensitive keywords use their own automaton.
        self._automaton_sensitive: Optional[ahocorasick.Automaton] = None
        # Regex patterns can be multiple per entry.
        self._regex_patterns: List[Tuple[int, str, re.Pattern]] = []
        self._entry_cache: Dict[int, LoreEntrySnapshot] = {}
        self._is_built = False

    @property
    def entry_count(self) -> int:
        """Return number of cached entries (for status checks)."""
        return len(self._entry_cache)

    def build_automaton(self, db: Session) -> None:
        """
        Build Aho-Corasick automaton from all enabled entries for this novel.

        Args:
            db: Database session for loading entries

        Time complexity: O(sum of keyword lengths)
        Space complexity: O(sum of keyword lengths)
        """
        self._automaton = ahocorasick.Automaton()
        self._automaton_sensitive = ahocorasick.Automaton()
        self._regex_patterns = []
        self._entry_cache.clear()

        entries = (
            db.query(LoreEntry)
            .options(joinedload(LoreEntry.keywords))
            .filter(
                LoreEntry.novel_id == self.novel_id,
                LoreEntry.enabled.is_(True)
            )
            .all()
        )

        insensitive_keywords: Dict[str, List[Tuple[int, str]]] = {}
        sensitive_keywords: Dict[str, List[Tuple[int, str]]] = {}

        for entry in entries:
            self._entry_cache[entry.id] = LoreEntrySnapshot(
                title=entry.title,
                content=entry.content,
                entry_type=entry.entry_type,
                token_budget=entry.token_budget,
                priority=entry.priority,
            )

            for key in entry.keywords:
                if key.is_regex:
                    try:
                        flags = 0 if key.case_sensitive else re.IGNORECASE
                        self._regex_patterns.append((entry.id, key.keyword, re.compile(key.keyword, flags)))
                    except re.error:
                        pass
                else:
                    keyword = key.keyword if key.case_sensitive else key.keyword.lower()
                    target_map = sensitive_keywords if key.case_sensitive else insensitive_keywords
                    if keyword not in target_map:
                        target_map[keyword] = []
                    target_map[keyword].append((entry.id, key.keyword))

        for keyword, values in insensitive_keywords.items():
            self._automaton.add_word(keyword, values)

        for keyword, values in sensitive_keywords.items():
            self._automaton_sensitive.add_word(keyword, values)

        self._automaton.make_automaton()
        self._automaton_sensitive.make_automaton()
        self._is_built = True

    def match(self, text: str, db: Optional[Session] = None) -> List[Tuple[int, str, List[str]]]:
        """
        Find all matching entries in the given text.

        Args:
            text: Input text to scan for keywords
            db: Optional db session (only needed if automaton not yet built)

        Returns:
            List of (entry_id, entry_title, matched_keywords)
            Sorted by priority (ascending = higher priority first)

        Time complexity: O(len(text) + number of matches)
        """
        if not self._is_built:
            if db is None:
                raise ValueError("LoreManager not built. Call build_automaton(db) first or pass db here.")
            self.build_automaton(db)

        matches: Dict[int, Set[str]] = {}

        # Handle empty automaton (no entries)
        if not self._entry_cache:
            return []

        if self._automaton is not None and len(self._automaton) > 0:
            text_lower = text.lower()
            for _, values in self._automaton.iter(text_lower):
                for entry_id, keyword in values:
                    if entry_id not in matches:
                        matches[entry_id] = set()
                    matches[entry_id].add(keyword)

        if self._automaton_sensitive is not None and len(self._automaton_sensitive) > 0:
            for _, values in self._automaton_sensitive.iter(text):
                for entry_id, keyword in values:
                    if entry_id not in matches:
                        matches[entry_id] = set()
                    matches[entry_id].add(keyword)

        for entry_id, keyword, pattern in self._regex_patterns:
            if pattern.search(text):
                if entry_id not in matches:
                    matches[entry_id] = set()
                matches[entry_id].add(f"[regex:{keyword}]")

        results = []
        for entry_id, keywords in matches.items():
            entry = self._entry_cache.get(entry_id)
            if entry:
                results.append((entry_id, entry.title, list(keywords)))

        results.sort(key=lambda x: self._entry_cache[x[0]].priority)

        return results

    def get_injection_context(
        self,
        text: str,
        db: Optional[Session] = None,
        max_tokens: Optional[int] = None
    ) -> Tuple[str, List[Dict], int]:
        """
        Get injectable context based on keyword matches, respecting token budget.

        Args:
            text: Input text to scan
            db: Optional db session (only needed if automaton not yet built)
            max_tokens: Override for max total tokens (default from config)

        Returns:
            (combined_context_string, list_of_matched_entries_metadata, total_tokens_used)
        """
        if max_tokens is None:
            max_tokens = self.settings.lore_max_total_tokens

        matches = self.match(text, db=db)

        injected_entries = []
        total_tokens = 0
        context_parts = []

        for entry_id, title, keywords in matches:
            entry = self._entry_cache.get(entry_id)
            if not entry:
                continue

            if total_tokens + entry.token_budget > max_tokens:
                continue

            total_tokens += entry.token_budget
            context_parts.append(f"[{entry.entry_type}: {entry.title}]\n{entry.content}")
            injected_entries.append({
                "entry_id": entry_id,
                "title": title,
                "content": entry.content,
                "entry_type": entry.entry_type,
                "priority": entry.priority,
                "matched_keywords": keywords,
                "tokens_used": entry.token_budget,
            })

        combined_context = "\n\n".join(context_parts)
        return combined_context, injected_entries, total_tokens

    def invalidate_cache(self) -> None:
        """Force rebuild of automaton on next match call."""
        self._automaton = None
        self._automaton_sensitive = None
        self._regex_patterns = []
        self._entry_cache.clear()
        self._is_built = False

    @staticmethod
    def generate_uid() -> str:
        """Generate UUID for character card sync."""
        return str(uuid.uuid4())
