"""
Tests for LoreManager class with Aho-Corasick automaton.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Novel, LoreEntry, LoreKey
from app.core.lore_manager import LoreManager


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def novel(db_session):
    """Create a test novel."""
    novel = Novel(
        title="Test Novel",
        author="Test Author",
        file_path="/test/path.txt",
        total_chapters=10,
    )
    db_session.add(novel)
    db_session.commit()
    return novel


@pytest.fixture
def lore_entries(db_session, novel):
    """Create test lore entries with keywords."""
    entries = []

    # Character entry (high priority)
    char_entry = LoreEntry(
        novel_id=novel.id,
        uid=LoreManager.generate_uid(),
        title="Protagonist",
        content="The main character of the story.",
        entry_type="Character",
        token_budget=200,
        priority=1,
        enabled=True,
    )
    db_session.add(char_entry)
    db_session.flush()

    char_key = LoreKey(
        entry_id=char_entry.id,
        keyword="protagonist",
        is_regex=False,
        case_sensitive=False,
    )
    db_session.add(char_key)
    entries.append(char_entry)

    # Item entry (medium priority)
    item_entry = LoreEntry(
        novel_id=novel.id,
        uid=LoreManager.generate_uid(),
        title="Magic Sword",
        content="A legendary sword with great power.",
        entry_type="Item",
        token_budget=150,
        priority=50,
        enabled=True,
    )
    db_session.add(item_entry)
    db_session.flush()

    item_key = LoreKey(
        entry_id=item_entry.id,
        keyword="magic sword",
        is_regex=False,
        case_sensitive=False,
    )
    db_session.add(item_key)
    entries.append(item_entry)

    # Location entry (low priority)
    loc_entry = LoreEntry(
        novel_id=novel.id,
        uid=LoreManager.generate_uid(),
        title="Ancient Temple",
        content="A mysterious temple in the mountains.",
        entry_type="Location",
        token_budget=100,
        priority=75,
        enabled=True,
    )
    db_session.add(loc_entry)
    db_session.flush()

    loc_key = LoreKey(
        entry_id=loc_entry.id,
        keyword="ancient temple",
        is_regex=False,
        case_sensitive=False,
    )
    db_session.add(loc_key)
    entries.append(loc_entry)

    # Disabled entry (should not match)
    disabled_entry = LoreEntry(
        novel_id=novel.id,
        uid=LoreManager.generate_uid(),
        title="Hidden Secret",
        content="This should not appear.",
        entry_type="Event",
        token_budget=100,
        priority=10,
        enabled=False,
    )
    db_session.add(disabled_entry)
    db_session.flush()

    disabled_key = LoreKey(
        entry_id=disabled_entry.id,
        keyword="hidden secret",
        is_regex=False,
        case_sensitive=False,
    )
    db_session.add(disabled_key)

    db_session.commit()
    return entries


class TestLoreManager:
    """Tests for LoreManager functionality."""

    def test_generate_uid(self):
        """Test UUID generation."""
        uid1 = LoreManager.generate_uid()
        uid2 = LoreManager.generate_uid()

        assert len(uid1) == 36
        assert uid1 != uid2

    def test_build_automaton(self, db_session, novel, lore_entries):
        """Test automaton building."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        assert manager._automaton is not None
        assert len(manager._entry_cache) == 3  # Only enabled entries

    def test_match_single_keyword(self, db_session, novel, lore_entries):
        """Test matching a single keyword."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        text = "The protagonist walked through the forest."
        matches = manager.match(text)

        assert len(matches) == 1
        assert matches[0][1] == "Protagonist"

    def test_match_multiple_keywords(self, db_session, novel, lore_entries):
        """Test matching multiple keywords."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        text = "The protagonist found the magic sword in the ancient temple."
        matches = manager.match(text)

        assert len(matches) == 3
        # Should be sorted by priority
        assert matches[0][1] == "Protagonist"  # priority 1
        assert matches[1][1] == "Magic Sword"  # priority 50
        assert matches[2][1] == "Ancient Temple"  # priority 75

    def test_match_case_insensitive(self, db_session, novel, lore_entries):
        """Test case-insensitive matching."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        text = "The PROTAGONIST found the MAGIC SWORD."
        matches = manager.match(text)

        assert len(matches) == 2

    def test_match_disabled_entry(self, db_session, novel, lore_entries):
        """Test that disabled entries are not matched."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        text = "The hidden secret was revealed."
        matches = manager.match(text)

        assert len(matches) == 0

    def test_get_injection_context(self, db_session, novel, lore_entries):
        """Test context injection with token budget."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        text = "The protagonist found the magic sword."
        context, entries, total_tokens = manager.get_injection_context(text)

        assert len(entries) == 2
        assert total_tokens == 350  # 200 + 150
        assert "Protagonist" in context
        assert "Magic Sword" in context

    def test_get_injection_context_with_budget(self, db_session, novel, lore_entries):
        """Test context injection respects max token budget."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        text = "The protagonist found the magic sword in the ancient temple."
        context, entries, total_tokens = manager.get_injection_context(text, max_tokens=300)

        # Should only include protagonist (200) and not exceed 300
        assert total_tokens <= 300
        assert len(entries) <= 2

    def test_cached_entries_survive_session_close(self, db_session, novel, lore_entries):
        """Cached lore entries should remain usable after the DB session closes."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        # Simulate request end where ORM instances become detached/expired.
        db_session.commit()
        db_session.close()

        context, entries, total_tokens = manager.get_injection_context(
            "The protagonist found the magic sword."
        )

        assert len(entries) == 2
        assert total_tokens == 350
        assert "Protagonist" in context
        assert "Magic Sword" in context

    def test_invalidate_cache(self, db_session, novel, lore_entries):
        """Test cache invalidation."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        assert manager._automaton is not None

        manager.invalidate_cache()

        assert manager._automaton is None
        assert len(manager._entry_cache) == 0

    def test_empty_novel(self, db_session, novel):
        """Test matching with no lore entries."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        text = "Some random text."
        matches = manager.match(text)

        assert len(matches) == 0

    def test_no_matches(self, db_session, novel, lore_entries):
        """Test text with no matching keywords."""
        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        text = "A completely unrelated sentence about cooking."
        matches = manager.match(text)

        assert len(matches) == 0

    def test_case_sensitive_keyword(self, db_session, novel):
        """Test case-sensitive keywords only match exact case."""
        entry = LoreEntry(
            novel_id=novel.id,
            uid=LoreManager.generate_uid(),
            title="Hero",
            content="A brave hero.",
            entry_type="Character",
            token_budget=100,
            priority=10,
            enabled=True,
        )
        db_session.add(entry)
        db_session.flush()

        key = LoreKey(
            entry_id=entry.id,
            keyword="Hero",
            is_regex=False,
            case_sensitive=True,
        )
        db_session.add(key)
        db_session.commit()

        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        assert manager.match("the hero arrived.") == []
        matches = manager.match("The Hero arrived.")
        assert len(matches) == 1
        assert matches[0][1] == "Hero"

    def test_shared_keyword_multiple_entries(self, db_session, novel):
        """Test shared keywords match multiple entries."""
        entry_one = LoreEntry(
            novel_id=novel.id,
            uid=LoreManager.generate_uid(),
            title="Dragon A",
            content="First dragon entry.",
            entry_type="Creature",
            token_budget=100,
            priority=5,
            enabled=True,
        )
        db_session.add(entry_one)
        db_session.flush()

        entry_two = LoreEntry(
            novel_id=novel.id,
            uid=LoreManager.generate_uid(),
            title="Dragon B",
            content="Second dragon entry.",
            entry_type="Creature",
            token_budget=100,
            priority=10,
            enabled=True,
        )
        db_session.add(entry_two)
        db_session.flush()

        db_session.add_all([
            LoreKey(entry_id=entry_one.id, keyword="dragon", is_regex=False, case_sensitive=False),
            LoreKey(entry_id=entry_two.id, keyword="dragon", is_regex=False, case_sensitive=False),
        ])
        db_session.commit()

        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        matches = manager.match("A dragon appeared.")
        titles = [match[1] for match in matches]
        assert "Dragon A" in titles
        assert "Dragon B" in titles

    def test_multiple_regex_keywords(self, db_session, novel):
        """Test multiple regex keywords for a single entry."""
        entry = LoreEntry(
            novel_id=novel.id,
            uid=LoreManager.generate_uid(),
            title="Ancient Dragon",
            content="A legendary dragon entry.",
            entry_type="Creature",
            token_budget=100,
            priority=5,
            enabled=True,
        )
        db_session.add(entry)
        db_session.flush()

        db_session.add_all([
            LoreKey(entry_id=entry.id, keyword=r"ancient\s+dragon", is_regex=True, case_sensitive=False),
            LoreKey(entry_id=entry.id, keyword=r"dragon\s+lord", is_regex=True, case_sensitive=False),
        ])
        db_session.commit()

        manager = LoreManager(novel.id)
        manager.build_automaton(db_session)

        matches = manager.match("The ancient dragon lord awoke.")
        assert len(matches) == 1
        matched_keywords = matches[0][2]
        assert any("ancient" in keyword for keyword in matched_keywords)
        assert any("dragon" in keyword for keyword in matched_keywords)
