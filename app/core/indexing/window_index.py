# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

try:
    import msgpack
except ImportError:  # pragma: no cover - fallback for environments without msgpack
    msgpack = None


WINDOW_INDEX_COMPACT_FORMAT_VERSION = 2


@dataclass(slots=True)
class WindowRef:
    window_id: int
    chapter_id: int
    start_pos: int
    end_pos: int
    entity_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "window_id": self.window_id,
            "chapter_id": self.chapter_id,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "entity_count": self.entity_count,
        }

    def to_compact(self) -> list[int]:
        return [
            self.window_id,
            self.chapter_id,
            self.start_pos,
            self.end_pos,
            self.entity_count,
        ]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WindowRef":
        return cls(
            window_id=int(data["window_id"]),
            chapter_id=int(data["chapter_id"]),
            start_pos=int(data["start_pos"]),
            end_pos=int(data["end_pos"]),
            entity_count=int(data["entity_count"]),
        )

    @classmethod
    def from_payload(cls, data: Mapping[str, Any] | Sequence[Any]) -> "WindowRef":
        if isinstance(data, Mapping):
            return cls.from_dict(dict(data))
        if not isinstance(data, Sequence) or len(data) != 5:
            raise ValueError(f"Unexpected WindowRef payload: {data!r}")
        return cls(
            window_id=int(data[0]),
            chapter_id=int(data[1]),
            start_pos=int(data[2]),
            end_pos=int(data[3]),
            entity_count=int(data[4]),
        )


@dataclass(slots=True)
class NovelIndex:
    entity_windows: dict[str, list[WindowRef]] = field(default_factory=dict)
    window_entities: dict[int, set[str]] = field(default_factory=dict)

    @staticmethod
    def _sorted_windows(windows: Iterable[WindowRef]) -> list[WindowRef]:
        return sorted(
            windows,
            key=lambda ref: (-ref.entity_count, ref.window_id),
        )

    def find_entity_passages(self, name: str, limit: int = 20) -> list[WindowRef]:
        if limit <= 0:
            return []
        windows = self.entity_windows.get(name, [])
        return self._sorted_windows(windows)[:limit]

    def find_cooccurrence(self, name_a: str, name_b: str, limit: int = 20) -> list[WindowRef]:
        if limit <= 0:
            return []
        windows_a = self.entity_windows.get(name_a, [])
        windows_b_ids = {ref.window_id for ref in self.entity_windows.get(name_b, [])}
        cooccurrence = [ref for ref in windows_a if ref.window_id in windows_b_ids]
        return self._sorted_windows(cooccurrence)[:limit]

    @staticmethod
    def build_window_entities(
        entity_windows: Mapping[str, Iterable[WindowRef]],
    ) -> dict[int, set[str]]:
        window_entities: dict[int, set[str]] = {}
        for entity_name, windows in entity_windows.items():
            for window in windows:
                window_entities.setdefault(int(window.window_id), set()).add(str(entity_name))
        return window_entities

    def to_msgpack(self) -> bytes:
        payload = {
            "v": WINDOW_INDEX_COMPACT_FORMAT_VERSION,
            "e": {
                name: [window.to_compact() for window in windows]
                for name, windows in self.entity_windows.items()
            },
        }
        if msgpack is not None:
            return msgpack.packb(payload, use_bin_type=True)
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_msgpack(cls, data: bytes) -> "NovelIndex":
        if msgpack is not None:
            payload = msgpack.unpackb(data, raw=False)
        else:
            payload = json.loads(data.decode("utf-8"))

        if isinstance(payload, Mapping) and payload.get("kind") == "state_proto":
            from .state_proto_runtime import StateProtoIndex

            return StateProtoIndex.from_payload(payload).to_window_index_compat()

        compact_entity_windows = payload.get("e")
        if isinstance(compact_entity_windows, Mapping):
            entity_windows = {
                str(name): [WindowRef.from_payload(window) for window in windows]
                for name, windows in compact_entity_windows.items()
            }
            raw_window_entities = payload.get("w")
        else:
            entity_windows = {
                str(name): [WindowRef.from_payload(window) for window in windows]
                for name, windows in payload.get("entity_windows", {}).items()
            }
            raw_window_entities = payload.get("window_entities")

        if isinstance(raw_window_entities, Mapping) and raw_window_entities:
            window_entities = {
                int(window_id): set(entities)
                for window_id, entities in raw_window_entities.items()
            }
        else:
            window_entities = cls.build_window_entities(entity_windows)
        return cls(entity_windows=entity_windows, window_entities=window_entities)
