# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

try:
    import msgpack
except ImportError:  # pragma: no cover - fallback for environments without msgpack
    msgpack = None


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WindowRef":
        return cls(
            window_id=int(data["window_id"]),
            chapter_id=int(data["chapter_id"]),
            start_pos=int(data["start_pos"]),
            end_pos=int(data["end_pos"]),
            entity_count=int(data["entity_count"]),
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

    def to_msgpack(self) -> bytes:
        payload = {
            "entity_windows": {
                name: [window.to_dict() for window in windows]
                for name, windows in self.entity_windows.items()
            },
            "window_entities": {
                str(window_id): sorted(entities)
                for window_id, entities in self.window_entities.items()
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

        entity_windows = {
            str(name): [WindowRef.from_dict(window) for window in windows]
            for name, windows in payload.get("entity_windows", {}).items()
        }
        window_entities = {
            int(window_id): set(entities)
            for window_id, entities in payload.get("window_entities", {}).items()
        }
        return cls(entity_windows=entity_windows, window_entities=window_entities)
