from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from app.core.indexing.lifecycle import WindowIndexLifecycleSnapshot
from app.core.indexing.status import resolve_window_index_readiness
from app.models import Novel

from .job_store import (
    INGEST_JOB_STAGE_ACCEPTED,
    INGEST_JOB_STATUS_FAILED,
    INGEST_JOB_STATUS_QUEUED,
    INGEST_JOB_STATUS_RUNNING,
    NovelIngestJobSnapshot,
    inspect_novel_ingest_job,
    inspect_novel_ingest_jobs,
)

READINESS_ACCEPTING = "accepting"
READINESS_PROCESSING = "processing"
READINESS_READY = "ready"
READINESS_DEGRADED_READY = "degraded_ready"
READINESS_FAILED_RETRYABLE = "failed_retryable"


@dataclass(frozen=True, slots=True)
class NovelReadinessCapabilities:
    chapters_available: bool
    whole_book_index_available: bool
    bootstrap_available: bool
    recent_fallback_only: bool


@dataclass(frozen=True, slots=True)
class NovelReadinessSnapshot:
    readiness: str
    capabilities: NovelReadinessCapabilities
    ingest_job: NovelIngestJobSnapshot | None


def resolve_novel_readiness(
    novel: Novel,
    *,
    index_state: WindowIndexLifecycleSnapshot,
    ingest_job: NovelIngestJobSnapshot | None,
) -> NovelReadinessSnapshot:
    index_readiness = resolve_window_index_readiness(index_state)
    chapters_available = int(getattr(novel, "total_chapters", 0) or 0) > 0
    whole_book_index_available = index_readiness.whole_book_index_available
    bootstrap_plan = ingest_job.bootstrap_plan if ingest_job is not None else None
    if not chapters_available:
        bootstrap_available = False
    elif bootstrap_plan == "defer_until_index":
        bootstrap_available = whole_book_index_available
    else:
        bootstrap_available = True
    capabilities = NovelReadinessCapabilities(
        chapters_available=chapters_available,
        whole_book_index_available=whole_book_index_available,
        bootstrap_available=bootstrap_available,
        recent_fallback_only=chapters_available and index_readiness.requires_recent_fallback,
    )

    if ingest_job is not None:
        if (
            ingest_job.status == INGEST_JOB_STATUS_QUEUED
            and ingest_job.stage == INGEST_JOB_STAGE_ACCEPTED
            and not chapters_available
        ):
            return NovelReadinessSnapshot(
                readiness=READINESS_ACCEPTING,
                capabilities=capabilities,
                ingest_job=ingest_job,
            )
        if ingest_job.status in {INGEST_JOB_STATUS_QUEUED, INGEST_JOB_STATUS_RUNNING}:
            readiness = READINESS_DEGRADED_READY if chapters_available else READINESS_PROCESSING
            return NovelReadinessSnapshot(readiness=readiness, capabilities=capabilities, ingest_job=ingest_job)
        if ingest_job.status == INGEST_JOB_STATUS_FAILED and not chapters_available:
            return NovelReadinessSnapshot(
                readiness=READINESS_FAILED_RETRYABLE,
                capabilities=capabilities,
                ingest_job=ingest_job,
            )

    if whole_book_index_available:
        readiness = READINESS_READY
    elif chapters_available:
        readiness = READINESS_DEGRADED_READY
    elif index_readiness.retryable:
        readiness = READINESS_FAILED_RETRYABLE
    else:
        readiness = READINESS_PROCESSING

    return NovelReadinessSnapshot(readiness=readiness, capabilities=capabilities, ingest_job=ingest_job)


def inspect_novel_readiness(
    novel: Novel,
    *,
    db,
    index_state: WindowIndexLifecycleSnapshot,
) -> NovelReadinessSnapshot:
    novel_id = getattr(novel, "id", None)
    ingest_job = inspect_novel_ingest_job(db, novel_id=novel_id) if isinstance(novel_id, int) else None
    return resolve_novel_readiness(novel, index_state=index_state, ingest_job=ingest_job)


def inspect_novel_readinesses(
    novels: Iterable[Novel],
    *,
    db,
    index_states: Mapping[int, WindowIndexLifecycleSnapshot],
) -> dict[int, NovelReadinessSnapshot]:
    novel_list = [novel for novel in novels if isinstance(getattr(novel, "id", None), int)]
    ingest_jobs = inspect_novel_ingest_jobs(db, novel_ids=[int(novel.id) for novel in novel_list])
    return {
        int(novel.id): resolve_novel_readiness(
            novel,
            index_state=index_states[int(novel.id)],
            ingest_job=ingest_jobs.get(int(novel.id)),
        )
        for novel in novel_list
        if int(novel.id) in index_states
    }
