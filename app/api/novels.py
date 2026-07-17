# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from fastapi import APIRouter

from .novel_chapters import router as novel_chapter_router
from .novel_continuations import router as novel_continuation_router
from .novel_status import router as novel_status_router
from .novel_uploads import router as novel_upload_router

router = APIRouter()
router.include_router(novel_upload_router)
router.include_router(novel_status_router)
router.include_router(novel_chapter_router)
router.include_router(novel_continuation_router)
