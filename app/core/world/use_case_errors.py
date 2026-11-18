# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Shared exception types for world-model application use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from fastapi import HTTPException


@dataclass(slots=True)
class WorldUseCaseError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class WorldUseCaseDetailError(RuntimeError):
    detail: object
    status_code: int
    headers: Mapping[str, str] | None = None


def detail_error_from_http_exception(exc: HTTPException) -> WorldUseCaseDetailError:
    return WorldUseCaseDetailError(
        detail=exc.detail,
        status_code=exc.status_code,
        headers=exc.headers,
    )
