import {
  getUiLocaleFallbackChain,
  SUPPORTED_UI_LOCALES,
  type UiLocale,
} from '@/lib/uiLocaleSchema'
import type { copilotZhMessages } from '@/lib/uiMessagePacks/copilot'
import type { homeZhMessages } from '@/lib/uiMessagePacks/home'
import type { novelZhMessages } from '@/lib/uiMessagePacks/novel'

export type { UiLocale } from '@/lib/uiLocaleSchema'

export type UiMessageParams = Record<string, string | number | boolean | null | undefined>
export type UiMessageValue = string | ((params: UiMessageParams) => string)

const APP_VERSION_LABEL = `NovWr v${__NOVWR_APP_VERSION__}`

const settingsZhMessages = {
  'settings.title': '设置',
  'settings.section.appearance': '外观',
  'settings.section.ai': 'AI 模型配置',
  'settings.footer.version': APP_VERSION_LABEL,
  'settings.appearance.themeTitle': '主题模式',
  'settings.appearance.theme.dark': '深色模式',
  'settings.appearance.theme.light': '浅色模式',
  'settings.appearance.languageTitle': '界面语言',
  'settings.appearance.languageDescription': '切换受支持产品界面的显示语言。',
  'settings.appearance.language.zh': '简体中文',
  'settings.appearance.language.en': 'English',
} as const satisfies Record<string, UiMessageValue>

const chromeZhMessages = {
  'navbar.features': '功能',
  'navbar.docs': '文档',
  'navbar.library': '作品库',
  'navbar.settings': '设置',
  'footer.description': '面向长篇小说的世界构建与辅助写作工具。',
  'dialog.confirm': '确认',
  'dialog.cancel': '取消',
  'dialog.gotIt': '知道了',
  'plainText.loading': '加载中...',
  'plainText.empty': '暂无内容',
} as const satisfies Record<string, UiMessageValue>

const libraryZhMessages = {
  'library.create': '新建作品',
  'library.import': '导入书稿',
  'library.untitled': '未命名作品',
  'library.rename': '修改书名',
  'library.error.create': '创建作品失败',
  'library.error.rename': '书名未保存',
  'library.title': '我的作品库',
  'library.description': '从第一章写起，或导入已有的 TXT、Markdown 书稿。',
  'library.error.load': '加载失败',
  'library.error.unknown': '未知错误',
  'library.error.uploadFailed': '上传失败',
  'library.error.uploadTooLarge': ({ maxMb }) => `文件过大，请上传不超过 ${String(maxMb ?? 30)} MB 的 txt 文本文件`,
  'library.error.uploadTypeNotSupported': '仅支持上传 .txt / .md 文本文件',
  'library.error.uploadParseFailed': '文件已上传，但暂时无法解析。请确认章节标题格式清晰后重试。',
  'library.uploadOverlay.title': '正在上传小说',
  'library.uploadOverlay.description': '请稍候。上传完成后，NovWr 会继续导入章节并自动准备世界信息。',
  'library.confirm.delete.title': '删除作品',
  'library.confirm.delete': '确定要删除这部作品吗？此操作不可撤销。',
  'library.empty.title': '书架上还没有作品。',
  'library.workCard.meta': ({ chapterCount, relativeTime }) => `${String(chapterCount ?? 0)} 章 · ${String(relativeTime ?? '')}更新`,
  'library.workCard.delete': '删除',
} as const satisfies Record<string, UiMessageValue>

const relativeTimeZhMessages = {
  'time.justNow': '刚刚',
  'time.minutesAgo': ({ count }) => `${String(count ?? 0)} 分钟前`,
  'time.hoursAgo': ({ count }) => `${String(count ?? 0)} 小时前`,
  'time.yesterday': '昨天',
  'time.daysAgo': ({ count }) => `${String(count ?? 0)} 天前`,
  'time.weeksAgo': ({ count }) => `${String(count ?? 0)} 周前`,
  'time.monthsAgo': ({ count }) => `${String(count ?? 0)} 月前`,
} as const satisfies Record<string, UiMessageValue>

const llmZhMessages = {
  'llm.notice.selfhost': '出于安全考虑，这里的配置只保留在当前浏览器标签页内存中；刷新页面后会清空。如果你想长期使用自己的 Key，推荐改用 Docker / 环境变量自部署。',
  'llm.notice.desktop': '配置会加密保存在这台电脑上，重启应用或覆盖安装后仍可使用。API Key 不会在界面中回显。',
  'llm.warning.partialConfig': '当前只填写了部分 BYOK 配置。请同时填写 Base URL、API Key 和 Model；否则续写、世界生成和提取都会被拒绝。',
  'llm.error.missingLocalConfig': '请先在设置中配置 AI 模型。',
  'llm.error.incompleteConfig': '当前 BYOK 配置不完整，请同时填写 Base URL、API Key 和 Model，或清空当前配置。',
  'llm.error.invalidBaseUrl': 'Base URL 必须是完整的 HTTP(S) 地址，且不能包含账号密码、查询参数、片段或空白字符。',
  'llm.error.invalidApiKey': 'API Key 格式无效。请重新填写不含空白或控制字符的有效 Key。',
  'llm.error.modelUnavailable': '当前模型不可用。请检查 Base URL、API Key、Model 是否匹配，并确认接口支持 JSON 模式。',
  'llm.result.successFallback': ({ latencyMs }) => `连接与应用兼容性检测通过 (${String(latencyMs ?? '')}ms)`,
  'llm.result.connectionFailed': '连接失败',
  'llm.result.providerConnectionFailed': '基础连接失败。请检查 Base URL、API Key 和 Model 是否匹配。',
  'llm.result.streamSupported': '流式输出已确认可用。',
  'llm.result.jsonSupported': 'JSON 模式已确认可用。',
  'llm.result.streamUnknown': '流式输出暂时无法确认，请重试。',
  'llm.result.jsonUnknown': 'JSON 模式暂时无法确认，请重试。',
  'llm.result.missingStreamCapability': '基础连接成功，但接口不支持流式输出，续写功能无法正常使用。',
  'llm.result.missingJsonCapability': '基础连接成功，但接口不支持 JSON 模式，世界生成和提取功能无法正常使用。',
  'llm.result.httpFailed': ({ status }) => `请求失败（HTTP ${String(status ?? '')}）`,
  'llm.result.saved': 'AI 模型配置已保存',
  'llm.result.cleared': 'AI 模型配置已清空',
  'llm.result.loadFailed': '无法读取本机 AI 模型配置',
  'llm.confirm.clearTitle': '清空本机 AI 模型配置？',
  'llm.confirm.clearDescription': '这会删除已加密保存的 Base URL、Model 和 API Key。删除后无法恢复，需要重新输入。',
  'llm.confirm.clearAction': '确认清空',
  'llm.label.baseUrl': 'API Base URL',
  'llm.label.apiKey': 'API Key',
  'llm.label.model': 'Model Name',
  'llm.placeholder.savedApiKey': '已保存；留空表示继续使用',
  'llm.status.apiKeyConfigured': 'API Key 已保存。留空会保留当前 Key，输入新值会替换。',
  'llm.button.saving': '保存中...',
  'llm.button.save': '保存配置',
  'llm.button.testing': '测试中...',
  'llm.button.test': '测试连接',
  'llm.button.clearing': '清空中...',
  'llm.button.retry': '重新读取',
  'llm.button.clearDesktop': '清空本机配置',
  'llm.button.clearSelfhost': '清空当前标签页配置',
} as const satisfies Record<string, UiMessageValue>

const zhMessages = {
  ...settingsZhMessages,
  ...chromeZhMessages,
  ...libraryZhMessages,
  ...relativeTimeZhMessages,
  ...llmZhMessages,
} as const satisfies Record<string, UiMessageValue>

type UiMessageCatalog = typeof zhMessages & typeof homeZhMessages & typeof novelZhMessages & typeof copilotZhMessages

export type UiMessageKey = Extract<keyof UiMessageCatalog, string>

const enMessages: Partial<Record<UiMessageKey, UiMessageValue>> = {
  'settings.title': 'Settings',
  'settings.section.appearance': 'Appearance',
  'settings.section.ai': 'AI model config',
  'settings.footer.version': APP_VERSION_LABEL,
  'settings.appearance.themeTitle': 'Theme mode',
  'settings.appearance.theme.dark': 'Dark mode',
  'settings.appearance.theme.light': 'Light mode',
  'settings.appearance.languageTitle': 'Interface language',
  'settings.appearance.languageDescription': 'Choose the display language for supported product surfaces.',
  'settings.appearance.language.zh': '简体中文',
  'settings.appearance.language.en': 'English',

  'navbar.features': 'Features',
  'navbar.docs': 'Docs',
  'navbar.library': 'Library',
  'navbar.settings': 'Settings',
  'footer.description': 'World-building and assisted writing for long-form fiction.',
  'dialog.confirm': 'Confirm',
  'dialog.cancel': 'Cancel',
  'dialog.gotIt': 'Got it',
  'plainText.loading': 'Loading...',
  'plainText.empty': 'No content yet',

  'library.create': 'New novel',
  'library.import': 'Import manuscript',
  'library.untitled': 'Untitled novel',
  'library.rename': 'Rename novel',
  'library.error.create': 'Could not create novel',
  'library.error.rename': 'Title could not be saved',
  'library.title': 'Library',
  'library.description': 'Start with a blank chapter or import a TXT or Markdown manuscript.',
  'library.error.load': 'Failed to load',
  'library.error.unknown': 'Unknown error',
  'library.error.uploadFailed': 'Upload failed',
  'library.error.uploadTooLarge': ({ maxMb }) => `The file is too large. Please upload a .txt file no larger than ${String(maxMb ?? 30)} MB.`,
  'library.error.uploadTypeNotSupported': 'Only .txt / .md novel files are supported right now.',
  'library.error.uploadParseFailed': 'The file uploaded, but NovWr could not parse it yet. Please clean up the chapter headings and try again.',
  'library.uploadOverlay.title': 'Uploading your novel',
  'library.uploadOverlay.description': 'Please wait. After the upload completes, NovWr will import the chapters and prepare the world data automatically.',
  'library.confirm.delete.title': 'Delete novel',
  'library.confirm.delete': 'Delete this novel? This action cannot be undone.',
  'library.empty.title': 'Your library is empty.',
  'library.workCard.meta': ({ chapterCount, relativeTime }) => `${String(chapterCount ?? 0)} ${Number(chapterCount) === 1 ? 'chapter' : 'chapters'} · updated ${String(relativeTime ?? '')}`,
  'library.workCard.delete': 'Delete',

  'time.justNow': 'just now',
  'time.minutesAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'minute' : 'minutes'} ago`,
  'time.hoursAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'hour' : 'hours'} ago`,
  'time.yesterday': 'yesterday',
  'time.daysAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'day' : 'days'} ago`,
  'time.weeksAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'week' : 'weeks'} ago`,
  'time.monthsAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'month' : 'months'} ago`,

  'llm.notice.selfhost': 'For safety, this configuration is kept only in the current browser tab’s memory and is cleared on refresh. If you want to use your own key long-term, self-host with Docker or environment variables instead.',
  'llm.notice.desktop': 'This configuration is encrypted on this computer and remains available after restarts or overwrite installs. The API key is never shown again.',
  'llm.warning.partialConfig': 'Only part of the BYOK config is filled in. Provide Base URL, API Key, and Model together; otherwise continuation, world generation, and extraction will be rejected.',
  'llm.error.missingLocalConfig': 'Configure an AI model in Settings before trying again.',
  'llm.error.incompleteConfig': 'The current BYOK config is incomplete. Fill in Base URL, API Key, and Model together, or clear the current config.',
  'llm.error.invalidBaseUrl': 'Base URL must be an absolute HTTP(S) address without credentials, query parameters, fragments, or whitespace.',
  'llm.error.invalidApiKey': 'API key format is invalid. Enter a valid key without whitespace or control characters.',
  'llm.error.modelUnavailable': 'The current model is unavailable. Check that Base URL, API Key, and Model match and that the endpoint supports JSON mode.',
  'llm.result.successFallback': ({ latencyMs }) => `Connection and compatibility check passed (${String(latencyMs ?? '')}ms)`,
  'llm.result.connectionFailed': 'Connection failed',
  'llm.result.providerConnectionFailed': 'The basic connection failed. Check that the Base URL, API key, and model match.',
  'llm.result.streamSupported': 'Streaming is supported.',
  'llm.result.jsonSupported': 'JSON mode is supported.',
  'llm.result.streamUnknown': 'Streaming could not be verified. Please retry.',
  'llm.result.jsonUnknown': 'JSON mode could not be verified. Please retry.',
  'llm.result.missingStreamCapability': 'The basic connection succeeded, but the endpoint does not support streaming, so continuation cannot work correctly.',
  'llm.result.missingJsonCapability': 'The basic connection succeeded, but the endpoint does not support JSON mode, so world generation and extraction cannot work correctly.',
  'llm.result.httpFailed': ({ status }) => `Request failed (HTTP ${String(status ?? '')})`,
  'llm.result.saved': 'AI model configuration saved',
  'llm.result.cleared': 'AI model configuration cleared',
  'llm.result.loadFailed': 'Could not load the local AI model configuration',
  'llm.confirm.clearTitle': 'Clear the local AI model configuration?',
  'llm.confirm.clearDescription': 'This deletes the encrypted Base URL, model, and API key. It cannot be recovered and must be entered again.',
  'llm.confirm.clearAction': 'Clear configuration',
  'llm.label.baseUrl': 'API Base URL',
  'llm.label.apiKey': 'API Key',
  'llm.label.model': 'Model name',
  'llm.placeholder.savedApiKey': 'Saved; leave blank to keep using it',
  'llm.status.apiKeyConfigured': 'An API key is saved. Leave this blank to keep it, or enter a new value to replace it.',
  'llm.button.saving': 'Saving...',
  'llm.button.save': 'Save configuration',
  'llm.button.testing': 'Testing...',
  'llm.button.test': 'Test connection',
  'llm.button.clearing': 'Clearing...',
  'llm.button.retry': 'Retry loading',
  'llm.button.clearDesktop': 'Clear local configuration',
  'llm.button.clearSelfhost': 'Clear current tab config',

}

function createEmptyUiMessageCatalog(): Record<UiLocale, Partial<Record<UiMessageKey, UiMessageValue>>> {
  return Object.fromEntries(
    SUPPORTED_UI_LOCALES.map((locale) => [locale, {}]),
  ) as Record<UiLocale, Partial<Record<UiMessageKey, UiMessageValue>>>
}

const baseUiMessages: Partial<Record<UiLocale, Partial<Record<UiMessageKey, UiMessageValue>>>> = {
  zh: zhMessages,
  en: enMessages,
}

export const uiMessages = createEmptyUiMessageCatalog()
for (const locale of SUPPORTED_UI_LOCALES) {
  const localeMessages = baseUiMessages[locale]
  if (!localeMessages) continue
  Object.assign(uiMessages[locale], localeMessages)
}

const registeredUiMessagePacks = new Set<object>()

export function registerUiMessages(
  messages: Partial<Record<UiLocale, Partial<Record<UiMessageKey, UiMessageValue>>>>,
): void {
  if (registeredUiMessagePacks.has(messages)) return
  registeredUiMessagePacks.add(messages)
  for (const locale of SUPPORTED_UI_LOCALES) {
    const localeMessages = messages[locale]
    if (!localeMessages) continue
    Object.assign(uiMessages[locale], localeMessages)
  }
}

function renderUiMessage(
  value: UiMessageValue,
  params: UiMessageParams | undefined,
): string {
  if (typeof value === 'function') {
    return value(params ?? {})
  }
  return value
}

export function translateUiMessage(
  locale: UiLocale,
  key: UiMessageKey,
  params?: UiMessageParams,
): string {
  for (const fallbackLocale of getUiLocaleFallbackChain(locale)) {
    const value = uiMessages[fallbackLocale][key]
    if (value) return renderUiMessage(value, params)
  }
  return `[missing:${String(key)}]`
}
