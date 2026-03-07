from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.database import Base
from app.world_relationships import canonicalize_relationship_label


class Novel(Base):
    __tablename__ = "novels"
    # Prevent SQLite from reusing primary keys after deletes (fixes id collisions with
    # persisted client state keyed by novel id). This emits `AUTOINCREMENT` on SQLite.
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    author = Column(String(255), default="")
    file_path = Column(String(512), nullable=False)
    total_chapters = Column(Integer, default=0)
    window_index = Column(LargeBinary, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    chapters = relationship("Chapter", back_populates="novel", cascade="all, delete-orphan")
    outlines = relationship("Outline", back_populates="novel", cascade="all, delete-orphan")
    continuations = relationship("Continuation", back_populates="novel", cascade="all, delete-orphan")
    lore_entries = relationship("LoreEntry", back_populates="novel", cascade="all, delete-orphan")
    bootstrap_job = relationship("BootstrapJob", back_populates="novel", uselist=False, cascade="all, delete-orphan")


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("novel_id", "chapter_number", name="uq_chapters_novel_chapter_number"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String(255), default="")
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    novel = relationship("Novel", back_populates="chapters")


class Outline(Base):
    __tablename__ = "outlines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=False)
    chapter_start = Column(Integer, nullable=False)
    chapter_end = Column(Integer, nullable=False)
    outline_text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    novel = relationship("Novel", back_populates="outlines")


class Continuation(Base):
    __tablename__ = "continuations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    prompt_used = Column(Text, default="")
    rating = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    novel = relationship("Novel", back_populates="continuations")


class LoreEntry(Base):
    """
    Lorebook entry containing injectable context fragments.

    Types: Character | Location | Item | Faction | Event
    Priority: Lower number = higher priority (1 = protagonist)
    """
    __tablename__ = "lore_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=False)
    uid = Column(String(36), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    entry_type = Column(String(50), nullable=False)
    token_budget = Column(Integer, default=500)
    priority = Column(Integer, default=100)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    novel = relationship("Novel", back_populates="lore_entries")
    keywords = relationship("LoreKey", back_populates="entry", cascade="all, delete-orphan")


class LoreKey(Base):
    """
    Keywords that trigger LoreEntry injection.
    Fed to pyahocorasick automaton for O(M) matching.
    """
    __tablename__ = "lore_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(Integer, ForeignKey("lore_entries.id"), nullable=False)
    keyword = Column(String(255), nullable=False)
    is_regex = Column(Boolean, default=False)
    case_sensitive = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    entry = relationship("LoreEntry", back_populates="keywords")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(150), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    is_active = Column(Boolean, nullable=False, default=True)
    nickname = Column(String(150), nullable=True)
    generation_quota = Column(Integer, nullable=False, default=5)
    feedback_submitted = Column(Boolean, nullable=False, default=False)
    feedback_answers = Column(JSON, nullable=True)
    preferences = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TokenUsage(Base):
    """Token usage tracking for LLM cost metering."""
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    model = Column(String(100), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    cost_estimate = Column(Float, nullable=False, default=0.0)
    billing_source = Column(String(20), nullable=False, default="selfhost")
    endpoint = Column(String(255), nullable=True)
    node_name = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_token_usage_created_at", "created_at"),
        Index("ix_token_usage_model", "model"),
        Index("ix_token_usage_billing_source_created_at", "billing_source", "created_at"),
        # Hosted-mode usage queries filter by user_id and often sort by created_at.
        Index("ix_token_usage_user_id_created_at", "user_id", "created_at"),
    )


class WorldEntity(Base):
    __tablename__ = "world_entities"
    __table_args__ = (
        UniqueConstraint("novel_id", "name", name="uq_world_entities_novel_name"),
        UniqueConstraint(
            "novel_id",
            "worldpack_pack_id",
            "worldpack_key",
            name="uq_world_entities_novel_worldpack_pack_key",
        ),
        CheckConstraint(
            "(worldpack_pack_id IS NULL AND worldpack_key IS NULL) OR "
            "(worldpack_pack_id IS NOT NULL AND worldpack_key IS NOT NULL)",
            name="ck_world_entities_worldpack_identity_complete",
        ),
        Index("ix_world_entities_novel_type_status", "novel_id", "entity_type", "status"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=False)
    name = Column(String(255), nullable=False)
    entity_type = Column(String(50), nullable=False)
    description = Column(Text, default="")
    aliases = Column(JSON, default=list)
    worldpack_pack_id = Column(String(255), nullable=True)
    worldpack_key = Column(String(255), nullable=True)
    origin = Column(String(20), nullable=False, default="manual")
    status = Column(String(20), default="draft")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    novel = relationship("Novel")
    attributes = relationship("WorldEntityAttribute", back_populates="entity", cascade="all, delete-orphan")
    source_relationships = relationship("WorldRelationship", foreign_keys="WorldRelationship.source_id", cascade="all, delete-orphan")
    target_relationships = relationship("WorldRelationship", foreign_keys="WorldRelationship.target_id", cascade="all, delete-orphan")


class WorldEntityAttribute(Base):
    __tablename__ = "world_entity_attributes"
    __table_args__ = (
        UniqueConstraint("entity_id", "key", name="uq_world_entity_attributes_entity_key"),
        Index("ix_world_entity_attributes_entity_visibility", "entity_id", "visibility"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Integer, ForeignKey("world_entities.id"), nullable=False)
    key = Column(String(255), nullable=False)
    surface = Column(Text, nullable=False)
    truth = Column(Text, default=None)
    visibility = Column(String(20), nullable=False, default="active")
    origin = Column(String(20), nullable=False, default="manual")
    worldpack_pack_id = Column(String(255), nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    entity = relationship("WorldEntity", back_populates="attributes")


class WorldRelationship(Base):
    __tablename__ = "world_relationships"
    __table_args__ = (
        Index("ix_world_relationships_novel_status", "novel_id", "status"),
        Index("ix_world_relationships_source", "source_id"),
        Index(
            "ix_world_relationships_pair_label_canonical",
            "novel_id",
            "source_id",
            "target_id",
            "label_canonical",
        ),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("world_entities.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("world_entities.id"), nullable=False)
    label = Column(String(100), nullable=False)
    label_canonical = Column(String(100), nullable=False, default="")
    description = Column(Text, default="")
    visibility = Column(String(20), nullable=False, default="active")
    worldpack_pack_id = Column(String(255), nullable=True)
    origin = Column(String(20), nullable=False, default="manual")
    status = Column(String(20), default="draft")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    @validates("label")
    def _set_label_canonical(self, key: str, value: str) -> str:
        self.label_canonical = canonicalize_relationship_label(value)
        return value


class WorldSystem(Base):
    __tablename__ = "world_systems"
    __table_args__ = (
        UniqueConstraint("novel_id", "name", name="uq_world_systems_novel_name"),
        Index("ix_world_systems_novel_status", "novel_id", "status"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=False)
    name = Column(String(255), nullable=False)
    display_type = Column(String(50), nullable=False)
    description = Column(Text, default="")
    data = Column(JSON, nullable=False, default=dict)
    constraints = Column(JSON, default=list)
    visibility = Column(String(20), nullable=False, default="active")
    origin = Column(String(20), nullable=False, default="manual")
    worldpack_pack_id = Column(String(255), nullable=True)
    status = Column(String(20), default="draft")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    novel = relationship("Novel")


class BootstrapJob(Base):
    __tablename__ = "bootstrap_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=False, unique=True)
    mode = Column(String(20), nullable=False, default="index_refresh")
    draft_policy = Column(String(50), nullable=True, default=None)
    initialized = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="pending")
    progress = Column(JSON, default=dict)
    result = Column(JSON, default=dict)
    error = Column(Text, default=None)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    novel = relationship("Novel", back_populates="bootstrap_job")


class UserEvent(Base):
    """Lightweight product analytics events for funnel analysis."""
    __tablename__ = "user_events"
    __table_args__ = (
        Index("ix_user_events_user_id", "user_id"),
        Index("ix_user_events_event", "event"),
        Index("ix_user_events_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event = Column(String(50), nullable=False)
    novel_id = Column(Integer, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Exploration(Base):
    __tablename__ = "explorations"
    __table_args__ = (
        UniqueConstraint("novel_id", "name", name="uq_explorations_novel_name"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    from_chapter = Column(Integer, nullable=False)
    to_chapter = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    novel = relationship("Novel")
    chapters = relationship("ExplorationChapter", back_populates="exploration", cascade="all, delete-orphan")


class ExplorationChapter(Base):
    __tablename__ = "exploration_chapters"
    __table_args__ = (
        UniqueConstraint("exploration_id", "chapter_number", name="uq_exploration_chapters_exploration_chapter"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    exploration_id = Column(Integer, ForeignKey("explorations.id"), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String(255), default="")
    content = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False)

    exploration = relationship("Exploration", back_populates="chapters")
