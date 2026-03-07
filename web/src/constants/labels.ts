export const LABELS = {
  // Tabs
  TAB_SYSTEMS: '世界体系',
  TAB_ENTITIES: '实体',
  TAB_RELATIONSHIPS: '关系',

  // Entity
  ENTITY_NEW: '+ 新实体',
  ENTITY_SEARCH_PLACEHOLDER: '搜索实体...',
  ENTITY_EMPTY: '选择一个实体查看详情',
  ENTITY_DELETE: '删除实体',
  ENTITY_DELETE_CONFIRM: '确定要删除这个实体吗？删除后无法恢复。',
  ENTITY_TYPE_ALL: '全部',
  ENTITY_ATTRIBUTES: '属性',
  ENTITY_ADD_ATTRIBUTE: '+ 添加属性',
  ENTITY_DRAFT_BANNER: (n: number) => `${n} 个待确认`,
  STATUS_DRAFT: '草稿',

  // Visibility
  VIS_ACTIVE: '活跃',
  VIS_REFERENCE: '参考',
  VIS_HIDDEN: '隐藏',

  // System
  SYSTEM_NEW: '+ 新体系',
  SYSTEM_SEARCH_PLACEHOLDER: '搜索体系...',
  SYSTEM_BACK: '‹ 世界体系',
  SYSTEM_CONSTRAINTS: '规则约束',
  SYSTEM_ADD_CONSTRAINT: '+ 添加约束',
  SYSTEM_ADD_ROOT: '+ 添加根节点',
  SYSTEM_ADD_EVENT: '+ 添加事件',
  SYSTEM_ADD_ITEM: '+ 添加规则',
  SYSTEM_INSERT: '+ 插入',
  SYSTEM_TYPE_HIERARCHY: '层级结构',
  SYSTEM_TYPE_GRAPH: '网络图',
  SYSTEM_TYPE_TIMELINE: '时间线',
  SYSTEM_TYPE_LIST: '列表',
  SYSTEM_DELETE: '删除体系',
  SYSTEM_DELETE_CONFIRM: '确认删除？',

  // Relationship
  REL_EMPTY: '选择一个实体查看关系',
  REL_NEW: '创建关系',
  REL_DELETE: '删除关系',
  REL_DELETE_CONFIRM: '确定要删除这个关系吗？',
  REL_DESCRIPTION: '关系描述',
  REL_LABEL_PLACEHOLDER: '（关系标签）',
  REL_DESCRIPTION_PLACEHOLDER: '（添加关系描述，决定续写质量）',
  REL_INSPECTOR_EMPTY: '点击一条关系查看描述',
  REL_INSPECTOR_HINT: '选择一条关系后，这里会展示其描述（更影响续写质量）',

  // Common
  CONFIRM: '确认',
  CANCEL: '取消',
  DELETE: '删除',
  SAVE: '保存',
  BATCH_CONFIRM: '批量确认',

  // Placeholders
  PH_KEY: '键名',
  PH_VALUE: '值',
  PH_NAME: '名称',
  PH_DESCRIPTION: '描述',
  PH_NODE_NAME: '节点名称',
  PH_EVENT_NAME: '事件名称',
  PH_TIME: '时间',
  PH_CONSTRAINT: '约束规则',
  PH_SYSTEM_NAME: '体系名称',

  // Bootstrap
  BOOTSTRAP_INITIAL_EXTRACTION: '提取实体与关系',
  BOOTSTRAP_REEXTRACT: '重提取实体关系',
  BOOTSTRAP_SCANNING: '处理中...',
  BOOTSTRAP_COMPLETED_INDEX_REFRESH: '章节关联分析完成',
  BOOTSTRAP_COMPLETED_EXTRACTION: (e: number, r: number) => `提取到 ${e} 个实体、${r} 条关系`,
  BOOTSTRAP_FAILED: '执行失败',
  BOOTSTRAP_REEXTRACT_CONFIRM_TITLE: '危险操作：重提取实体关系',
  BOOTSTRAP_REEXTRACT_CONFIRM_DESC:
    '替换当前 AI 提取的草稿（保留已确认内容），然后重新提取实体和关系。\n确认继续吗？',
  BOOTSTRAP_REEXTRACT_CONFIRM: '确认重提取',
  BOOTSTRAP_STEP_PENDING: '准备中',
  BOOTSTRAP_STEP_TOKENIZING: '分词处理',
  BOOTSTRAP_STEP_EXTRACTING: '提取候选词',
  BOOTSTRAP_STEP_WINDOWING: '分析章节关联',
  BOOTSTRAP_STEP_REFINING: 'AI 精炼提取',
  BOOTSTRAP_NO_TEXT: '请先上传章节内容',

  // Error toasts (World Model)
  ERROR_DELETE_FAILED: '删除失败，请重试',
  ERROR_SAVE_FAILED: '保存失败，请重试',
  ERROR_CONFIRM_FAILED: '确认失败，请重试',
  ERROR_REJECT_FAILED: '拒绝失败，请重试',
  ERROR_BOOTSTRAP_TRIGGER_FAILED: '操作失败，请重试',
  WORLDPACK_IMPORT_COMPLETED: '世界观导入完成',
  WORLDPACK_IMPORT_FAILED: '世界观导入失败，请重试',

  // Draft review
  CONFIRM_ALL_ENTITIES: '全部确认',
  CONFIRM_ALL_RELATIONSHIPS: '全部确认',

  // Display helpers (centralized for future i18n)
  ENTITY_TYPE_LABEL: (entityType: string, locale: 'zh' | 'en' = 'zh') => {
    const table: Record<'zh' | 'en', Record<string, string>> = {
      zh: {
        Character: '角色',
        Location: '地点',
        Faction: '势力',
        Concept: '概念',
        Vehicle: '载具',
        Item: '物品',
      },
      en: {
        Character: 'Character',
        Location: 'Location',
        Faction: 'Faction',
        Concept: 'Concept',
        Vehicle: 'Vehicle',
        Item: 'Item',
      },
    }
    return table[locale][entityType] ?? entityType
  },
} as const
