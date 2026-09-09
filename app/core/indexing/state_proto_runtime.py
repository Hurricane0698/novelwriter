from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any, Callable, Literal, Mapping, Sequence

from app.language_policy import get_language_policy

from .state_proto_model import (
    CUE_ASSERTED,
    CUE_HISTORICAL,
    CUE_HYPOTHETICAL,
    CUE_NEGATED,
    DEFAULT_CJK_OPEN_CHARS,
    DEFAULT_CJK_PREVIEW_CHARS,
    DEFAULT_NON_CJK_OPEN_CHARS,
    DEFAULT_NON_CJK_PREVIEW_CHARS,
    SCRIPT_MODE_CJK_HEAVY,
    SCRIPT_MODE_SPACE_DELIMITED,
    STATE_PROTO_COMPACT_FORMAT_VERSION,
    STATE_PROTO_PAYLOAD_KIND,
    SUPPORTED_CLAIM_SLOTS,
    UNCERTAINTY_AMBIGUOUS_CUE,
    UNCERTAINTY_FRESH_CONFLICT,
    UNCERTAINTY_LOW_MARGIN,
    UNCERTAINTY_SPARSE_TAIL,
    CandidateStatePack,
    ClaimAtom,
    ClaimKey,
    CoverageRepresentative,
    MentionPosting,
    PackProvenance,
    Regime,
    Segment,
    SlotTracePack,
    SlotTraceRegimeRow,
    SourceOpenPayload,
    TargetSpec,
    _CJK_CHAR_RE,
)

try:
    import msgpack
except ImportError:  # pragma: no cover - fallback for environments without msgpack
    msgpack = None


@dataclass
class StateProtoIndex:
    language: str
    targets: dict[str, TargetSpec] = field(default_factory=dict)
    segments: list[Segment] = field(default_factory=list)
    mention_postings: list[MentionPosting] = field(default_factory=list)
    claim_atoms: list[ClaimAtom] = field(default_factory=list)
    coverage_reps: list[CoverageRepresentative] = field(default_factory=list)
    chapter_texts: dict[int, str] = field(default_factory=dict, repr=False, compare=False)
    chapter_text_resolver: Callable[[int], str] | None = field(default=None, repr=False, compare=False)
    _chapter_order: dict[int, int] = field(default_factory=dict, repr=False, compare=False)
    _segments_by_id: dict[int, Segment] = field(default_factory=dict, repr=False, compare=False)
    _segment_text_cache: dict[int, str] = field(default_factory=dict, repr=False, compare=False)
    _claims_by_id: dict[int, ClaimAtom] = field(default_factory=dict, repr=False, compare=False)
    _claims_by_key: dict[ClaimKey, list[ClaimAtom]] = field(default_factory=dict, repr=False, compare=False)
    _coverage_by_target: dict[str, list[CoverageRepresentative]] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._chapter_order = {segment.chapter_id: segment.chapter_number for segment in self.segments}
        self._segments_by_id = {segment.segment_id: segment for segment in self.segments}
        self._claims_by_id = {claim.claim_id: claim for claim in self.claim_atoms}
        grouped_claims: dict[ClaimKey, list[ClaimAtom]] = defaultdict(list)
        for claim in self.claim_atoms:
            grouped_claims[claim.key].append(claim)
        self._claims_by_key = {
            key: sorted(claims, key=lambda item: (item.chapter_number, item.segment_id, item.claim_id))
            for key, claims in grouped_claims.items()
        }
        coverage_by_target: dict[str, list[CoverageRepresentative]] = defaultdict(list)
        for rep in self.coverage_reps:
            coverage_by_target[rep.target_id].append(rep)
        self._coverage_by_target = dict(coverage_by_target)

    def get_segment_text(self, segment_id: int) -> str:
        cached = self._segment_text_cache.get(segment_id)
        if cached is not None:
            return cached
        segment = self._segments_by_id[segment_id]
        chapter_text = self.chapter_texts.get(segment.chapter_id, "")
        if not chapter_text and self.chapter_text_resolver is not None:
            chapter_text = self.chapter_text_resolver(segment.chapter_id) or ""
            if chapter_text:
                self.chapter_texts[segment.chapter_id] = chapter_text
        text = chapter_text[segment.start_pos:segment.end_pos]
        self._segment_text_cache[segment_id] = text
        return text

    def to_msgpack(self) -> bytes:
        grouped_segments: dict[int, list[Segment]] = defaultdict(list)
        grouped_mentions: dict[int, list[MentionPosting]] = defaultdict(list)
        grouped_claims: dict[int, list[ClaimAtom]] = defaultdict(list)
        for segment in self.segments:
            grouped_segments[segment.chapter_id].append(segment)
        segment_chapter_by_id = {
            segment.segment_id: segment.chapter_id
            for segment in self.segments
        }
        for posting in self.mention_postings:
            chapter_id = segment_chapter_by_id.get(posting.segment_id)
            if chapter_id is not None:
                grouped_mentions[chapter_id].append(posting)
        for claim in self.claim_atoms:
            segment = self._segments_by_id.get(claim.segment_id)
            if segment is not None:
                grouped_claims[segment.chapter_id].append(claim)
        payload = {
            "kind": STATE_PROTO_PAYLOAD_KIND,
            "v": STATE_PROTO_COMPACT_FORMAT_VERSION,
            "language": self.language,
            "targets": [
                [target.id, target.kind, target.canonical_name, list(target.aliases)]
                for target in self.targets.values()
            ],
            "chapters": [
                {
                    "chapter_id": chapter_id,
                    "chapter_number": grouped_segments[chapter_id][0].chapter_number
                    if grouped_segments[chapter_id]
                    else self._chapter_order.get(chapter_id, 0),
                    "signature": None,
                    "segments": [segment.to_compact() for segment in grouped_segments[chapter_id]],
                    "mentions": [posting.to_compact() for posting in grouped_mentions.get(chapter_id, ())],
                    "claims": [claim.to_compact() for claim in grouped_claims.get(chapter_id, ())],
                }
                for chapter_id in sorted(
                    grouped_segments,
                    key=lambda value: (
                        self._chapter_order.get(value, 0),
                        value,
                    ),
                )
            ],
            "coverage": [rep.to_compact() for rep in self.coverage_reps],
        }
        if msgpack is not None:
            return msgpack.packb(payload, use_bin_type=True)
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def to_window_index_compat(self):
        from .window_index import NovelIndex, WindowRef

        entity_windows: dict[str, list[WindowRef]] = defaultdict(list)
        seen: set[tuple[str, int]] = set()
        for rep in sorted(self.coverage_reps, key=lambda item: (item.target_id, item.bucket_id)):
            target = self.targets.get(rep.target_id)
            segment = self._segments_by_id.get(rep.segment_id)
            if target is None or segment is None:
                continue
            ref = WindowRef(
                window_id=segment.segment_id,
                chapter_id=segment.chapter_id,
                start_pos=segment.start_pos,
                end_pos=segment.end_pos,
                entity_count=max(1, int(round(rep.rep_score))),
            )
            for alias in target.all_aliases():
                dedupe_key = (alias, ref.window_id)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                entity_windows.setdefault(alias, []).append(ref)

        resolved_entity_windows = {
            name: list(windows)
            for name, windows in entity_windows.items()
        }
        return NovelIndex(
            entity_windows=resolved_entity_windows,
            window_entities=NovelIndex.build_window_entities(resolved_entity_windows),
        )

    @classmethod
    def from_msgpack(
        cls,
        data: bytes,
        *,
        chapter_texts: Mapping[int, str] | None = None,
        chapter_text_resolver: Callable[[int], str] | None = None,
    ) -> "StateProtoIndex":
        if msgpack is not None:
            payload = msgpack.unpackb(data, raw=False)
        else:
            payload = json.loads(data.decode("utf-8"))

        return cls.from_payload(
            payload,
            chapter_texts=chapter_texts,
            chapter_text_resolver=chapter_text_resolver,
        )

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        chapter_texts: Mapping[int, str] | None = None,
        chapter_text_resolver: Callable[[int], str] | None = None,
    ) -> "StateProtoIndex":
        """Build from a decoded payload, including legacy and chapter-sharded formats."""
        targets = {
            str(row[0]): TargetSpec(
                id=str(row[0]),
                kind=str(row[1]),
                canonical_name=str(row[2]),
                aliases=tuple(str(alias) for alias in row[3] or ()),
            )
            for row in payload.get("targets", ())
        }

        segments: list[Segment] = []
        mention_postings: list[MentionPosting] = []
        claim_atoms: list[ClaimAtom] = []
        coverage_reps = [
            CoverageRepresentative(
                target_id=str(row[0]),
                bucket_id=int(row[1]),
                segment_id=int(row[2]),
                rep_score=float(row[3]),
            )
            for row in payload.get("coverage", ())
        ]

        if payload.get("kind") == STATE_PROTO_PAYLOAD_KIND and payload.get("chapters"):
            for chapter_payload in payload.get("chapters", ()):
                segments.extend(
                    Segment(
                        segment_id=int(row[0]),
                        chapter_id=int(row[1]),
                        chapter_number=int(row[2]),
                        start_pos=int(row[3]),
                        end_pos=int(row[4]),
                        progress_bucket=int(row[5]),
                        prev_segment_id=(
                            None if row[6] is None else int(row[6])
                        ),
                        next_segment_id=(
                            None if row[7] is None else int(row[7])
                        ),
                    )
                    for row in chapter_payload.get("segments", ())
                )
                mention_postings.extend(
                    MentionPosting(
                        target_id=str(row[0]),
                        segment_id=int(row[1]),
                        mention_score=float(row[2]),
                        density=float(row[3]),
                        best_anchor_offset=int(row[4]),
                    )
                    for row in chapter_payload.get("mentions", ())
                )
                claim_atoms.extend(
                    ClaimAtom(
                        claim_id=int(row[0]),
                        key=ClaimKey(target_id=str(row[1]), slot=str(row[2])),
                        value_signature=str(row[3]),
                        segment_id=int(row[4]),
                        chapter_number=int(row[5]),
                        anchor_offset=int(row[6]),
                        confidence=float(row[7]),
                        cue_bitmap=int(row[8]),
                        change_salience=float(row[9]),
                    )
                    for row in chapter_payload.get("claims", ())
                )
        else:
            segments = [
                Segment(
                    segment_id=int(row[0]),
                    chapter_id=int(row[1]),
                    chapter_number=int(row[2]),
                    start_pos=int(row[3]),
                    end_pos=int(row[4]),
                    progress_bucket=int(row[5]),
                    prev_segment_id=None if row[6] is None else int(row[6]),
                    next_segment_id=None if row[7] is None else int(row[7]),
                )
                for row in payload.get("segments", ())
            ]
            mention_postings = [
                MentionPosting(
                    target_id=str(row[0]),
                    segment_id=int(row[1]),
                    mention_score=float(row[2]),
                    density=float(row[3]),
                    best_anchor_offset=int(row[4]),
                )
                for row in payload.get("mentions", ())
            ]
            claim_atoms = [
                ClaimAtom(
                    claim_id=int(row[0]),
                    key=ClaimKey(target_id=str(row[1]), slot=str(row[2])),
                    value_signature=str(row[3]),
                    segment_id=int(row[4]),
                    chapter_number=int(row[5]),
                    anchor_offset=int(row[6]),
                    confidence=float(row[7]),
                    cue_bitmap=int(row[8]),
                    change_salience=float(row[9]),
                )
                for row in payload.get("claims", ())
            ]

        return cls(
            language=str(payload.get("language") or "zh"),
            targets=targets,
            segments=segments,
            mention_postings=mention_postings,
            claim_atoms=claim_atoms,
            coverage_reps=coverage_reps,
            chapter_texts=dict(chapter_texts or {}),
            chapter_text_resolver=chapter_text_resolver,
        )

    def find_state(self, target_id: str, slot: str | None = None) -> list[CandidateStatePack]:
        if slot:
            return self._find_state_for_slot(target_id, slot)[:2]

        packs: list[CandidateStatePack] = []
        for supported_slot in SUPPORTED_CLAIM_SLOTS:
            slot_packs = self._find_state_for_slot(target_id, supported_slot)
            if slot_packs:
                packs.append(slot_packs[0])
        packs.sort(
            key=lambda pack: (
                -self._pack_regime(pack).currentness_score,
                pack.slot,
                pack.candidate_value_signature,
            )
        )
        return packs[:3]

    def trace_slot(self, target_id: str, slot: str) -> SlotTracePack:
        key = ClaimKey(target_id=target_id, slot=slot)
        regimes = self._derive_regimes_for_key(key)
        ranked = sorted(regimes, key=self._regime_order_key, reverse=True)
        winner_handle = ranked[0] if ranked else None
        rows: list[SlotTraceRegimeRow] = []
        for idx, regime in enumerate(ranked[:4]):
            start_segment = self._segments_by_id[regime.start_segment_id]
            end_segment = self._segments_by_id[regime.end_segment_id]
            rows.append(
                SlotTraceRegimeRow(
                    regime_handle=self._regime_handle(key.target_id, key.slot, idx),
                    value_signature=regime.value_signature,
                    chapter_from=start_segment.chapter_number,
                    chapter_to=end_segment.chapter_number,
                    support_score=round(regime.support_score, 3),
                    tail_support_score=round(regime.tail_support_score, 3),
                    currentness_score=round(regime.currentness_score, 3),
                    is_current_candidate=winner_handle == regime,
                )
            )
        return SlotTracePack(
            trace_id=self._trace_handle(target_id, slot),
            target_id=target_id,
            slot=slot,
            regimes=tuple(rows),
        )

    def open(self, handle: str) -> SourceOpenPayload | SlotTracePack:
        if handle.startswith("trace::"):
            _, target_id, slot = handle.split("::", 2)
            return self.trace_slot(target_id, slot)
        if not handle.startswith("segment::"):
            raise KeyError(f"Unsupported handle: {handle}")
        segment_id = int(handle.split("::", 1)[1])
        return self._open_segment(segment_id)

    def resolve_pack_provenance(self, pack: CandidateStatePack) -> PackProvenance:
        regime = self._pack_regime(pack)
        primary_claim = self._claims_by_id[regime.rep_claim_ids[-1]]
        segment = self._segments_by_id[primary_claim.segment_id]
        source_payload = self._open_segment(segment.segment_id)
        return PackProvenance(
            pack=pack,
            regime=regime,
            primary_claim=primary_claim,
            segment=segment,
            source_payload=source_payload,
        )

    def estimate_payload_tokens(self, payload: Any) -> int:
        plain = json.dumps(_json_ready(payload), ensure_ascii=False)
        cjk_chars = sum(1 for char in plain if _is_cjk(char))
        latinish = re.findall(r"[A-Za-z0-9_]+", plain)
        punctuation_count = sum(1 for char in plain if not char.isalnum() and not char.isspace() and not _is_cjk(char))
        return cjk_chars + len(latinish) + max(punctuation_count // 4, 1)

    def _find_state_for_slot(self, target_id: str, slot: str) -> list[CandidateStatePack]:
        key = ClaimKey(target_id=target_id, slot=slot)
        regimes = self._derive_regimes_for_key(key)
        if not regimes:
            return []
        ranked = sorted(regimes, key=self._regime_order_key, reverse=True)
        top_two = ranked[:2]
        diff = (
            top_two[0].currentness_score - top_two[1].currentness_score
            if len(top_two) >= 2
            else None
        )
        packs: list[CandidateStatePack] = []
        for idx, regime in enumerate(top_two):
            preview_claim = self._claims_by_id[regime.rep_claim_ids[-1]]
            preview_text = self.get_segment_text(preview_claim.segment_id)
            uncertainty_hint = self._resolve_uncertainty_hint(regime, ranked, score_margin=diff)
            conflict_handle = self._build_conflict_handle(regime, key)
            support_handle = None
            if len(regime.rep_claim_ids) > 1:
                support_handle = self._segment_handle(
                    self._claims_by_id[regime.rep_claim_ids[0]].segment_id
                )
            packs.append(
                CandidateStatePack(
                    pack_id=self._pack_id(target_id, slot, idx),
                    target_id=target_id,
                    slot=slot,
                    candidate_value_signature=regime.value_signature,
                    support_score=round(regime.support_score, 3),
                    tail_support_score=round(regime.tail_support_score, 3),
                    uncertainty_hint=uncertainty_hint,
                    preview_excerpt=_excerpt_around_anchor(
                        preview_text,
                        anchor_offset=preview_claim.anchor_offset,
                        script_mode=_detect_script_mode(preview_text),
                        char_limit=_preview_char_limit(preview_text),
                    ),
                    primary_handle=self._segment_handle(preview_claim.segment_id),
                    support_handle=support_handle,
                    conflict_handle=conflict_handle,
                    trace_handle=self._trace_handle(target_id, slot),
                    source_handle=self._segment_handle(preview_claim.segment_id),
                )
            )
        return packs

    def _derive_regimes_for_key(self, key: ClaimKey) -> list[Regime]:
        claims = self._claims_by_key.get(key, [])
        if not claims:
            return []

        grouped: list[list[ClaimAtom]] = []
        current_group: list[ClaimAtom] = []
        for claim in claims:
            if not current_group:
                current_group = [claim]
                continue
            previous = current_group[-1]
            chapter_gap = claim.chapter_number - previous.chapter_number
            segment_gap = (
                claim.segment_id - previous.segment_id
                if claim.chapter_number == previous.chapter_number
                else 0
            )
            if (
                claim.value_signature != previous.value_signature
                or chapter_gap > 1
                or (chapter_gap == 0 and segment_gap > 4)
            ):
                grouped.append(current_group)
                current_group = [claim]
                continue
            current_group.append(claim)
        if current_group:
            grouped.append(current_group)

        regimes: list[Regime] = []
        latest_index = len(grouped) - 1
        for idx, group in enumerate(grouped):
            weights = [_effective_claim_weight(claim) for claim in group]
            support_score = min(2.5, sum(weights))
            tail_support_score = min(1.5, sum(weights[-2:]))
            later_conflicts = [
                other
                for later_group in grouped[idx + 1 :]
                for other in later_group
                if other.value_signature != group[-1].value_signature
            ]
            conflict_after_score = min(
                2.0,
                sum(_effective_claim_weight(claim) for claim in later_conflicts),
            )
            recency_bonus = 0.0
            if idx == latest_index:
                recency_bonus = 1.0
            elif idx == latest_index - 1:
                latest_end = self._segments_by_id[grouped[latest_index][-1].segment_id]
                current_end = self._segments_by_id[group[-1].segment_id]
                if latest_end.chapter_number - current_end.chapter_number <= 1:
                    recency_bonus = 0.4
            currentness_score = (
                0.55 * tail_support_score
                + 0.30 * recency_bonus
                + 0.15 * support_score
                - 0.60 * conflict_after_score
            )
            rep_claim_ids = _representative_claim_ids(group)
            regimes.append(
                Regime(
                    key=key,
                    value_signature=group[-1].value_signature,
                    claim_lo=group[0].claim_id,
                    claim_hi=group[-1].claim_id,
                    start_segment_id=group[0].segment_id,
                    end_segment_id=group[-1].segment_id,
                    support_score=round(support_score, 4),
                    tail_support_score=round(tail_support_score, 4),
                    latest_support_segment_id=group[-1].segment_id,
                    rep_claim_ids=rep_claim_ids,
                    conflict_after_score=round(conflict_after_score, 4),
                    currentness_score=round(currentness_score, 4),
                    has_asserted_support=any(claim.cue_bitmap & CUE_ASSERTED for claim in group),
                )
            )
        return regimes

    def _resolve_uncertainty_hint(
        self,
        regime: Regime,
        ranked_regimes: Sequence[Regime],
        *,
        score_margin: float | None,
    ) -> str | None:
        if score_margin is not None and score_margin < 0.25 and ranked_regimes and ranked_regimes[0] == regime:
            return UNCERTAINTY_LOW_MARGIN
        if regime.conflict_after_score >= 0.60:
            return UNCERTAINTY_FRESH_CONFLICT
        if regime.tail_support_score < 0.45:
            return UNCERTAINTY_SPARSE_TAIL
        if not regime.has_asserted_support:
            return UNCERTAINTY_AMBIGUOUS_CUE
        return None

    def _pack_regime(self, pack: CandidateStatePack) -> Regime:
        key = ClaimKey(target_id=pack.target_id, slot=pack.slot)
        ranked = sorted(self._derive_regimes_for_key(key), key=self._regime_order_key, reverse=True)
        try:
            rank = int(pack.pack_id.rsplit("::", 1)[1])
        except (IndexError, ValueError):
            rank = 0
        if 0 <= rank < len(ranked):
            return ranked[rank]
        raise KeyError(f"Pack regime not found for {pack.pack_id}")

    def _build_conflict_handle(self, regime: Regime, key: ClaimKey) -> str | None:
        claims = self._claims_by_key.get(key, [])
        for claim in claims:
            if claim.segment_id <= regime.end_segment_id:
                continue
            if claim.value_signature != regime.value_signature:
                return self._segment_handle(claim.segment_id)
        return None

    def _open_segment(self, segment_id: int) -> SourceOpenPayload:
        segment = self._segments_by_id[segment_id]
        chapter_text = self.chapter_texts.get(segment.chapter_id, "")
        if not chapter_text and self.chapter_text_resolver is not None:
            chapter_text = self.chapter_text_resolver(segment.chapter_id) or ""
            if chapter_text:
                self.chapter_texts[segment.chapter_id] = chapter_text
        script_mode = _detect_script_mode(chapter_text)
        text = chapter_text[segment.start_pos:segment.end_pos]
        limit = _open_char_limit(script_mode)
        trimmed = _trim_source_text(text, script_mode=script_mode, char_limit=limit)
        return SourceOpenPayload(
            chapter_id=segment.chapter_id,
            chapter_number=segment.chapter_number,
            start_pos=segment.start_pos,
            end_pos=min(segment.start_pos + len(trimmed), segment.end_pos),
            text=trimmed,
            prev_segment_handle=(
                self._segment_handle(segment.prev_segment_id)
                if segment.prev_segment_id is not None
                else None
            ),
            next_segment_handle=(
                self._segment_handle(segment.next_segment_id)
                if segment.next_segment_id is not None
                else None
            ),
            chapter_handle=None,
        )

    @staticmethod
    def _regime_order_key(regime: Regime) -> tuple[float, int, int]:
        return (
            regime.currentness_score,
            regime.end_segment_id,
            regime.claim_hi,
        )

    @staticmethod
    def _pack_id(target_id: str, slot: str, rank: int) -> str:
        return f"pack::{target_id}::{slot}::{rank}"

    @staticmethod
    def _trace_handle(target_id: str, slot: str) -> str:
        return f"trace::{target_id}::{slot}"

    @staticmethod
    def _segment_handle(segment_id: int | None) -> str | None:
        if segment_id is None:
            return None
        return f"segment::{segment_id}"

    @staticmethod
    def _regime_handle(target_id: str, slot: str, rank: int) -> str:
        return f"regime::{target_id}::{slot}::{rank}"

def _detect_script_mode(text: str) -> Literal["cjk_heavy", "space_delimited"]:
    non_whitespace = [char for char in text if not char.isspace()]
    if not non_whitespace:
        return SCRIPT_MODE_SPACE_DELIMITED
    cjk_count = sum(1 for char in non_whitespace if _is_cjk(char))
    if cjk_count / max(len(non_whitespace), 1) >= 0.30:
        return SCRIPT_MODE_CJK_HEAVY
    return SCRIPT_MODE_SPACE_DELIMITED


def _is_cjk(char: str) -> bool:
    return bool(_CJK_CHAR_RE.match(char))


def _preview_char_limit(text: str) -> int:
    return (
        DEFAULT_CJK_PREVIEW_CHARS
        if _detect_script_mode(text) == SCRIPT_MODE_CJK_HEAVY
        else DEFAULT_NON_CJK_PREVIEW_CHARS
    )


def _open_char_limit(script_mode: str) -> int:
    return (
        DEFAULT_CJK_OPEN_CHARS
        if script_mode == SCRIPT_MODE_CJK_HEAVY
        else DEFAULT_NON_CJK_OPEN_CHARS
    )


def _trim_source_text(text: str, *, script_mode: str, char_limit: int) -> str:
    if len(text) <= char_limit:
        return text
    policy = get_language_policy("zh" if script_mode == SCRIPT_MODE_CJK_HEAVY else "en")
    return policy.trim_to_sentence_boundary(text, char_limit)


def _excerpt_around_anchor(
    text: str,
    *,
    anchor_offset: int,
    script_mode: str,
    char_limit: int,
) -> str:
    if not text:
        return ""
    if len(text) <= char_limit:
        return text.strip()
    half = max(char_limit // 2, 1)
    start = max(anchor_offset - half, 0)
    end = min(start + char_limit, len(text))
    excerpt = text[start:end].strip()
    if len(excerpt) <= char_limit:
        return excerpt
    return _trim_source_text(excerpt, script_mode=script_mode, char_limit=char_limit)



def _effective_claim_weight(claim: ClaimAtom) -> float:
    multiplier = 1.0
    if claim.cue_bitmap & CUE_HISTORICAL:
        multiplier = min(multiplier, 0.50)
    if claim.cue_bitmap & CUE_HYPOTHETICAL:
        multiplier = min(multiplier, 0.35)
    if claim.cue_bitmap & CUE_NEGATED:
        multiplier = min(multiplier, 0.20)
    return multiplier * claim.confidence


def _representative_claim_ids(claims: Sequence[ClaimAtom]) -> tuple[int, ...]:
    if not claims:
        return ()
    if len(claims) <= 3:
        return tuple(claim.claim_id for claim in claims)
    middle = claims[len(claims) // 2]
    return (claims[0].claim_id, middle.claim_id, claims[-1].claim_id)



def _json_ready(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_ready(val) for key, val in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json_ready(val) for key, val in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(item) for item in value]
