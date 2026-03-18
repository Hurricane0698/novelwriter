import { beforeEach, describe, it, expect, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { MemoryRouter, useLocation, useSearchParams } from 'react-router-dom'
import {
  NovelCopilotProvider,
} from '@/components/novel-copilot/NovelCopilotProvider'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { NovelCopilotDrawer } from '@/components/novel-copilot/NovelCopilotDrawer'
import { ToastProvider } from '@/components/world-model/shared/Toast'
import { ApiError } from '@/services/api'

// Mock copilot API — these tests verify UI behavior, not API integration
const mockOpenSession = vi.fn()
const mockListRuns = vi.fn()
const mockCreateRun = vi.fn()
const mockPollRun = vi.fn()
const mockApplySuggestions = vi.fn()
const mockDismissSuggestions = vi.fn()

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

vi.mock('@/services/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/services/api')>()
  return {
    ...original,
    copilotApi: {
      openSession: (...args: unknown[]) => mockOpenSession(...args),
      listRuns: (...args: unknown[]) => mockListRuns(...args),
      createRun: (...args: unknown[]) => mockCreateRun(...args),
      pollRun: (...args: unknown[]) => mockPollRun(...args),
      pollLatestRun: vi.fn().mockRejectedValue(
        new original.ApiError(404, 'HTTP 404', { code: 'run_not_found' }),
      ),
      applySuggestions: (...args: unknown[]) => mockApplySuggestions(...args),
      dismissSuggestions: (...args: unknown[]) => mockDismissSuggestions(...args),
    },
  }
})

beforeEach(() => {
  // Copilot API mocks
  mockOpenSession.mockReset().mockResolvedValue({
    session_id: 'backend-session-1',
    signature: 'test-sig',
    mode: 'research',
    scope: 'whole_book',
    context: null,
    interaction_locale: 'zh',
    display_title: '',
    created: true,
    created_at: new Date().toISOString(),
  })
  mockListRuns.mockReset().mockResolvedValue([])
  mockCreateRun.mockReset().mockImplementation(
    async (...[, , data]: [number, string, { prompt: string }]) => ({
      run_id: 'backend-run-1',
      status: 'queued',
      prompt: data.prompt,
      trace: [{ step_id: 's0', kind: 'init', status: 'running', summary: '正在连接...' }],
      evidence: [],
      suggestions: [],
    }),
  )
  // Poll returns completed with suggestions matching old mock shape
  mockPollRun.mockReset().mockImplementation(
    async () => ({
      run_id: 'backend-run-1',
      status: 'completed',
      prompt: '补完苏瑶的设定锚点',
      answer: '分析完成',
      trace: [
        { step_id: 'tool_mode', kind: 'tool_mode', status: 'completed', summary: '本轮启用工具研究模式，调用 1 次工具' },
        { step_id: 'tool_1', kind: 'tool_find', status: 'completed', summary: '工具检索：搜索「苏瑶」' },
        { step_id: 'evidence_complete', kind: 'evidence', status: 'completed', summary: '整理出 1 条可展示依据' },
        { step_id: 'analyze_complete', kind: 'analyze', status: 'completed', summary: '分析完成，2 条建议' },
      ],
      evidence: [{ evidence_id: 'e_1', source_type: 'chapter_excerpt', title: '第1章', excerpt: '苏瑶与古老宗门之间的牵连被再次提起', why_relevant: '章节证据' }],
      suggestions: [
        {
          suggestion_id: 'sg_test_primary',
          kind: 'update_entity',
          title: '补完 苏瑶 的设定锚点',
          summary: '补足实体描述中的背景与隐含约束。',
          evidence_ids: ['e_1'],
          target: { resource: 'entity', resource_id: 101, label: '苏瑶', tab: 'entities', entity_id: 101 },
          preview: {
            target_label: '苏瑶',
            summary: '补足实体描述中的背景与隐含约束。',
            field_deltas: [{ field: 'description', label: '描述', before: '女主角', after: '苏瑶与古老宗门存在未明牵连，并在关键章节中多次被提及。' }],
            evidence_quotes: ['苏瑶与古老宗门之间的牵连被再次提起'],
            actionable: true,
          },
          apply: { type: 'update_entity', entity_id: 101, data: { description: '苏瑶与古老宗门存在未明牵连，并在关键章节中多次被提及。' } },
          status: 'pending',
        },
        {
          suggestion_id: 'sg_test_secondary',
          kind: 'update_entity',
          title: '补充 苏瑶 的别名或属性',
          summary: '补充别名',
          evidence_ids: ['e_1'],
          target: { resource: 'entity', resource_id: 101, label: '苏瑶', tab: 'entities', entity_id: 101 },
          preview: {
            target_label: '苏瑶',
            summary: '补充一个稳定别名',
            field_deltas: [{ field: 'aliases', label: '别名', before: '', after: '宗门旧识' }],
            evidence_quotes: [],
            actionable: true,
          },
          apply: { type: 'update_entity', entity_id: 101, data: { aliases: ['宗门旧识'] } },
          status: 'pending',
        },
      ],
    }),
  )
  mockApplySuggestions.mockReset().mockResolvedValue({
    results: [{ suggestion_id: 'sg_test_primary', success: true }],
  })
  mockDismissSuggestions.mockReset().mockResolvedValue({ ok: true })
})

function DrawerHarness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return createElement(
    MemoryRouter,
    null,
    createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(
        ToastProvider,
        null,
        createElement(
          NovelCopilotProvider,
          { novelId: 1, interactionLocale: 'zh' },
          createElement(SearchEcho),
          createElement(SessionCountProbe),
          createElement(DrawerTriggers),
          createElement(ConnectedDrawer),
        ),
      ),
    ),
  )
}

function SearchEcho() {
  const location = useLocation()
  return createElement('div', { 'data-testid': 'location-search' }, location.search)
}

function ConnectedDrawer() {
  const [, setSearchParams] = useSearchParams()
  const location = useLocation()

  return createElement(NovelCopilotDrawer, {
    novelId: 1,
    onLocateTarget: (target: { tab: string; review_kind?: string | null }) => {
      const next = new URLSearchParams(location.search)
      if (target.tab === 'review') {
        next.set('tab', 'review')
        if (target.review_kind) next.set('kind', target.review_kind)
      } else {
        next.set('tab', target.tab)
      }
      setSearchParams(next)
    },
  })
}

function SessionCountProbe() {
  const { sessions } = useNovelCopilot()
  return createElement('div', { 'data-testid': 'copilot-session-count' }, String(sessions.length))
}

function DrawerTriggers() {
  const { openDrawer } = useNovelCopilot()

  return createElement(
    'div',
    null,
    createElement(
      'button',
      {
        type: 'button',
        onClick: () => openDrawer(
          { mode: 'research', scope: 'whole_book' },
          { displayTitle: '全书探索' },
        ),
      },
      'open-whole-book',
    ),
    createElement(
      'button',
      {
        type: 'button',
        onClick: () => openDrawer(
          { mode: 'draft_cleanup', scope: 'current_tab', context: { tab: 'review' } },
          { displayTitle: '草稿整理' },
        ),
      },
      'open-draft-cleanup',
    ),
    createElement(
      'button',
      {
        type: 'button',
        onClick: () => openDrawer(
          { mode: 'current_entity', scope: 'current_entity', context: { entity_id: 101 } },
          { displayTitle: '苏瑶' },
        ),
      },
      'open-current-entity',
    ),
    createElement(
      'button',
      {
        type: 'button',
        onClick: () => openDrawer(
          {
            mode: 'current_entity',
            scope: 'current_entity',
            context: { entity_id: 101, surface: 'atlas', tab: 'entities' },
          },
          { displayTitle: '苏瑶（Atlas）' },
        ),
      },
      'open-current-entity-atlas',
    ),
  )
}

describe('NovelCopilotDrawer', () => {
  it('stays cold while closed and only initializes world run data after opening a session', async () => {
    const user = userEvent.setup()
    render(createElement(DrawerHarness))

    expect(screen.queryByTestId('novel-copilot-drawer')).toBeNull()
    expect(mockOpenSession).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'open-whole-book' }))

    expect(screen.getByTestId('novel-copilot-drawer')).toBeTruthy()
    await waitFor(() => {
      expect(mockOpenSession).toHaveBeenCalled()
    })
  })

  it('reuses the same current-entity session across studio and atlas UI contexts', async () => {
    const user = userEvent.setup()
    render(createElement(DrawerHarness))

    await user.click(screen.getByRole('button', { name: 'open-current-entity' }))
    expect(screen.getByTestId('copilot-session-count')).toHaveTextContent('1')

    await waitFor(() => {
      expect(mockOpenSession).toHaveBeenLastCalledWith(
        1,
        expect.objectContaining({
          mode: 'current_entity',
          scope: 'current_entity',
          context: { entity_id: 101 },
        }),
      )
    })

    await user.click(screen.getByRole('button', { name: 'open-current-entity-atlas' }))

    expect(screen.getByTestId('copilot-session-count')).toHaveTextContent('1')
    await waitFor(() => {
      expect(mockOpenSession).toHaveBeenLastCalledWith(
        1,
        expect.objectContaining({
          mode: 'current_entity',
          scope: 'current_entity',
          context: { entity_id: 101, surface: 'atlas', tab: 'entities' },
        }),
      )
    })
  })

  it('reuses the same in-flight backend session resolver for warmup and first run submission', async () => {
    const user = userEvent.setup()
    const openSessionDeferred = deferred<{
      session_id: string
      signature: string
      mode: string
      scope: string
      context: null
      interaction_locale: string
      display_title: string
      created: boolean
      created_at: string
    }>()
    mockOpenSession.mockReset().mockImplementation(() => openSessionDeferred.promise)

    render(createElement(DrawerHarness))

    await user.click(screen.getByRole('button', { name: 'open-whole-book' }))
    await user.click(screen.getByRole('button', { name: /盘点设定缺口/ }))

    expect(mockOpenSession).toHaveBeenCalledTimes(1)
    expect(mockCreateRun).not.toHaveBeenCalled()

    await act(async () => {
      openSessionDeferred.resolve({
        session_id: 'backend-session-1',
        signature: 'test-sig',
        mode: 'research',
        scope: 'whole_book',
        context: null,
        interaction_locale: 'zh',
        display_title: '全书探索',
        created: true,
        created_at: new Date().toISOString(),
      })
      await openSessionDeferred.promise
    })

    await waitFor(() => {
      expect(mockCreateRun).toHaveBeenCalledWith(
        1,
        'backend-session-1',
        expect.objectContaining({
          quick_action_id: 'scan_world_gaps',
        }),
      )
    })
    expect(mockOpenSession).toHaveBeenCalledTimes(1)
  })

  it('switches copy and presets across whole-book, entity, and draft sessions', async () => {
    const user = userEvent.setup()
    document.documentElement.classList.add('light')
    render(createElement(DrawerHarness))

    try {
      await user.click(screen.getByRole('button', { name: 'open-whole-book' }))

      expect(screen.getAllByText('全书研究').length).toBeGreaterThan(0)
      expect(screen.getByText('研究工作台')).toBeTruthy()
      expect(screen.getByText('盘点设定缺口')).toBeTruthy()
      expect(screen.getByPlaceholderText('输入研究问题，例如“盘点全书里反复出现但尚未入模的势力、地点和规则”')).toBeTruthy()

      await user.click(screen.getByRole('button', { name: 'open-current-entity' }))

      expect(screen.getByTestId('novel-copilot-session-strip')).toBeTruthy()
      expect(screen.getAllByText('苏瑶').length).toBeGreaterThan(0)
      expect(screen.getAllByText('实体上下文').length).toBeGreaterThan(0)
      expect(screen.getByText('实体补完')).toBeTruthy()
      expect(screen.getByText('围绕 苏瑶 补足类型、属性、约束与关联线索，不要默认它只是人物。')).toBeTruthy()
      expect(screen.getByText('补完当前实体')).toBeTruthy()
      expect(screen.getByPlaceholderText('输入补充要求，例如“优先补足苏瑶与宗门的关联线索”')).toBeTruthy()

      await user.type(
        screen.getByPlaceholderText('输入补充要求，例如“优先补足苏瑶与宗门的关联线索”'),
        '补完苏瑶的设定锚点{enter}',
      )
      expect(screen.getByText('补完苏瑶的设定锚点')).toBeTruthy()

      await user.click(screen.getByRole('button', { name: 'open-draft-cleanup' }))

      expect(screen.getAllByText('草稿整理').length).toBeGreaterThan(0)
      expect(screen.getAllByText('草稿上下文').length).toBeGreaterThan(0)
      expect(screen.getByText('草稿清理')).toBeTruthy()
      expect(screen.getByText('统一草稿命名')).toBeTruthy()
      expect(screen.getByPlaceholderText('输入清理目标，例如“统一草稿命名并标出最值得先确认的条目”')).toBeTruthy()
      expect(screen.queryByText('补完苏瑶的设定锚点')).toBeNull()

      await user.click(screen.getByRole('button', { name: /苏瑶/ }))

      expect(await screen.findByText('补完 苏瑶 的设定锚点', {}, { timeout: 3000 })).toBeTruthy()
      expect(screen.getByText('补充 苏瑶 的别名或属性')).toBeTruthy()
      expect(screen.getByText('研究过程')).toBeTruthy()
      expect(screen.getByText('1 步检索 · 1 条依据')).toBeTruthy()
      expect(screen.queryByText('搜索「苏瑶」')).toBeNull()
      expect(screen.queryByText('苏瑶与古老宗门之间的牵连被再次提起')).toBeNull()

      await user.click(screen.getByRole('button', { name: '展开研究过程' }))

      expect(screen.getByText('本轮通过分步检索整理信息，共执行 1 步')).toBeTruthy()
      expect(screen.getByText('搜索「苏瑶」')).toBeTruthy()
      expect(screen.getByText('第1章')).toBeTruthy()

      await user.click(screen.getByRole('button', { name: /第1章/ }))
      const researchDetail = screen.getByTestId('copilot-research-detail')
      expect(researchDetail).toBeTruthy()
      expect(within(researchDetail).getByText('完整依据')).toBeTruthy()
      expect(within(researchDetail).getByText('苏瑶与古老宗门之间的牵连被再次提起')).toBeTruthy()

      await user.click(
        within(screen.getByTestId(/copilot-suggestion-.*primary/)).getByRole('button', { name: '展开预览' }),
      )
      expect(screen.getByText('目标:')).toBeTruthy()
      expect(screen.getAllByText('补足实体描述中的背景与隐含约束。').length).toBeGreaterThan(0)
      expect(screen.getAllByText('描述').length).toBeGreaterThan(0)

      await user.click(
        within(screen.getByTestId(/copilot-suggestion-.*primary/)).getByRole('button', { name: '查看目标' }),
      )
      expect(screen.getByTestId('location-search').textContent).toContain('tab=entities')

      await user.click(
        within(screen.getByTestId(/copilot-suggestion-.*primary/)).getByRole('button', { name: /采纳/ }),
      )
      // With real API: frontend calls copilotApi.applySuggestions (backend does the world mutation)
      expect(mockApplySuggestions).toHaveBeenCalled()
      expect(screen.getAllByText('已采纳').length).toBeGreaterThan(0)

      const wholeBookSession = within(screen.getByTestId('novel-copilot-session-strip'))
        .getByText('全书探索')
        .closest('[data-testid^="novel-copilot-session-"]')
      expect(wholeBookSession).toBeTruthy()

      const entitySession = within(screen.getByTestId('novel-copilot-session-strip'))
        .getByText('苏瑶')
        .closest('[data-testid^="novel-copilot-session-"]')
      expect(entitySession).toBeTruthy()
      await user.click(within(entitySession as HTMLElement).getByRole('button', { name: '关闭会话' }))

      expect(screen.queryByText('补完 苏瑶 的设定锚点')).toBeNull()
      expect(screen.getAllByText('草稿整理').length).toBeGreaterThan(0)
    } finally {
      document.documentElement.classList.remove('light')
    }
  })

  it('shows a friendly apply failure toast instead of silently doing nothing', async () => {
    const user = userEvent.setup()
    mockApplySuggestions.mockResolvedValueOnce({
      results: [{ suggestion_id: 'sg_test_primary', success: false, error_code: 'copilot_target_stale', error_message: '这条建议对应的内容刚刚发生了变化，请刷新后再试一次。' }],
    })

    render(createElement(DrawerHarness))

    await user.click(screen.getByRole('button', { name: 'open-current-entity' }))
    await user.type(
      screen.getByPlaceholderText('输入补充要求，例如“优先补足苏瑶与宗门的关联线索”'),
      '补完苏瑶的设定锚点{enter}',
    )
    await screen.findByText('补完 苏瑶 的设定锚点', {}, { timeout: 3000 })

    await user.click(
      within(screen.getByTestId(/copilot-suggestion-.*primary/)).getByRole('button', { name: /采纳/ }),
    )

    expect(await screen.findByText('这条建议对应的内容刚刚发生了变化，请刷新后再试一次。')).toBeTruthy()
  })

  it('sanitizes legacy tool-trace and evidence-pack wording before rendering it to users', async () => {
    const user = userEvent.setup()
    mockPollRun.mockResolvedValueOnce({
      run_id: 'backend-run-1',
      status: 'completed',
      prompt: '补全设定线索',
      answer: '分析完成',
      trace: [
        { step_id: 'tool_mode', kind: 'tool_mode', status: 'completed', summary: '本轮启用工具研究模式，调用 2 次工具' },
        { step_id: 'tool_1', kind: 'tool_find', status: 'completed', summary: '工具检索：搜索「苏瑶」' },
        { step_id: 'tool_2', kind: 'tool_open', status: 'completed', summary: '工具展开：打开证据包 pk_abc123，来源 2 条' },
      ],
      evidence: [{
        evidence_id: 'pack_pk_abc123',
        source_type: 'evidence_pack',
        title: '苏瑶 / 宗门',
        excerpt: '苏瑶与宗门旧事被多处提及。',
        why_relevant: 'Tool-discovered (support: 2)',
        pack_id: 'pk_abc123',
        support_count: 2,
        preview_excerpt: '苏瑶与宗门旧事被多处提及。',
        expanded: false,
      }],
      suggestions: [],
    })

    render(createElement(DrawerHarness))

    await user.click(screen.getByRole('button', { name: 'open-current-entity' }))
    await user.type(
      screen.getByPlaceholderText('输入补充要求，例如“优先补足苏瑶与宗门的关联线索”'),
      '补全设定线索{enter}',
    )

    await screen.findByText('分析完成', {}, { timeout: 3000 })
    await user.click(screen.getByRole('button', { name: '展开研究过程' }))

    const researchProcess = screen.getByTestId('copilot-research-process')
    expect(researchProcess).toHaveTextContent('本轮通过分步检索整理信息，共执行 2 步')
    expect(researchProcess).toHaveTextContent('展开更多上下文，补充了 2 条来源')
    expect(researchProcess).toHaveTextContent('线索摘要')
    expect(researchProcess).toHaveTextContent('已从相关线索中整理')
    expect(researchProcess).not.toHaveTextContent(/Tool-discovered/i)
    expect(researchProcess).not.toHaveTextContent(/证据包/)
    expect(researchProcess).not.toHaveTextContent(/命中信号/)

    await user.click(screen.getByRole('button', { name: /苏瑶 \/ 宗门/ }))
    const researchDetail = screen.getByTestId('copilot-research-detail')
    expect(within(researchDetail).getByText('相关依据')).toBeTruthy()
    expect(within(researchDetail).queryByText(/命中信号/)).toBeNull()
  })

  it.each([
    [409, 'session_run_active', '当前会话里已有一轮研究正在进行，请等它完成后再继续。'],
    [429, 'too_many_active_runs', '你当前同时进行的研究轮次已达上限，请先等待其他会话完成。'],
    [429, 'generation_quota_exhausted', '可用额度已用完，请先提交反馈解锁更多额度。'],
    [503, 'too_many_global_runs', '当前服务器较忙，正在处理过多的 Copilot 请求，请稍后再试。'],
  ] as const)('shows a friendly run creation error for %s/%s', async (status, code, expectedMessage) => {
    const user = userEvent.setup()
    mockCreateRun.mockRejectedValueOnce(new ApiError(status, `HTTP ${status}`, {
      code,
      detail: { code },
    }))

    render(createElement(DrawerHarness))

    await user.click(screen.getByRole('button', { name: 'open-current-entity' }))
    await user.type(
      screen.getByPlaceholderText('输入补充要求，例如“优先补足苏瑶与宗门的关联线索”'),
      '补完苏瑶的设定锚点{enter}',
    )

    expect(await screen.findByText(expectedMessage)).toBeTruthy()
    expect(screen.queryByText(`HTTP ${status}`)).toBeNull()
  })

  it('renders a human-friendly reason when a suggestion cannot be directly applied', async () => {
    const user = userEvent.setup()
    mockPollRun.mockResolvedValueOnce({
      run_id: 'backend-run-1',
      status: 'completed',
      prompt: '补全关系',
      answer: '分析完成',
      trace: [],
      evidence: [],
      suggestions: [
        {
          suggestion_id: 'sg_rel_blocked',
          kind: 'create_relationship',
          title: '补上关系',
          summary: '建议补上一条关键关系。',
          evidence_ids: [],
          target: { resource: 'relationship', resource_id: null, label: '新关系', tab: 'relationships', entity_id: 101 },
          preview: {
            target_label: '新关系',
            summary: '建议补上一条关键关系。',
            field_deltas: [],
            evidence_quotes: [],
            actionable: false,
            non_actionable_reason: '这条关系还依赖未确认的人物或设定。请先确认相关实体，再来确认这条关系。',
          },
          apply: null,
          status: 'pending',
        },
      ],
    })

    render(createElement(DrawerHarness))

    await user.click(screen.getByRole('button', { name: 'open-current-entity' }))
    await user.type(
      screen.getByPlaceholderText('输入补充要求，例如“优先补足苏瑶与宗门的关联线索”'),
      '补全关系{enter}',
    )

    expect(await screen.findByText('补上关系', {}, { timeout: 3000 })).toBeTruthy()
    expect(screen.getByText(/请先确认相关实体，再来确认这条关系/)).toBeTruthy()
  })

  it('hydrates the latest backend run when reopening the same context', async () => {
    const user = userEvent.setup()
    mockListRuns.mockResolvedValueOnce([
      {
        run_id: 'backend-latest-run',
        status: 'completed',
        prompt: '补完苏瑶的设定锚点',
        answer: '这是后端恢复出的最新分析结果',
        trace: [
          { step_id: 'tool_mode', kind: 'tool_mode', status: 'completed', summary: '本轮启用工具研究模式，调用 1 次工具' },
        ],
        evidence: [],
        suggestions: [
          {
            suggestion_id: 'sg_latest',
            kind: 'update_entity',
            title: '恢复的建议卡',
            summary: '来自后端最新 run',
            evidence_ids: [],
            target: { resource: 'entity', resource_id: 101, label: '苏瑶', tab: 'entities', entity_id: 101 },
            preview: {
              target_label: '苏瑶',
              summary: '恢复的建议预览',
              field_deltas: [],
              evidence_quotes: [],
              actionable: true,
            },
            apply: { type: 'update_entity', entity_id: 101, data: { description: '恢复后的描述' } },
            status: 'pending',
          },
        ],
      },
    ])

    render(createElement(DrawerHarness))

    await user.click(screen.getByRole('button', { name: 'open-current-entity' }))

    expect(await screen.findByText('恢复的建议卡')).toBeTruthy()
    expect(screen.getByText('这是后端恢复出的最新分析结果')).toBeTruthy()
  })

  it('shows an interrupted retry action and resumes the same run explicitly', async () => {
    const user = userEvent.setup()
    mockListRuns.mockResolvedValueOnce([
      {
        run_id: 'backend-interrupted-run',
        status: 'interrupted',
        prompt: '补完苏瑶的设定锚点',
        answer: null,
        trace: [],
        evidence: [],
        suggestions: [],
        error: '这轮研究在后台中断了。',
      },
    ])
    mockCreateRun.mockResolvedValueOnce({
      run_id: 'backend-resume-run',
      status: 'queued',
      prompt: '补完苏瑶的设定锚点',
      trace: [{ step_id: 's0', kind: 'init', status: 'running', summary: '正在恢复上次研究...' }],
      evidence: [],
      suggestions: [],
    })
    mockPollRun.mockResolvedValueOnce({
      run_id: 'backend-resume-run',
      status: 'completed',
      prompt: '补完苏瑶的设定锚点',
      answer: '恢复后的分析结果',
      trace: [],
      evidence: [],
      suggestions: [],
    })

    render(createElement(DrawerHarness))

    await user.click(screen.getByRole('button', { name: 'open-current-entity' }))
    expect(await screen.findByRole('button', { name: '恢复上次研究' })).toBeTruthy()
    expect(screen.getByText(/恢复将继续上次检索进度/)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '恢复上次研究' }))

    await waitFor(() => {
      expect(mockCreateRun).toHaveBeenCalledWith(
        1,
        'backend-session-1',
        {
          prompt: '补完苏瑶的设定锚点',
          resume_run_id: 'backend-interrupted-run',
        },
      )
    })
    expect(await screen.findByText('恢复后的分析结果', {}, { timeout: 3000 })).toBeTruthy()
  })

  it('keeps earlier turns visible when the same session submits a follow-up prompt', async () => {
    const user = userEvent.setup()

    mockCreateRun
      .mockResolvedValueOnce({
        run_id: 'backend-run-1',
        status: 'queued',
        prompt: '先总结苏瑶',
        trace: [{ step_id: 's0', kind: 'init', status: 'running', summary: '正在连接...' }],
        evidence: [],
        suggestions: [],
      })
      .mockResolvedValueOnce({
        run_id: 'backend-run-2',
        status: 'queued',
        prompt: '继续分析她和宗门的关系',
        trace: [{ step_id: 's0', kind: 'init', status: 'running', summary: '正在连接...' }],
        evidence: [],
        suggestions: [],
      })

    mockPollRun
      .mockResolvedValueOnce({
        run_id: 'backend-run-1',
        status: 'completed',
        prompt: '先总结苏瑶',
        answer: '第一轮回答',
        trace: [],
        evidence: [],
        suggestions: [],
      })
      .mockResolvedValueOnce({
        run_id: 'backend-run-2',
        status: 'completed',
        prompt: '继续分析她和宗门的关系',
        answer: '第二轮回答',
        trace: [],
        evidence: [],
        suggestions: [],
      })

    render(createElement(DrawerHarness))

    await user.click(screen.getByRole('button', { name: 'open-current-entity' }))
    const textarea = screen.getByPlaceholderText('输入补充要求，例如“优先补足苏瑶与宗门的关联线索”')

    await user.type(textarea, '先总结苏瑶{enter}')
    expect(await screen.findByText('第一轮回答', {}, { timeout: 3000 })).toBeTruthy()

    await user.type(textarea, '继续分析她和宗门的关系{enter}')
    expect(await screen.findByText('第二轮回答', {}, { timeout: 3000 })).toBeTruthy()
    expect(screen.getByText('先总结苏瑶')).toBeTruthy()
    expect(screen.getByText('继续分析她和宗门的关系')).toBeTruthy()
    expect(screen.getByText('第一轮回答')).toBeTruthy()
  })

  it('keeps polling after one transient poll failure and recovers on the next retry', async () => {
    vi.useFakeTimers()

    try {
      mockPollRun
        .mockRejectedValueOnce(new Error('temporary network error'))
        .mockResolvedValueOnce({
          run_id: 'backend-run-1',
          status: 'completed',
          prompt: '补完苏瑶的设定锚点',
          answer: '网络恢复后的分析结果',
          trace: [],
          evidence: [],
          suggestions: [],
        })

      render(createElement(DrawerHarness))

      fireEvent.click(screen.getByRole('button', { name: 'open-current-entity' }))
      const textarea = screen.getByPlaceholderText('输入补充要求，例如“优先补足苏瑶与宗门的关联线索”')
      fireEvent.change(textarea, { target: { value: '补完苏瑶的设定锚点' } })
      fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' })
      await act(async () => {
        await Promise.resolve()
      })
      expect(mockCreateRun).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500)
      })
      expect(screen.queryByText('连接中断，请稍后重试。')).toBeNull()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000)
      })
      expect(screen.getByText('网络恢复后的分析结果')).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows an error only after repeated transient poll failures exceed the retry budget', async () => {
    vi.useFakeTimers()

    try {
      mockPollRun.mockRejectedValue(new Error('persistent network error'))

      render(createElement(DrawerHarness))

      fireEvent.click(screen.getByRole('button', { name: 'open-current-entity' }))
      const textarea = screen.getByPlaceholderText('输入补充要求，例如“优先补足苏瑶与宗门的关联线索”')
      fireEvent.change(textarea, { target: { value: '补完苏瑶的设定锚点' } })
      fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' })
      await act(async () => {
        await Promise.resolve()
      })
      expect(mockCreateRun).toHaveBeenCalledTimes(1)

      for (const delayMs of [1500, 3000, 6000, 12000, 12000]) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(delayMs)
        })
      }

      expect(screen.getByText('连接中断，请稍后重试。')).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })
})
