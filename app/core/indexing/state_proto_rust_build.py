from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Sequence

from app.core.state_proto_contract import STATE_PROTO_PAYLOAD_FORMAT_VERSION

from .builder import ChapterText
from .state_proto_model import (
    TARGET_KIND_ENTITY,
    TargetSpec,
    compute_state_proto_chapter_signature,
)
from .state_proto_rust_module import get_rust_state_proto_module

RUST_STATE_PROTO_BUILD_REQUEST_FORMAT_VERSION = STATE_PROTO_PAYLOAD_FORMAT_VERSION


@dataclass(frozen=True, slots=True)
class RustStateProtoChapter:
    chapter_id: int
    text: str
    signature: str


@dataclass(frozen=True, slots=True)
class RustStateProtoTarget:
    id: str
    canonical_name: str
    kind: str = TARGET_KIND_ENTITY
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RustStateProtoBuildRequest:
    format_version: int
    requested_language: str | None
    chapters: tuple[RustStateProtoChapter, ...]
    targets: tuple[RustStateProtoTarget, ...]

    def to_wire(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "requested_language": self.requested_language,
            "chapters": [
                {
                    "chapter_id": chapter.chapter_id,
                    "text": chapter.text,
                    "signature": chapter.signature,
                }
                for chapter in self.chapters
            ],
            "targets": [
                {
                    "id": target.id,
                    "canonical_name": target.canonical_name,
                    "kind": target.kind,
                    "aliases": list(target.aliases),
                }
                for target in self.targets
            ],
        }

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_wire(), ensure_ascii=False).encode("utf-8")

    def to_python_args(
        self,
    ) -> tuple[
        str | None, list[tuple[int, str, str]], list[tuple[str, str, str, list[str]]]
    ]:
        return (
            self.requested_language,
            [
                (chapter.chapter_id, chapter.text, chapter.signature)
                for chapter in self.chapters
            ],
            [
                (
                    target.id,
                    target.canonical_name,
                    target.kind,
                    list(target.aliases),
                )
                for target in self.targets
            ],
        )


@dataclass(frozen=True, slots=True)
class RustStateProtoUpdatePlan:
    mode: str
    supported_incremental: bool
    existing_payload_compatible: bool
    target_catalog_changed: bool
    dirty_chapter_ids: tuple[int, ...]
    fallback_reason: str | None = None
    no_changes: bool = False

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> "RustStateProtoUpdatePlan":
        return cls(
            mode=str(data.get("mode") or "full"),
            supported_incremental=bool(data.get("supported_incremental")),
            existing_payload_compatible=bool(data.get("existing_payload_compatible")),
            target_catalog_changed=bool(data.get("target_catalog_changed")),
            dirty_chapter_ids=tuple(
                int(value) for value in data.get("dirty_chapter_ids") or ()
            ),
            fallback_reason=(
                None
                if data.get("fallback_reason") in (None, "")
                else str(data["fallback_reason"])
            ),
            no_changes=bool(data.get("no_changes")),
        )


@dataclass(frozen=True, slots=True)
class RustStateProtoAssembleResult:
    payload_bytes: int
    chapter_count: int
    target_count: int
    segment_count: int
    mention_posting_count: int
    claim_atom_count: int
    coverage_rep_count: int
    rebuilt_chapter_count: int
    reused_chapter_count: int
    incremental_applied: bool

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> "RustStateProtoAssembleResult":
        return cls(
            payload_bytes=int(data["payload_bytes"]),
            chapter_count=int(data["chapter_count"]),
            target_count=int(data["target_count"]),
            segment_count=int(data["segment_count"]),
            mention_posting_count=int(data["mention_posting_count"]),
            claim_atom_count=int(data["claim_atom_count"]),
            coverage_rep_count=int(data["coverage_rep_count"]),
            rebuilt_chapter_count=int(data["rebuilt_chapter_count"]),
            reused_chapter_count=int(data["reused_chapter_count"]),
            incremental_applied=bool(data["incremental_applied"]),
        )


@dataclass(frozen=True, slots=True)
class RustStateProtoBuildResult:
    payload_bytes: int
    chapter_count: int
    chapter_chars: int
    target_count: int
    segment_count: int
    mention_posting_count: int
    claim_atom_count: int
    coverage_rep_count: int
    segmentation_ms: float
    mention_ms: float
    claim_ms: float
    coverage_ms: float
    serialize_ms: float
    duration_ms: float
    plan_mode: str
    incremental_applied: bool
    rebuilt_chapter_count: int
    reused_chapter_count: int
    fallback_reason: str | None = None

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> "RustStateProtoBuildResult":
        return cls(
            payload_bytes=int(data["payload_bytes"]),
            chapter_count=int(data["chapter_count"]),
            chapter_chars=int(data.get("chapter_chars") or 0),
            target_count=int(data["target_count"]),
            segment_count=int(data["segment_count"]),
            mention_posting_count=int(data["mention_posting_count"]),
            claim_atom_count=int(data["claim_atom_count"]),
            coverage_rep_count=int(data["coverage_rep_count"]),
            segmentation_ms=float(data.get("segmentation_ms") or 0.0),
            mention_ms=float(data.get("mention_ms") or 0.0),
            claim_ms=float(data.get("claim_ms") or 0.0),
            coverage_ms=float(data.get("coverage_ms") or 0.0),
            serialize_ms=float(data.get("serialize_ms") or 0.0),
            duration_ms=float(data.get("duration_ms") or 0.0),
            plan_mode=str(data.get("plan_mode") or "full"),
            incremental_applied=bool(data.get("incremental_applied")),
            rebuilt_chapter_count=int(data.get("rebuilt_chapter_count") or 0),
            reused_chapter_count=int(data.get("reused_chapter_count") or 0),
            fallback_reason=(
                None
                if data.get("fallback_reason") in (None, "")
                else str(data["fallback_reason"])
            ),
        )


def rust_state_proto_payload_format_version() -> int:
    rust_module = get_rust_state_proto_module()
    if rust_module is None:
        return RUST_STATE_PROTO_BUILD_REQUEST_FORMAT_VERSION
    return int(rust_module.payload_format_version())


def build_rust_state_proto_request(
    *,
    chapters: Sequence[ChapterText],
    target_specs: Sequence[TargetSpec],
    novel_language: str | None,
) -> RustStateProtoBuildRequest:
    return RustStateProtoBuildRequest(
        format_version=RUST_STATE_PROTO_BUILD_REQUEST_FORMAT_VERSION,
        requested_language=novel_language,
        chapters=tuple(
            RustStateProtoChapter(
                chapter_id=int(chapter.chapter_id),
                text=chapter.text or "",
                signature=compute_state_proto_chapter_signature(chapter.text or ""),
            )
            for chapter in chapters
        ),
        targets=tuple(
            RustStateProtoTarget(
                id=target.id,
                canonical_name=target.canonical_name,
                kind=target.kind,
                aliases=tuple(target.aliases),
            )
            for target in target_specs
        ),
    )


def _load_json_bytes(data: bytes) -> dict[str, Any]:
    return json.loads(data.decode("utf-8"))


def _require_rust_state_proto_module():
    rust_module = get_rust_state_proto_module()
    if rust_module is None:
        raise RuntimeError("Rust state-proto module is unavailable")
    return rust_module


def plan_rust_state_proto_update(
    *,
    existing_payload: bytes | None,
    request: RustStateProtoBuildRequest,
) -> RustStateProtoUpdatePlan:
    rust_module = get_rust_state_proto_module()
    if rust_module is None:
        return RustStateProtoUpdatePlan(
            mode="full",
            supported_incremental=False,
            existing_payload_compatible=False,
            target_catalog_changed=False,
            dirty_chapter_ids=tuple(chapter.chapter_id for chapter in request.chapters),
            fallback_reason="rust_module_unavailable",
        )
    requested_language, chapters, targets = request.to_python_args()
    raw = rust_module.plan_update(
        existing_payload,
        requested_language,
        chapters,
        targets,
    )
    return RustStateProtoUpdatePlan.from_wire(dict(raw))


def assemble_rust_state_proto_payload(
    *,
    request: RustStateProtoBuildRequest,
    chapter_shards: Sequence[dict[str, Any]],
    existing_payload: bytes | None,
) -> tuple[bytes, RustStateProtoAssembleResult]:
    rust_module = _require_rust_state_proto_module()
    result = rust_module.assemble_payload(
        request.to_json_bytes(),
        json.dumps(list(chapter_shards), ensure_ascii=False).encode("utf-8"),
        existing_payload,
    )
    payload_bytes = bytes(result[0])
    assemble = RustStateProtoAssembleResult.from_wire(
        _load_json_bytes(bytes(result[1]))
    )
    return payload_bytes, assemble


def build_rust_state_proto_full(
    *,
    request: RustStateProtoBuildRequest,
) -> tuple[bytes, RustStateProtoBuildResult]:
    rust_module = _require_rust_state_proto_module()
    requested_language, chapters, targets = request.to_python_args()
    result = rust_module.build_full_structured(
        requested_language,
        chapters,
        targets,
    )
    payload_bytes = bytes(result[0])
    build = RustStateProtoBuildResult.from_wire(dict(result[1]))
    return payload_bytes, build


def update_rust_state_proto_incremental(
    *,
    existing_payload: bytes,
    request: RustStateProtoBuildRequest,
) -> tuple[bytes, RustStateProtoBuildResult]:
    rust_module = _require_rust_state_proto_module()
    requested_language, chapters, targets = request.to_python_args()
    result = rust_module.update_incremental_structured(
        existing_payload,
        requested_language,
        chapters,
        targets,
    )
    payload_bytes = bytes(result[0])
    build = RustStateProtoBuildResult.from_wire(dict(result[1]))
    return payload_bytes, build
