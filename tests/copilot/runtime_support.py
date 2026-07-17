# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared support objects for split copilot runtime tests."""

from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.llm_config import ResolvedLlmConfig

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_LLM_CONFIG = ResolvedLlmConfig(
    base_url="https://example.com/v1",
    api_key="test-key",
    model="test-model",
    billing_source_hint="selfhost",
    source="selfhost_settings",
)


async def noop_coro():
    return None
