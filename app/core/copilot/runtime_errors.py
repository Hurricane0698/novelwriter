# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Shared error types for copilot runtime modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CopilotError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class RunLeaseLostError(RuntimeError):
    """Raised when a worker no longer owns the run lease."""
