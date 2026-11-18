# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Registry-based runtime copy for copilot user-facing text.

This is intentionally narrower than the global prompt/snippet catalogs:
it covers the small runtime/trace/status strings that used to live inline in
module-local locale branches across copilot runtime seams.
"""

from __future__ import annotations

from enum import Enum

from app.language import DEFAULT_LANGUAGE, get_language_fallback_chain


class CopilotTextKey(str, Enum):
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    RUN_FAILED = "run_failed"
    RUN_INTERRUPTED = "run_interrupted"
    RUN_RESEARCHING = "run_researching"

    TEXT_DESCRIPTION_LABEL = "text_description_label"
    TEXT_ATTRIBUTES_LABEL = "text_attributes_label"
    TEXT_CONSTRAINTS_LABEL = "text_constraints_label"
    TEXT_NO_DESCRIPTION = "text_no_description"
    TEXT_RESOURCE_ENTITY = "text_resource_entity"
    TEXT_RESOURCE_RELATIONSHIP = "text_resource_relationship"
    TEXT_RESOURCE_SYSTEM = "text_resource_system"
    TEXT_NEW_RESOURCE = "text_new_resource"
    TEXT_FIELD_NAME = "text_field_name"
    TEXT_FIELD_ENTITY_TYPE = "text_field_entity_type"
    TEXT_FIELD_DESCRIPTION = "text_field_description"
    TEXT_FIELD_ALIASES = "text_field_aliases"
    TEXT_FIELD_RELATIONSHIP_LABEL = "text_field_relationship_label"
    TEXT_FIELD_VISIBILITY = "text_field_visibility"
    TEXT_FIELD_CONSTRAINTS = "text_field_constraints"
    TEXT_FIELD_DISPLAY_TYPE = "text_field_display_type"
    TEXT_ATTRIBUTE_FIELD_LABEL = "text_attribute_field_label"

    TRACE_EMPTY_QUERY = "trace_empty_query"
    TRACE_RETRIEVAL_STEP_INCOMPLETE = "trace_retrieval_step_incomplete"
    TRACE_FIND = "trace_find"
    TRACE_FIND_SCOPE_SUFFIX = "trace_find_scope_suffix"
    TRACE_FIND_TOTAL_SUFFIX = "trace_find_total_suffix"
    TRACE_OPEN = "trace_open"
    TRACE_OPEN_SOURCE_SUFFIX = "trace_open_source_suffix"
    TRACE_READ_TARGETS = "trace_read_targets"
    TRACE_READ_RESULTS_SUFFIX = "trace_read_results_suffix"
    TRACE_REFRESH_SNAPSHOT = "trace_refresh_snapshot"
    TRACE_REFRESH_ENTITIES = "trace_refresh_entities"
    TRACE_REFRESH_RELATIONSHIPS = "trace_refresh_relationships"
    TRACE_REFRESH_DRAFTS = "trace_refresh_drafts"
    TRACE_REFRESH_COUNTS_SUFFIX = "trace_refresh_counts_suffix"
    TRACE_REFRESH_CONTEXT_REFRESHED_SUFFIX = "trace_refresh_context_refreshed_suffix"
    TRACE_GENERIC_TOOL_COMPLETED = "trace_generic_tool_completed"

    TRACE_TOOL_MODE_USED_STEPS = "trace_tool_mode_used_steps"
    TRACE_TOOL_MODE_DIRECT = "trace_tool_mode_direct"
    TRACE_TOOL_COMPLETED_FALLBACK = "trace_tool_completed_fallback"
    TRACE_ANALYZE_RUNNING = "trace_analyze_running"
    TRACE_TOOL_LOOP_COMPLETED = "trace_tool_loop_completed"
    TRACE_ONE_SHOT_UNSUPPORTED = "trace_one_shot_unsupported"
    TRACE_ONE_SHOT_FAILED = "trace_one_shot_failed"
    TRACE_EVIDENCE_PREPARED = "trace_evidence_prepared"
    TRACE_ANALYSIS_COMPLETED = "trace_analysis_completed"

    SCOPE_CHAPTER_WINDOW_TITLE = "scope_chapter_window_title"
    SCOPE_CHAPTER_TAIL_TITLE = "scope_chapter_tail_title"
    SCOPE_CHAPTER_MENTIONS_ENTITY = "scope_chapter_mentions_entity"
    SCOPE_RECENT_CHAPTER_CONTEXT = "scope_recent_chapter_context"
    SCOPE_STALE_RECENT_CHAPTER_CONTEXT = "scope_stale_recent_chapter_context"
    SCOPE_MISSING_RECENT_CHAPTER_CONTEXT = "scope_missing_recent_chapter_context"
    SCOPE_FAILED_RECENT_CHAPTER_CONTEXT = "scope_failed_recent_chapter_context"
    SCOPE_ENTITY_TITLE = "scope_entity_title"
    SCOPE_ENTITY_TARGET_REASON = "scope_entity_target_reason"
    SCOPE_RELATIONSHIP_EXCERPT = "scope_relationship_excerpt"
    SCOPE_RELATIONSHIP_TARGET_REASON = "scope_relationship_target_reason"
    SCOPE_DRAFT_ENTITY_EXCERPT = "scope_draft_entity_excerpt"
    SCOPE_DRAFT_ENTITY_TITLE = "scope_draft_entity_title"
    SCOPE_DRAFT_ENTITY_REASON = "scope_draft_entity_reason"
    SCOPE_DRAFT_RELATIONSHIP_EXCERPT = "scope_draft_relationship_excerpt"
    SCOPE_DRAFT_RELATIONSHIP_TITLE = "scope_draft_relationship_title"
    SCOPE_DRAFT_RELATIONSHIP_REASON = "scope_draft_relationship_reason"
    SCOPE_DRAFT_SYSTEM_EXCERPT = "scope_draft_system_excerpt"
    SCOPE_DRAFT_SYSTEM_TITLE = "scope_draft_system_title"
    SCOPE_DRAFT_SYSTEM_REASON = "scope_draft_system_reason"

    TOOL_UNKNOWN_TOOL = "tool_unknown_tool"
    TOOL_UNKNOWN_PACK = "tool_unknown_pack"
    TOOL_OPEN_MANY_NO_PACKS = "tool_open_many_no_packs"
    TOOL_OPEN_MANY_TOO_MANY_PACKS = "tool_open_many_too_many_packs"
    TOOL_OPEN_MANY_FAILED_COUNT = "tool_open_many_failed_count"
    TOOL_ISSUE_MISSING_DESCRIPTION = "tool_issue_missing_description"
    TOOL_ISSUE_NO_ALIASES = "tool_issue_no_aliases"
    TOOL_ISSUE_NO_ATTRIBUTES = "tool_issue_no_attributes"
    TOOL_ISSUE_NO_CONSTRAINTS = "tool_issue_no_constraints"
    TOOL_DRAFT_ENTITY_ISSUES_EXCERPT = "tool_draft_entity_issues_excerpt"
    TOOL_DRAFT_RELATIONSHIP_MISSING_DESCRIPTION_EXCERPT = "tool_draft_relationship_missing_description_excerpt"
    TOOL_DRAFT_SYSTEM_ISSUES_EXCERPT = "tool_draft_system_issues_excerpt"

    SUGGESTION_SYNTH_ENTITY_TITLE = "suggestion_synth_entity_title"
    SUGGESTION_SYNTH_ENTITY_SUMMARY = "suggestion_synth_entity_summary"
    SUGGESTION_FALLBACK_TITLE = "suggestion_fallback_title"
    SUGGESTION_REASON_STALE = "suggestion_reason_stale"
    SUGGESTION_REASON_DRAFT_ONLY = "suggestion_reason_draft_only"
    SUGGESTION_REASON_CANNOT_APPLY_DIRECT = "suggestion_reason_cannot_apply_direct"
    SUGGESTION_REASON_DRAFT_CREATE_DISALLOWED = "suggestion_reason_draft_create_disallowed"
    SUGGESTION_REASON_NOT_DIRECTLY_APPLICABLE = "suggestion_reason_not_directly_applicable"
    SUGGESTION_CREATE_REASON_ENTITY_INCOMPLETE = "suggestion_create_reason_entity_incomplete"
    SUGGESTION_CREATE_REASON_ENTITY_NAME_COLLISION = "suggestion_create_reason_entity_name_collision"
    SUGGESTION_CREATE_REASON_RELATIONSHIP_INCOMPLETE = "suggestion_create_reason_relationship_incomplete"
    SUGGESTION_CREATE_REASON_RELATIONSHIP_DEPENDENCY = "suggestion_create_reason_relationship_dependency"
    SUGGESTION_CREATE_REASON_RELATIONSHIP_CONFLICT = "suggestion_create_reason_relationship_conflict"
    SUGGESTION_CREATE_REASON_SYSTEM_INCOMPLETE = "suggestion_create_reason_system_incomplete"
    SUGGESTION_CREATE_REASON_SYSTEM_NAME_COLLISION = "suggestion_create_reason_system_name_collision"

    APPLY_ERROR_SUGGESTION_NOT_FOUND = "apply_error_suggestion_not_found"
    APPLY_ERROR_ALREADY_APPLIED = "apply_error_already_applied"
    APPLY_ERROR_STALE = "apply_error_stale"
    APPLY_ERROR_DEPENDENCY_FAILED = "apply_error_dependency_failed"
    APPLY_ERROR_GENERIC = "apply_error_generic"

    WORKSPACE_EVIDENCE_COMPILED = "workspace_evidence_compiled"
    WORKSPACE_EVIDENCE_COMPILED_MULTIPLE = "workspace_evidence_compiled_multiple"


_MESSAGES: dict[str, dict[CopilotTextKey, str]] = {}


def register_copilot_messages(locale: str, messages: dict[CopilotTextKey, str]) -> None:
    if locale not in _MESSAGES:
        _MESSAGES[locale] = {}
    _MESSAGES[locale].update(messages)


def get_copilot_text(
    text_key: CopilotTextKey,
    *,
    locale: str | None = None,
    **params: object,
) -> str:
    for candidate in get_language_fallback_chain(locale, default=DEFAULT_LANGUAGE):
        bucket = _MESSAGES.get(candidate)
        if bucket and text_key in bucket:
            return bucket[text_key].format(**params)
    raise KeyError(f"No copilot runtime text for {text_key!r} (locale={locale or DEFAULT_LANGUAGE!r})")


_ZH: dict[CopilotTextKey, str] = {
    CopilotTextKey.INVALID_MODEL_OUTPUT: "模型返回的审读结果格式不完整。可以缩短选段，或在设置中切换模型后再试。",
    CopilotTextKey.RUN_FAILED: "Copilot 本轮运行失败，请稍后重试。",
    CopilotTextKey.RUN_INTERRUPTED: "本轮 Copilot 失去了后台活跃租约，请稍后重试。",
    CopilotTextKey.RUN_RESEARCHING: "正在研究，等待模型决定是否调用工具...",

    CopilotTextKey.TEXT_DESCRIPTION_LABEL: "描述",
    CopilotTextKey.TEXT_ATTRIBUTES_LABEL: "属性",
    CopilotTextKey.TEXT_CONSTRAINTS_LABEL: "约束",
    CopilotTextKey.TEXT_NO_DESCRIPTION: "(无描述)",
    CopilotTextKey.TEXT_RESOURCE_ENTITY: "实体",
    CopilotTextKey.TEXT_RESOURCE_RELATIONSHIP: "关系",
    CopilotTextKey.TEXT_RESOURCE_SYSTEM: "体系",
    CopilotTextKey.TEXT_NEW_RESOURCE: "新{resource_label}",
    CopilotTextKey.TEXT_FIELD_NAME: "名称",
    CopilotTextKey.TEXT_FIELD_ENTITY_TYPE: "类型",
    CopilotTextKey.TEXT_FIELD_DESCRIPTION: "描述",
    CopilotTextKey.TEXT_FIELD_ALIASES: "别名",
    CopilotTextKey.TEXT_FIELD_RELATIONSHIP_LABEL: "关系标签",
    CopilotTextKey.TEXT_FIELD_VISIBILITY: "可见性",
    CopilotTextKey.TEXT_FIELD_CONSTRAINTS: "约束",
    CopilotTextKey.TEXT_FIELD_DISPLAY_TYPE: "展示类型",
    CopilotTextKey.TEXT_ATTRIBUTE_FIELD_LABEL: "属性 · {key}",

    CopilotTextKey.TRACE_EMPTY_QUERY: "（空查询）",
    CopilotTextKey.TRACE_RETRIEVAL_STEP_INCOMPLETE: "检索步骤未完成：{error}",
    CopilotTextKey.TRACE_FIND: "搜索「{query}」",
    CopilotTextKey.TRACE_FIND_SCOPE_SUFFIX: "（范围：{scope}）",
    CopilotTextKey.TRACE_FIND_TOTAL_SUFFIX: "，找到 {count} 组相关线索",
    CopilotTextKey.TRACE_OPEN: "展开更多上下文",
    CopilotTextKey.TRACE_OPEN_SOURCE_SUFFIX: "，补充了 {count} 条来源",
    CopilotTextKey.TRACE_READ_TARGETS: "读取 {count} 个设定目标",
    CopilotTextKey.TRACE_READ_RESULTS_SUFFIX: "，返回 {count} 条结果",
    CopilotTextKey.TRACE_REFRESH_SNAPSHOT: "刷新当前设定快照",
    CopilotTextKey.TRACE_REFRESH_ENTITIES: "实体 {count}",
    CopilotTextKey.TRACE_REFRESH_RELATIONSHIPS: "关系 {count}",
    CopilotTextKey.TRACE_REFRESH_DRAFTS: "草稿 {count}",
    CopilotTextKey.TRACE_REFRESH_COUNTS_SUFFIX: "，{counts}",
    CopilotTextKey.TRACE_REFRESH_CONTEXT_REFRESHED_SUFFIX: "：已刷新上下文",
    CopilotTextKey.TRACE_GENERIC_TOOL_COMPLETED: "检索步骤「{tool_name}」已执行",

    CopilotTextKey.TRACE_TOOL_MODE_USED_STEPS: "本轮通过分步检索整理信息，共执行 {count} 步",
    CopilotTextKey.TRACE_TOOL_MODE_DIRECT: "本轮未追加检索步骤，模型直接完成分析",
    CopilotTextKey.TRACE_TOOL_COMPLETED_FALLBACK: "工具 {tool_name}：已执行",
    CopilotTextKey.TRACE_ANALYZE_RUNNING: "正在整理检索结果并生成回答...",
    CopilotTextKey.TRACE_TOOL_LOOP_COMPLETED: "本轮工具研究已完成",
    CopilotTextKey.TRACE_ONE_SHOT_UNSUPPORTED: "当前模型不支持分步检索，已切换为直接分析",
    CopilotTextKey.TRACE_ONE_SHOT_FAILED: "分步检索异常（{reason}），已切换为直接分析",
    CopilotTextKey.TRACE_EVIDENCE_PREPARED: "整理出 {count} 条可展示依据",
    CopilotTextKey.TRACE_ANALYSIS_COMPLETED: "分析完成，生成 {count} 条建议",

    CopilotTextKey.SCOPE_CHAPTER_WINDOW_TITLE: "第{chapter_number}章 · 位置{start}-{end}",
    CopilotTextKey.SCOPE_CHAPTER_TAIL_TITLE: "第{chapter_number}章 · 尾部",
    CopilotTextKey.SCOPE_CHAPTER_MENTIONS_ENTITY: "包含对「{entity_name}」的提及",
    CopilotTextKey.SCOPE_RECENT_CHAPTER_CONTEXT: "最近章节上下文",
    CopilotTextKey.SCOPE_STALE_RECENT_CHAPTER_CONTEXT: "章节有更新，先回退到最近章节上下文",
    CopilotTextKey.SCOPE_MISSING_RECENT_CHAPTER_CONTEXT: "全书内容还在准备中，先回退到最近章节上下文",
    CopilotTextKey.SCOPE_FAILED_RECENT_CHAPTER_CONTEXT: "全书内容整理失败，先回退到最近章节上下文",
    CopilotTextKey.SCOPE_ENTITY_TITLE: "实体 · {entity_name}",
    CopilotTextKey.SCOPE_ENTITY_TARGET_REASON: "当前研究目标实体",
    CopilotTextKey.SCOPE_RELATIONSHIP_EXCERPT: "关系: {source_name} → {label} → {target_name}. {description}",
    CopilotTextKey.SCOPE_RELATIONSHIP_TARGET_REASON: "与目标实体相关的已知关系",
    CopilotTextKey.SCOPE_DRAFT_ENTITY_EXCERPT: "[草稿实体] {entity_name} ({entity_type})",
    CopilotTextKey.SCOPE_DRAFT_ENTITY_TITLE: "草稿实体 · {entity_name}",
    CopilotTextKey.SCOPE_DRAFT_ENTITY_REASON: "当前草稿工作集中的实体",
    CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_EXCERPT: "[草稿关系] {source_name} --[{label}]--> {target_name}",
    CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_TITLE: "草稿关系 · {label}",
    CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_REASON: "当前草稿工作集中的关系",
    CopilotTextKey.SCOPE_DRAFT_SYSTEM_EXCERPT: "[草稿体系] {system_name}",
    CopilotTextKey.SCOPE_DRAFT_SYSTEM_TITLE: "草稿体系 · {system_name}",
    CopilotTextKey.SCOPE_DRAFT_SYSTEM_REASON: "当前草稿工作集中的体系",

    CopilotTextKey.TOOL_UNKNOWN_TOOL: "未知工具：{tool_name}",
    CopilotTextKey.TOOL_UNKNOWN_PACK: "未知线索包：{pack_id}。请先调用 find()。",
    CopilotTextKey.TOOL_OPEN_MANY_NO_PACKS: "open_many 至少需要 1 个有效的 pack_id。",
    CopilotTextKey.TOOL_OPEN_MANY_TOO_MANY_PACKS: "open_many 单次最多接受 {max_count} 个不同的 pack_id；请缩小范围后重试。",
    CopilotTextKey.TOOL_OPEN_MANY_FAILED_COUNT: "open_many 未完全成功：{failed_count}/{requested_count} 个 pack_id 打开失败，请检查 results。",
    CopilotTextKey.TOOL_ISSUE_MISSING_DESCRIPTION: "空描述",
    CopilotTextKey.TOOL_ISSUE_NO_ALIASES: "无别名",
    CopilotTextKey.TOOL_ISSUE_NO_ATTRIBUTES: "无属性",
    CopilotTextKey.TOOL_ISSUE_NO_CONSTRAINTS: "无约束",
    CopilotTextKey.TOOL_DRAFT_ENTITY_ISSUES_EXCERPT: "[草稿实体] {entity_name} ({entity_type}) — 问题: {issues}",
    CopilotTextKey.TOOL_DRAFT_RELATIONSHIP_MISSING_DESCRIPTION_EXCERPT: "[草稿关系] {source_name} --[{label}]--> {target_name} — 空描述",
    CopilotTextKey.TOOL_DRAFT_SYSTEM_ISSUES_EXCERPT: "[草稿体系] {system_name} — 问题: {issues}",

    CopilotTextKey.SUGGESTION_SYNTH_ENTITY_TITLE: "补入关联实体「{entity_name}」",
    CopilotTextKey.SUGGESTION_SYNTH_ENTITY_SUMMARY: "为关系建议补入缺失实体「{entity_name}」。",
    CopilotTextKey.SUGGESTION_FALLBACK_TITLE: "建议 {index}",
    CopilotTextKey.SUGGESTION_REASON_STALE: "这条建议对应的内容刚刚发生了变化，请刷新后再试一次。",
    CopilotTextKey.SUGGESTION_REASON_DRAFT_ONLY: "这一步只能直接整理待确认内容，已确认内容请到对应页面编辑。",
    CopilotTextKey.SUGGESTION_REASON_CANNOT_APPLY_DIRECT: "这条建议暂时还不能直接采纳，请换一种方式继续整理。",
    CopilotTextKey.SUGGESTION_REASON_DRAFT_CREATE_DISALLOWED: "这里更适合整理现有待确认内容；新建内容请先回到正常编辑流程。",
    CopilotTextKey.SUGGESTION_REASON_NOT_DIRECTLY_APPLICABLE: "这条建议目前还不能直接采纳。",
    CopilotTextKey.SUGGESTION_CREATE_REASON_ENTITY_INCOMPLETE: "这条实体建议还不完整，暂时不能直接采纳。",
    CopilotTextKey.SUGGESTION_CREATE_REASON_ENTITY_NAME_COLLISION: "这个名字和现有内容太接近了，请先调整后再确认。",
    CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_INCOMPLETE: "这条关系信息还不完整，暂时不能直接采纳。",
    CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_DEPENDENCY: "这条关系还依赖未确认的实体或设定。请先确认相关实体，再来确认这条关系。",
    CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_CONFLICT: "这条关系和现有内容重复或冲突了，暂时不能直接采纳。",
    CopilotTextKey.SUGGESTION_CREATE_REASON_SYSTEM_INCOMPLETE: "这条体系建议还不完整，暂时不能直接采纳。",
    CopilotTextKey.SUGGESTION_CREATE_REASON_SYSTEM_NAME_COLLISION: "这个体系名称和现有内容太接近了，请先调整后再确认。",

    CopilotTextKey.APPLY_ERROR_SUGGESTION_NOT_FOUND: "这条建议已经失效了，请重新生成一次。",
    CopilotTextKey.APPLY_ERROR_ALREADY_APPLIED: "这条建议已经确认过了。",
    CopilotTextKey.APPLY_ERROR_STALE: "这条建议对应的内容刚刚发生了变化，请刷新后再试一次。",
    CopilotTextKey.APPLY_ERROR_DEPENDENCY_FAILED: "这条关系还依赖未确认的实体或设定。请先确认相关实体，再来确认这条关系。",
    CopilotTextKey.APPLY_ERROR_GENERIC: "这次确认没有成功，请稍后再试。",

    CopilotTextKey.WORKSPACE_EVIDENCE_COMPILED: "已从相关线索中整理",
    CopilotTextKey.WORKSPACE_EVIDENCE_COMPILED_MULTIPLE: "已从 {count} 处相关线索中整理",
}

_EN: dict[CopilotTextKey, str] = {
    CopilotTextKey.INVALID_MODEL_OUTPUT: "The model returned an unreadable review. Try a shorter passage or choose another model in Settings.",
    CopilotTextKey.RUN_FAILED: "Copilot run failed. Please try again.",
    CopilotTextKey.RUN_INTERRUPTED: "The copilot run lost its active background lease. Please try again.",
    CopilotTextKey.RUN_RESEARCHING: "Research in progress. Waiting for the model to decide whether tools are needed...",

    CopilotTextKey.TEXT_DESCRIPTION_LABEL: "Description",
    CopilotTextKey.TEXT_ATTRIBUTES_LABEL: "Attributes",
    CopilotTextKey.TEXT_CONSTRAINTS_LABEL: "Constraints",
    CopilotTextKey.TEXT_NO_DESCRIPTION: "(No description)",
    CopilotTextKey.TEXT_RESOURCE_ENTITY: "entity",
    CopilotTextKey.TEXT_RESOURCE_RELATIONSHIP: "relationship",
    CopilotTextKey.TEXT_RESOURCE_SYSTEM: "system",
    CopilotTextKey.TEXT_NEW_RESOURCE: "New {resource_label}",
    CopilotTextKey.TEXT_FIELD_NAME: "Name",
    CopilotTextKey.TEXT_FIELD_ENTITY_TYPE: "Type",
    CopilotTextKey.TEXT_FIELD_DESCRIPTION: "Description",
    CopilotTextKey.TEXT_FIELD_ALIASES: "Aliases",
    CopilotTextKey.TEXT_FIELD_RELATIONSHIP_LABEL: "Relationship label",
    CopilotTextKey.TEXT_FIELD_VISIBILITY: "Visibility",
    CopilotTextKey.TEXT_FIELD_CONSTRAINTS: "Constraints",
    CopilotTextKey.TEXT_FIELD_DISPLAY_TYPE: "Display type",
    CopilotTextKey.TEXT_ATTRIBUTE_FIELD_LABEL: "Attribute · {key}",

    CopilotTextKey.TRACE_EMPTY_QUERY: "(empty query)",
    CopilotTextKey.TRACE_RETRIEVAL_STEP_INCOMPLETE: "Retrieval step did not finish: {error}",
    CopilotTextKey.TRACE_FIND: 'Search "{query}"',
    CopilotTextKey.TRACE_FIND_SCOPE_SUFFIX: " (scope: {scope})",
    CopilotTextKey.TRACE_FIND_TOTAL_SUFFIX: ", found {count} groups of related clues",
    CopilotTextKey.TRACE_OPEN: "Expand more context",
    CopilotTextKey.TRACE_OPEN_SOURCE_SUFFIX: ", added {count} source references",
    CopilotTextKey.TRACE_READ_TARGETS: "Read {count} world targets",
    CopilotTextKey.TRACE_READ_RESULTS_SUFFIX: ", returned {count} results",
    CopilotTextKey.TRACE_REFRESH_SNAPSHOT: "Refresh current world snapshot",
    CopilotTextKey.TRACE_REFRESH_ENTITIES: "entities {count}",
    CopilotTextKey.TRACE_REFRESH_RELATIONSHIPS: "relationships {count}",
    CopilotTextKey.TRACE_REFRESH_DRAFTS: "drafts {count}",
    CopilotTextKey.TRACE_REFRESH_COUNTS_SUFFIX: ", {counts}",
    CopilotTextKey.TRACE_REFRESH_CONTEXT_REFRESHED_SUFFIX: ": context refreshed",
    CopilotTextKey.TRACE_GENERIC_TOOL_COMPLETED: 'The "{tool_name}" retrieval step completed',

    CopilotTextKey.TRACE_TOOL_MODE_USED_STEPS: "This run used {count} retrieval steps",
    CopilotTextKey.TRACE_TOOL_MODE_DIRECT: "No extra retrieval steps were needed; the model completed the analysis directly",
    CopilotTextKey.TRACE_TOOL_COMPLETED_FALLBACK: "Tool {tool_name}: completed",
    CopilotTextKey.TRACE_ANALYZE_RUNNING: "Compiling retrieval results and drafting the answer...",
    CopilotTextKey.TRACE_TOOL_LOOP_COMPLETED: "The tool-based research pass completed",
    CopilotTextKey.TRACE_ONE_SHOT_UNSUPPORTED: "The current model does not support multi-step retrieval, so the run switched to direct analysis",
    CopilotTextKey.TRACE_ONE_SHOT_FAILED: "Multi-step retrieval failed ({reason}), so the run switched to direct analysis",
    CopilotTextKey.TRACE_EVIDENCE_PREPARED: "Prepared {count} evidence items for display",
    CopilotTextKey.TRACE_ANALYSIS_COMPLETED: "Analysis completed with {count} suggestions",

    CopilotTextKey.SCOPE_CHAPTER_WINDOW_TITLE: "Chapter {chapter_number} · Position {start}-{end}",
    CopilotTextKey.SCOPE_CHAPTER_TAIL_TITLE: "Chapter {chapter_number} · Tail",
    CopilotTextKey.SCOPE_CHAPTER_MENTIONS_ENTITY: 'Mentions "{entity_name}"',
    CopilotTextKey.SCOPE_RECENT_CHAPTER_CONTEXT: "Recent chapter context",
    CopilotTextKey.SCOPE_STALE_RECENT_CHAPTER_CONTEXT: "The chapters changed, so the run is temporarily falling back to recent chapter context",
    CopilotTextKey.SCOPE_MISSING_RECENT_CHAPTER_CONTEXT: "Whole-book content is still being prepared, so the run is temporarily falling back to recent chapter context",
    CopilotTextKey.SCOPE_FAILED_RECENT_CHAPTER_CONTEXT: "Whole-book content failed to organize, so the run is temporarily falling back to recent chapter context",
    CopilotTextKey.SCOPE_ENTITY_TITLE: "Entity · {entity_name}",
    CopilotTextKey.SCOPE_ENTITY_TARGET_REASON: "Current research target entity",
    CopilotTextKey.SCOPE_RELATIONSHIP_EXCERPT: "Relationship: {source_name} → {label} → {target_name}. {description}",
    CopilotTextKey.SCOPE_RELATIONSHIP_TARGET_REASON: "Known relationships connected to the target entity",
    CopilotTextKey.SCOPE_DRAFT_ENTITY_EXCERPT: "[Draft entity] {entity_name} ({entity_type})",
    CopilotTextKey.SCOPE_DRAFT_ENTITY_TITLE: "Draft entity · {entity_name}",
    CopilotTextKey.SCOPE_DRAFT_ENTITY_REASON: "Entity from the current draft workset",
    CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_EXCERPT: "[Draft relationship] {source_name} --[{label}]--> {target_name}",
    CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_TITLE: "Draft relationship · {label}",
    CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_REASON: "Relationship from the current draft workset",
    CopilotTextKey.SCOPE_DRAFT_SYSTEM_EXCERPT: "[Draft system] {system_name}",
    CopilotTextKey.SCOPE_DRAFT_SYSTEM_TITLE: "Draft system · {system_name}",
    CopilotTextKey.SCOPE_DRAFT_SYSTEM_REASON: "System from the current draft workset",

    CopilotTextKey.TOOL_UNKNOWN_TOOL: "Unknown tool: {tool_name}",
    CopilotTextKey.TOOL_UNKNOWN_PACK: "Unknown pack_id: {pack_id}. Use find() first.",
    CopilotTextKey.TOOL_OPEN_MANY_NO_PACKS: "open_many requires at least one valid pack_id.",
    CopilotTextKey.TOOL_OPEN_MANY_TOO_MANY_PACKS: "open_many accepts at most {max_count} unique pack_ids per call. Retry with fewer packs.",
    CopilotTextKey.TOOL_OPEN_MANY_FAILED_COUNT: "open_many did not fully succeed: {failed_count}/{requested_count} pack_ids failed to open. Check results.",
    CopilotTextKey.TOOL_ISSUE_MISSING_DESCRIPTION: "Missing description",
    CopilotTextKey.TOOL_ISSUE_NO_ALIASES: "No aliases",
    CopilotTextKey.TOOL_ISSUE_NO_ATTRIBUTES: "No attributes",
    CopilotTextKey.TOOL_ISSUE_NO_CONSTRAINTS: "No constraints",
    CopilotTextKey.TOOL_DRAFT_ENTITY_ISSUES_EXCERPT: "[Draft entity] {entity_name} ({entity_type}) — Issues: {issues}",
    CopilotTextKey.TOOL_DRAFT_RELATIONSHIP_MISSING_DESCRIPTION_EXCERPT: "[Draft relationship] {source_name} --[{label}]--> {target_name} — Missing description",
    CopilotTextKey.TOOL_DRAFT_SYSTEM_ISSUES_EXCERPT: "[Draft system] {system_name} — Issues: {issues}",

    CopilotTextKey.SUGGESTION_SYNTH_ENTITY_TITLE: 'Add related entity "{entity_name}"',
    CopilotTextKey.SUGGESTION_SYNTH_ENTITY_SUMMARY: 'Add the missing entity "{entity_name}" so the relationship suggestion can be applied.',
    CopilotTextKey.SUGGESTION_FALLBACK_TITLE: "Suggestion {index}",
    CopilotTextKey.SUGGESTION_REASON_STALE: "This suggestion is stale because the underlying content just changed. Refresh and try again.",
    CopilotTextKey.SUGGESTION_REASON_DRAFT_ONLY: "This step can only tidy draft content directly. Edit confirmed content from its main page instead.",
    CopilotTextKey.SUGGESTION_REASON_CANNOT_APPLY_DIRECT: "This suggestion cannot be applied directly yet. Please continue with a different edit.",
    CopilotTextKey.SUGGESTION_REASON_DRAFT_CREATE_DISALLOWED: "This workspace is for cleaning up existing draft content. Please return to the normal editing flow to create new items.",
    CopilotTextKey.SUGGESTION_REASON_NOT_DIRECTLY_APPLICABLE: "This suggestion cannot be applied directly right now.",
    CopilotTextKey.SUGGESTION_CREATE_REASON_ENTITY_INCOMPLETE: "This entity suggestion is incomplete and cannot be applied yet.",
    CopilotTextKey.SUGGESTION_CREATE_REASON_ENTITY_NAME_COLLISION: "This name is too close to existing content. Adjust it before applying.",
    CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_INCOMPLETE: "This relationship suggestion is incomplete and cannot be applied yet.",
    CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_DEPENDENCY: "This relationship still depends on unconfirmed entities or world details. Confirm those first, then apply the relationship.",
    CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_CONFLICT: "This relationship duplicates or conflicts with existing content, so it cannot be applied yet.",
    CopilotTextKey.SUGGESTION_CREATE_REASON_SYSTEM_INCOMPLETE: "This system suggestion is incomplete and cannot be applied yet.",
    CopilotTextKey.SUGGESTION_CREATE_REASON_SYSTEM_NAME_COLLISION: "This system name is too close to existing content. Adjust it before applying.",

    CopilotTextKey.APPLY_ERROR_SUGGESTION_NOT_FOUND: "This suggestion is no longer valid. Generate it again.",
    CopilotTextKey.APPLY_ERROR_ALREADY_APPLIED: "This suggestion was already applied.",
    CopilotTextKey.APPLY_ERROR_STALE: "The underlying content just changed. Refresh and try again.",
    CopilotTextKey.APPLY_ERROR_DEPENDENCY_FAILED: "This relationship still depends on unconfirmed entities or world details. Confirm those first, then apply the relationship.",
    CopilotTextKey.APPLY_ERROR_GENERIC: "The apply step did not succeed. Please try again later.",

    CopilotTextKey.WORKSPACE_EVIDENCE_COMPILED: "Compiled from related clues",
    CopilotTextKey.WORKSPACE_EVIDENCE_COMPILED_MULTIPLE: "Compiled from {count} related clues",
}

_JA: dict[CopilotTextKey, str] = {
    CopilotTextKey.INVALID_MODEL_OUTPUT: "モデルが返した確認結果を読み取れませんでした。選択範囲を短くするか、設定でモデルを切り替えてください。",
    CopilotTextKey.RUN_FAILED: "Copilot の実行に失敗しました。しばらくしてからもう一度お試しください。",
    CopilotTextKey.RUN_INTERRUPTED: "Copilot の実行でバックグラウンドのアクティブリースが失われました。もう一度お試しください。",
    CopilotTextKey.RUN_RESEARCHING: "調査中です。モデルがツールを使うかどうか判断するのを待っています...",

    CopilotTextKey.TRACE_EMPTY_QUERY: "（空のクエリ）",
    CopilotTextKey.TRACE_RETRIEVAL_STEP_INCOMPLETE: "取得ステップは完了しませんでした：{error}",
    CopilotTextKey.TRACE_FIND: "「{query}」を検索",
    CopilotTextKey.TRACE_FIND_SCOPE_SUFFIX: "（範囲：{scope}）",
    CopilotTextKey.TRACE_FIND_TOTAL_SUFFIX: "、関連手がかりを {count} 件見つけました",
    CopilotTextKey.TRACE_OPEN: "追加コンテキストを展開",
    CopilotTextKey.TRACE_OPEN_SOURCE_SUFFIX: "、ソースを {count} 件追加",
    CopilotTextKey.TRACE_READ_TARGETS: "設定対象を {count} 件読み込み",
    CopilotTextKey.TRACE_READ_RESULTS_SUFFIX: "、結果を {count} 件返しました",
    CopilotTextKey.TRACE_REFRESH_SNAPSHOT: "現在の世界設定スナップショットを更新",
    CopilotTextKey.TRACE_REFRESH_ENTITIES: "エンティティ {count}",
    CopilotTextKey.TRACE_REFRESH_RELATIONSHIPS: "関係 {count}",
    CopilotTextKey.TRACE_REFRESH_DRAFTS: "草稿 {count}",
    CopilotTextKey.TRACE_REFRESH_COUNTS_SUFFIX: "、{counts}",
    CopilotTextKey.TRACE_REFRESH_CONTEXT_REFRESHED_SUFFIX: "：コンテキストを更新しました",
    CopilotTextKey.TRACE_GENERIC_TOOL_COMPLETED: "取得ステップ「{tool_name}」を実行しました",

    CopilotTextKey.TRACE_TOOL_MODE_USED_STEPS: "この実行では段階的な取得を {count} 回行いました",
    CopilotTextKey.TRACE_TOOL_MODE_DIRECT: "追加の取得ステップは不要で、モデルがそのまま分析を完了しました",
    CopilotTextKey.TRACE_TOOL_COMPLETED_FALLBACK: "ツール {tool_name}：完了",
    CopilotTextKey.TRACE_ANALYZE_RUNNING: "取得結果を整理して回答を生成しています...",
    CopilotTextKey.TRACE_TOOL_LOOP_COMPLETED: "ツールベースの調査が完了しました",
    CopilotTextKey.TRACE_ONE_SHOT_UNSUPPORTED: "現在のモデルは段階的取得をサポートしていないため、直接分析に切り替えました",
    CopilotTextKey.TRACE_ONE_SHOT_FAILED: "段階的取得で問題が発生したため（{reason}）、直接分析に切り替えました",
    CopilotTextKey.TRACE_EVIDENCE_PREPARED: "表示用の根拠を {count} 件整理しました",
    CopilotTextKey.TRACE_ANALYSIS_COMPLETED: "分析が完了し、提案を {count} 件生成しました",
}

_KO: dict[CopilotTextKey, str] = {
    CopilotTextKey.INVALID_MODEL_OUTPUT: "모델의 검토 결과를 읽을 수 없습니다. 선택한 구절을 줄이거나 설정에서 모델을 변경해 보세요.",
    CopilotTextKey.RUN_FAILED: "Copilot 실행에 실패했습니다. 잠시 후 다시 시도해 주세요.",
    CopilotTextKey.RUN_INTERRUPTED: "Copilot 실행에서 백그라운드 활성 리스가 끊어졌습니다. 다시 시도해 주세요.",
    CopilotTextKey.RUN_RESEARCHING: "조사 중입니다. 모델이 도구를 사용할지 결정하는 중입니다...",

    CopilotTextKey.TRACE_EMPTY_QUERY: "(빈 쿼리)",
    CopilotTextKey.TRACE_RETRIEVAL_STEP_INCOMPLETE: "검색 단계가 완료되지 않았습니다: {error}",
    CopilotTextKey.TRACE_FIND: '"{query}" 검색',
    CopilotTextKey.TRACE_FIND_SCOPE_SUFFIX: " (범위: {scope})",
    CopilotTextKey.TRACE_FIND_TOTAL_SUFFIX: ", 관련 단서를 {count}건 찾았습니다",
    CopilotTextKey.TRACE_OPEN: "추가 문맥 펼치기",
    CopilotTextKey.TRACE_OPEN_SOURCE_SUFFIX: ", 출처를 {count}건 추가했습니다",
    CopilotTextKey.TRACE_READ_TARGETS: "설정 대상 {count}개 읽기",
    CopilotTextKey.TRACE_READ_RESULTS_SUFFIX: ", 결과 {count}개 반환",
    CopilotTextKey.TRACE_REFRESH_SNAPSHOT: "현재 세계 설정 스냅샷 새로고침",
    CopilotTextKey.TRACE_REFRESH_ENTITIES: "엔티티 {count}",
    CopilotTextKey.TRACE_REFRESH_RELATIONSHIPS: "관계 {count}",
    CopilotTextKey.TRACE_REFRESH_DRAFTS: "초안 {count}",
    CopilotTextKey.TRACE_REFRESH_COUNTS_SUFFIX: ", {counts}",
    CopilotTextKey.TRACE_REFRESH_CONTEXT_REFRESHED_SUFFIX: ": 문맥을 새로고침했습니다",
    CopilotTextKey.TRACE_GENERIC_TOOL_COMPLETED: '"{tool_name}" 검색 단계를 완료했습니다',

    CopilotTextKey.TRACE_TOOL_MODE_USED_STEPS: "이번 실행에서는 단계별 검색을 {count}번 사용했습니다",
    CopilotTextKey.TRACE_TOOL_MODE_DIRECT: "추가 검색 단계 없이 모델이 바로 분석을 완료했습니다",
    CopilotTextKey.TRACE_TOOL_COMPLETED_FALLBACK: "도구 {tool_name}: 완료",
    CopilotTextKey.TRACE_ANALYZE_RUNNING: "검색 결과를 정리하고 답변을 작성하는 중입니다...",
    CopilotTextKey.TRACE_TOOL_LOOP_COMPLETED: "도구 기반 조사가 완료되었습니다",
    CopilotTextKey.TRACE_ONE_SHOT_UNSUPPORTED: "현재 모델이 단계별 검색을 지원하지 않아 직접 분석으로 전환했습니다",
    CopilotTextKey.TRACE_ONE_SHOT_FAILED: "단계별 검색에 문제가 발생해({reason}) 직접 분석으로 전환했습니다",
    CopilotTextKey.TRACE_EVIDENCE_PREPARED: "표시할 근거 {count}개를 준비했습니다",
    CopilotTextKey.TRACE_ANALYSIS_COMPLETED: "분석이 완료되어 제안 {count}개를 생성했습니다",
}

register_copilot_messages("zh", _ZH)
register_copilot_messages("en", _EN)
register_copilot_messages("ja", _JA)
register_copilot_messages("ko", _KO)
