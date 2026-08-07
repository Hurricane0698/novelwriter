from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.ai_client import AIClient
from app.core.auth import get_current_user_or_default
from app.core.llm_config import ResolvedLlmConfig
from app.core.llm_request import get_llm_config
from app.database import get_db
from app.models import Chapter, NovelOutline, User
from app.schemas import NovelOutlineCreateRequest, NovelOutlineResponse

from . import novel_support

router = APIRouter(prefix="/api/novels/{novel_id}/outlines", tags=["novel-outlines"])


def _range_text(db: Session, novel_id: int, start: int, end: int) -> str:
    chapters = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel_id, Chapter.chapter_number >= start, Chapter.chapter_number <= end)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )
    if not chapters:
        raise HTTPException(status_code=400, detail="Selected chapter range has no content")
    # Keep the request bounded while preserving every chapter boundary.
    chunks = []
    total = 0
    for chapter in chapters:
        body = chapter.content or ""
        if len(body) > 12000:
            body = body[:12000] + "\n[本章正文较长，后文省略]"
        chunk = f"\n### 第{chapter.chapter_number}章：{chapter.title or ''}\n{body}\n"
        if total + len(chunk) > 900000:
            chunks.append("\n[后续章节正文因请求长度限制省略，请根据已提供章节和章节标题概括整体走向。]\n")
            break
        chunks.append(chunk)
        total += len(chunk)
    return "".join(chunks)


@router.get("", response_model=list[NovelOutlineResponse])
def list_outlines(
    novel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel_support.get_accessible_novel(db, novel_id, current_user)
    return db.query(NovelOutline).filter(NovelOutline.novel_id == novel_id).order_by(
        NovelOutline.start_chapter.asc(), NovelOutline.end_chapter.asc(), NovelOutline.created_at.desc()
    ).all()


@router.post("", response_model=NovelOutlineResponse)
async def create_outline(
    novel_id: int,
    req: NovelOutlineCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
    llm_config: ResolvedLlmConfig = Depends(get_llm_config),
):
    novel = novel_support.get_accessible_novel(db, novel_id, current_user)
    if req.start_chapter > req.end_chapter:
        raise HTTPException(status_code=400, detail="start_chapter must not exceed end_chapter")
    total = max(1, int(novel.total_chapters or 0))
    if req.end_chapter > total:
        raise HTTPException(status_code=400, detail=f"Chapter range must be within 1-{total}")

    source = _range_text(db, novel_id, req.start_chapter, req.end_chapter)
    prompt = f"""请总结小说《{novel.title}》第{req.start_chapter}章到第{req.end_chapter}章的剧情大纲。
这是用户手动指定的范围，不要改成原作者的其他分段，也不要补写不存在的内容。
请用中文输出结构清晰的纯文本大纲，包含：主要事件与因果、人物状态变化、重要线索/伏笔、世界观信息、范围结尾时的未解决问题。
不要写续写正文，不要输出JSON，不要添加无法从材料确认的设定。

正文材料：
{source}"""
    content = await AIClient().generate(
        prompt,
        llm_config=llm_config,
        system_prompt="你是严谨的小说剧情编辑，只根据提供的正文做准确总结。",
        max_tokens=12000,
        temperature=0.2,
        user_id=current_user.id,
    )
    if not content.strip():
        raise HTTPException(status_code=502, detail="Outline generation returned empty content")
    row = NovelOutline(
        novel_id=novel_id,
        start_chapter=req.start_chapter,
        end_chapter=req.end_chapter,
        title=f"第{req.start_chapter}—{req.end_chapter}章剧情大纲",
        content=content.strip(),
        model=llm_config.model,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{outline_id}")
def delete_outline(
    novel_id: int,
    outline_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
):
    novel_support.get_accessible_novel(db, novel_id, current_user)
    row = db.query(NovelOutline).filter(NovelOutline.id == outline_id, NovelOutline.novel_id == novel_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Outline not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": outline_id}
