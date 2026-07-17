import {
  getUiLocaleFallbackChain,
  SUPPORTED_UI_LOCALES,
  type UiLocale,
} from '@/lib/uiLocaleSchema'
import type { copilotZhMessages } from '@/lib/uiMessagePacks/copilot'
import type { homeZhMessages } from '@/lib/uiMessagePacks/home'
import type { legalZhMessages } from '@/lib/uiMessagePacks/legal'
import type { novelZhMessages } from '@/lib/uiMessagePacks/novel'

export type { UiLocale } from '@/lib/uiLocaleSchema'

export type UiMessageParams = Record<string, string | number | boolean | null | undefined>
export type UiMessageValue = string | ((params: UiMessageParams) => string)

const APP_VERSION_LABEL = `NovWr v${__NOVWR_APP_VERSION__}`

const settingsZhMessages = {
  'settings.title': '设置',
  'settings.section.appearance': '外观',
  'settings.section.ai': 'AI 模型配置',
  'settings.section.account': '账户',
  'settings.footer.version': APP_VERSION_LABEL,
  'settings.appearance.themeTitle': '主题模式',
  'settings.appearance.theme.dark': '深色模式',
  'settings.appearance.theme.light': '浅色模式',
  'settings.appearance.languageTitle': '界面语言',
  'settings.appearance.languageDescription': '切换受支持产品界面的显示语言。',
  'settings.appearance.language.zh': '简体中文',
  'settings.appearance.language.en': 'English',
  'settings.account.nickname': '昵称',
  'settings.account.remainingQuota': '剩余生成次数',
  'settings.account.feedbackReward': '提交反馈可获得额外生成额度',
  'settings.account.submitFeedback': '提交反馈',
  'settings.account.logout': '退出登录',
} as const satisfies Record<string, UiMessageValue>

const chromeZhMessages = {
  'navbar.features': '功能',
  'navbar.library': '作品库',
  'navbar.settings': '设置',
  'navbar.login': '登录',
  'footer.link.terms': '用户规则',
  'footer.link.privacy': '隐私说明',
  'footer.link.copyright': '版权投诉',
  'footer.description': '面向长篇创作的 AI 辅助写作与续写工具。使用本服务前，请阅读相关规则、隐私说明与版权投诉说明。',
  'dialog.confirm': '确认',
  'dialog.cancel': '取消',
  'dialog.gotIt': '知道了',
  'plainText.loading': '加载中...',
  'plainText.empty': '暂无内容',
} as const satisfies Record<string, UiMessageValue>

const loginZhMessages = {
  'login.header.hosted': '首次使用请用邀请码激活；之后可用昵称、密码或 GitHub 登录',
  'login.header.hostedInviteOnly': '首次使用请用邀请码激活；之后用昵称和密码登录',
  'login.oauth.disabled': '当前内测暂不开放 GitHub 登录。',
  'login.oauth.githubNotConfigured': 'GitHub 登录暂未配置，请稍后再试。',
  'login.oauth.stateInvalid': '登录状态已失效，请重新点击 GitHub 登录。',
  'login.oauth.accessDenied': '你已取消 GitHub 授权，未完成登录。',
  'login.oauth.signupBlocked': '当前暂不接受新的 GitHub 注册，请稍后再试。',
  'login.oauth.accountDisabled': '该账户已被停用，请联系管理员。',
  'login.oauth.failed': 'GitHub 登录失败，请稍后重试。',
  'login.github.button': '使用 GitHub 登录',
  'login.invite.or': '或使用其他方式',
  'login.invite.code.label': '邀请码',
  'login.invite.code.placeholder': '填写你收到的专属邀请码（仅首次激活使用）',
  'login.invite.nickname.label': '昵称',
  'login.invite.nickname.placeholder': '首次使用时填写你的显示名称',
  'login.hosted.mode.login': '已有账号登录',
  'login.hosted.mode.activate': '首次激活',
  'login.hosted.loginHint': '如果你已经激活过账号，请直接用昵称和密码登录。',
  'login.hosted.activateHint': '邀请码只用于首次激活。激活完成后，请用昵称和密码登录。',
  'login.hosted.nickname.placeholder': '输入你激活时设置的昵称',
  'login.hosted.password.activatePlaceholder': '首次设置一个登录密码',
  'login.hosted.password.loginPlaceholder': '输入你的登录密码',
  'login.hosted.password.hint': '至少填写 8 位。激活完成后，后续就用昵称和密码登录。',
  'login.hosted.password.minLengthError': '密码必须至少填写 8 位。',
  'login.hosted.nickname.requiredError': '请先填写昵称。',
  'login.hosted.invite.requiredError': '请先填写邀请码。',
  'login.hosted.activation.genericError': '激活失败，请检查填写内容后重试。',
  'login.hosted.activation.networkError': '无法连接到后端，请确认服务已启动后再试。',
  'login.username.label': '用户名',
  'login.password.label': '密码',
  'login.submit.loading': '请稍候...',
  'login.submit.activate': '激活并进入',
  'login.submit.hostedLogin': '登录',
  'login.requestIdSuffix': ({ requestId }) => `（Request ID: ${String(requestId ?? '')}）`,
  'login.alert.invalidInvite.title': '邀请码无效',
  'login.alert.invalidInvite.description': '请检查邀请码是否正确',
  'login.alert.inviteClaimed.title': '邀请码已被激活',
  'login.alert.inviteClaimed.description': '这个邀请码已经完成首次激活。请改用你的昵称和密码登录。',
  'login.alert.nicknameTaken.title': '昵称已被占用',
  'login.alert.nicknameTaken.description': '这个昵称已经被其他账号使用，请换一个昵称后再激活。',
  'login.alert.signupBlocked.title': '注册已暂停',
  'login.alert.signupBlocked.description': '当前暂不接受新的注册，请稍后再试',
  'login.alert.invalidCredentials.title': '登录失败',
  'login.alert.invalidCredentials.description': '昵称或密码错误',
  'login.alert.backend404.title': '连接失败',
  'login.alert.backend404.description': '无法连接到后端（/api 404）。如果你在 WSL + Windows 浏览器开发，请确认后端已启动，并重启前端 dev server 以生效 Vite /api 代理。',
  'login.alert.httpFailure.title': '操作失败',
  'login.alert.httpFailure.description': ({ status }) => `请求失败（HTTP ${String(status ?? '')}）。请稍后重试`,
  'login.alert.network.title': '连接失败',
  'login.alert.network.description': '无法连接到后端，请确认后端已启动（以及前端是否通过 /api 代理）。',
} as const satisfies Record<string, UiMessageValue>

const libraryZhMessages = {
  'library.create': '新建作品',
  'library.title': '我的作品库',
  'library.description': '管理你的所有小说作品',
  'library.demo.badge': '引导演示',
  'library.demo.title': '先跑一遍示例，再导入你的正文',
  'library.demo.description': ({ title }) => `先打开「${String(title ?? '')}」这部示例，快速理解世界模型、Studio 续写和全书检索是如何协同工作的。`,
  'library.demo.description.inProgress': ({ title, current, total }) => `「${String(title ?? '')}」的示例引导已完成 ${String(current ?? 0)}/${String(total ?? 4)} 步。继续进入 Studio，把世界模型、续写台和 Copilot 走完一遍。`,
  'library.demo.description.completed': ({ title }) => `你已经完成「${String(title ?? '')}」的示例引导。可以随时重新查看，也可以直接上传你自己的正文。`,
  'library.demo.description.skipped': ({ title }) => `你之前收起了「${String(title ?? '')}」的示例引导。随时可以重新打开，或者直接上传你自己的正文。`,
  'library.demo.open': '打开引导演示',
  'library.demo.start': '开始引导',
  'library.demo.resume': '继续引导',
  'library.demo.reopen': '重新查看',
  'library.demo.upload': '上传我的 txt',
  'library.error.load': '加载失败',
  'library.error.unknown': '未知错误',
  'library.error.uploadFailed': '上传失败',
  'library.error.uploadTooLarge': ({ maxMb }) => `文件过大，请上传不超过 ${String(maxMb ?? 30)} MB 的 txt 文本文件`,
  'library.error.uploadTypeNotSupported': '仅支持上传 txt 文本文件',
  'library.error.uploadParseFailed': '文件已上传，但暂时无法解析。请确认章节标题格式清晰后重试。',
  'library.uploadOverlay.title': '正在上传小说',
  'library.uploadOverlay.description': '请稍候。上传完成后，NovWr 会继续导入章节并自动准备世界信息。',
  'library.confirm.delete': '确定要删除这部作品吗？此操作不可撤销。',
  'library.empty.title': '还没有作品，开始创作你的第一部小说吧',
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
  'llm.notice.hosted': '当前 hosted beta 只使用平台托管的 AI 凭证，不接受浏览器侧 BYOK 覆盖。续写、世界生成、bootstrap 和后台任务都会走同一套平台配置；如果你需要自带模型密钥，请改用 Docker / 环境变量自部署。',
  'llm.notice.selfhost': '出于安全考虑，这里的配置只保留在当前浏览器标签页内存中；刷新页面后会清空。如果你想长期使用自己的 Key，推荐改用 Docker / 环境变量自部署。',
  'llm.notice.desktop': '配置会加密保存在这台电脑上，重启应用或覆盖安装后仍可使用。API Key 不会在界面中回显。',
  'llm.warning.partialConfig': '当前只填写了部分 BYOK 配置。请同时填写 Base URL、API Key 和 Model；否则续写、世界生成和提取都会被拒绝。',
  'llm.error.missingLocalConfig': '请先在设置中配置 AI 模型。',
  'llm.error.missingHostedConfig': '平台 AI 服务尚未配置，请稍后再试或联系服务管理员。',
  'llm.error.incompleteConfig': '当前 BYOK 配置不完整，请同时填写 Base URL、API Key 和 Model，或清空当前配置。',
  'llm.error.incompleteHostedConfig': '平台 AI 服务配置不完整，请稍后再试或联系服务管理员。',
  'llm.error.invalidBaseUrl': 'Base URL 必须是完整的 HTTP(S) 地址，且不能包含账号密码、查询参数、片段或空白字符。',
  'llm.error.invalidApiKey': 'API Key 格式无效。请重新填写不含空白或控制字符的有效 Key。',
  'llm.error.aiDisabled': '当前实例已关闭 AI 功能，暂时无法发起模型请求。',
  'llm.error.budgetHardStop': '当前实例的托管 AI 额度已达上限，请稍后再试，或改用你自己的 API Key。',
  'llm.error.budgetUnavailable': '当前实例暂时关闭了托管 AI 请求，请稍后再试，或改用你自己的 API Key。',
  'llm.error.modelUnavailable': '当前模型不可用。请检查 Base URL、API Key、Model 是否匹配，并确认接口支持 JSON 模式。',
  'llm.result.successFallback': ({ latencyMs }) => `连接与应用兼容性检测通过 (${String(latencyMs ?? '')}ms)`,
  'llm.result.connectionFailed': '连接失败',
  'llm.result.providerConnectionFailed': '基础连接失败。请检查 Base URL、API Key 和 Model 是否匹配。',
  'llm.result.missingStreamCapability': '基础连接成功，但接口不支持流式输出，续写功能无法正常使用。',
  'llm.result.missingJsonCapability': '基础连接成功，但接口不支持 JSON 模式，世界生成和提取功能无法正常使用。',
  'llm.result.missingStreamAndJsonCapabilities': '基础连接成功，但接口不支持流式输出和 JSON 模式，当前无法用于 NovWr。',
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

const feedbackZhMessages = {
  'feedback.title': '使用反馈',
  'feedback.description': '填写以下反馈即可获得额外生成额度。你的反馈对我们非常重要。',
  'feedback.question.rating': '1. 整体体验如何？',
  'feedback.question.issues': '2. 遇到了什么问题？（可多选）',
  'feedback.question.suggestion': '3. 改进建议（可选）',
  'feedback.rating.great': '很好，超出预期',
  'feedback.rating.good': '还不错，有潜力',
  'feedback.rating.okay': '一般，需要改进',
  'feedback.rating.poor': '不太行，问题较多',
  'feedback.issue.speed': '生成速度太慢',
  'feedback.issue.quality': '生成文本质量不够好',
  'feedback.issue.ux': '操作流程不够直观',
  'feedback.issue.bugs': '遇到了 Bug',
  'feedback.issue.other': '其他问题',
  'feedback.issue.none': '暂时没有明显问题',
  'feedback.placeholder.bug': '简要描述一下遇到的 Bug，例如：上传小说后页面白屏',
  'feedback.placeholder.other': '具体是什么问题？',
  'feedback.placeholder.suggestion': '有什么想法或建议？',
  'feedback.bonus.max': '提交可获得 30 次额度',
  'feedback.bonus.upgrade': '填写不少于 20 字的建议，额度从 20 次提升至 30 次',
  'feedback.submit.loading': '提交中...',
  'feedback.submit.button': ({ count }) => `提交反馈，获得 ${String(count ?? 20)} 次额度`,
} as const satisfies Record<string, UiMessageValue>

const zhMessages = {
  ...settingsZhMessages,
  ...chromeZhMessages,
  ...loginZhMessages,
  ...libraryZhMessages,
  ...relativeTimeZhMessages,
  ...llmZhMessages,
  ...feedbackZhMessages,
} as const satisfies Record<string, UiMessageValue>

type UiMessageCatalog = typeof zhMessages & typeof homeZhMessages & typeof novelZhMessages & typeof copilotZhMessages & typeof legalZhMessages

export type UiMessageKey = Extract<keyof UiMessageCatalog, string>

const enMessages: Partial<Record<UiMessageKey, UiMessageValue>> = {
  'settings.title': 'Settings',
  'settings.section.appearance': 'Appearance',
  'settings.section.ai': 'AI model config',
  'settings.section.account': 'Account',
  'settings.footer.version': APP_VERSION_LABEL,
  'settings.appearance.themeTitle': 'Theme mode',
  'settings.appearance.theme.dark': 'Dark mode',
  'settings.appearance.theme.light': 'Light mode',
  'settings.appearance.languageTitle': 'Interface language',
  'settings.appearance.languageDescription': 'Choose the display language for supported product surfaces.',
  'settings.appearance.language.zh': '简体中文',
  'settings.appearance.language.en': 'English',
  'settings.account.nickname': 'Nickname',
  'settings.account.remainingQuota': 'Remaining generations',
  'settings.account.feedbackReward': 'Submit feedback to unlock extra generation quota',
  'settings.account.submitFeedback': 'Submit feedback',
  'settings.account.logout': 'Log out',

  'navbar.features': 'Features',
  'navbar.library': 'Library',
  'navbar.settings': 'Settings',
  'navbar.login': 'Log in',
  'footer.link.terms': 'Terms of use',
  'footer.link.privacy': 'Privacy notice',
  'footer.link.copyright': 'Copyright notice',
  'footer.description': 'An AI-assisted writing and continuation tool for long-form fiction. Please read the terms, privacy notice, and copyright notice before using the service.',
  'dialog.confirm': 'Confirm',
  'dialog.cancel': 'Cancel',
  'dialog.gotIt': 'Got it',
  'plainText.loading': 'Loading...',
  'plainText.empty': 'No content yet',

  'login.header.hosted': 'Use an invite code once to activate, then sign in with nickname and password or GitHub',
  'login.header.hostedInviteOnly': 'Use an invite code once to activate, then sign in with nickname and password',
  'login.oauth.disabled': 'GitHub sign-in is not available in this beta right now.',
  'login.oauth.githubNotConfigured': 'GitHub sign-in is not configured yet. Please try again later.',
  'login.oauth.stateInvalid': 'Your login state expired. Please click GitHub sign-in again.',
  'login.oauth.accessDenied': 'You canceled GitHub authorization, so sign-in was not completed.',
  'login.oauth.signupBlocked': 'New GitHub sign-ups are currently paused. Please try again later.',
  'login.oauth.accountDisabled': 'This account has been disabled. Please contact the administrator.',
  'login.oauth.failed': 'GitHub sign-in failed. Please try again later.',
  'login.github.button': 'Continue with GitHub',
  'login.invite.or': 'or use another method',
  'login.invite.code.label': 'Invite code',
  'login.invite.code.placeholder': 'Enter the personal invite code you received (first activation only)',
  'login.invite.nickname.label': 'Nickname',
  'login.invite.nickname.placeholder': 'Your display name on first use',
  'login.hosted.mode.login': 'Sign in',
  'login.hosted.mode.activate': 'Activate',
  'login.hosted.loginHint': 'If you already activated your account, sign in directly with nickname and password.',
  'login.hosted.activateHint': 'Invite codes are only for first-time activation. After that, sign in with nickname and password.',
  'login.hosted.nickname.placeholder': 'Enter the nickname you activated with',
  'login.hosted.password.activatePlaceholder': 'Set a password for future sign-ins',
  'login.hosted.password.loginPlaceholder': 'Enter your password',
  'login.hosted.password.hint': 'Use at least 8 characters. After activation, you will sign in with nickname and password.',
  'login.hosted.password.minLengthError': 'Password must be at least 8 characters.',
  'login.hosted.nickname.requiredError': 'Please enter a nickname first.',
  'login.hosted.invite.requiredError': 'Please enter an invite code first.',
  'login.hosted.activation.genericError': 'Activation failed. Please check your inputs and try again.',
  'login.hosted.activation.networkError': 'The frontend could not reach the backend. Please make sure the service is running and try again.',
  'login.username.label': 'Username',
  'login.password.label': 'Password',
  'login.submit.loading': 'Please wait...',
  'login.submit.activate': 'Activate and enter',
  'login.submit.hostedLogin': 'Log in',
  'login.requestIdSuffix': ({ requestId }) => ` (Request ID: ${String(requestId ?? '')})`,
  'login.alert.invalidInvite.title': 'Invalid invite code',
  'login.alert.invalidInvite.description': 'Please check whether the invite code is correct',
  'login.alert.inviteClaimed.title': 'Invite code already activated',
  'login.alert.inviteClaimed.description': 'This invite code has already completed first-time activation. Please sign in with your nickname and password instead.',
  'login.alert.nicknameTaken.title': 'Nickname already taken',
  'login.alert.nicknameTaken.description': 'That nickname is already in use by another account. Please choose a different one before activating.',
  'login.alert.signupBlocked.title': 'Sign-ups are paused',
  'login.alert.signupBlocked.description': 'New registrations are currently unavailable. Please try again later',
  'login.alert.invalidCredentials.title': 'Sign-in failed',
  'login.alert.invalidCredentials.description': 'Incorrect nickname or password',
  'login.alert.backend404.title': 'Connection failed',
  'login.alert.backend404.description': 'The frontend could not reach the backend (/api returned 404). If you develop with WSL + a Windows browser, make sure the backend is running, then restart the frontend dev server so the Vite /api proxy takes effect.',
  'login.alert.httpFailure.title': 'Request failed',
  'login.alert.httpFailure.description': ({ status }) => `The request failed (HTTP ${String(status ?? '')}). Please try again later`,
  'login.alert.network.title': 'Connection failed',
  'login.alert.network.description': 'The frontend could not reach the backend. Please make sure the backend is running and that the frontend is using the /api proxy.',

  'library.create': 'New novel',
  'library.title': 'Library',
  'library.description': 'Manage all of your novels',
  'library.demo.badge': 'Guided sample',
  'library.demo.title': 'Try the sample first, then import your own work',
  'library.demo.description': ({ title }) => `Open “${String(title ?? '')}” first to learn how the world model, Studio continuation, and whole-book retrieval fit together.`,
  'library.demo.description.inProgress': ({ title, current, total }) => `The guided sample “${String(title ?? '')}” is ${String(current ?? 0)}/${String(total ?? 4)} steps in. Jump back into Studio to finish the world model, continuation, and Copilot loop.`,
  'library.demo.description.completed': ({ title }) => `You have already finished the guided sample for “${String(title ?? '')}”. Reopen it anytime, or move on and import your own manuscript.`,
  'library.demo.description.skipped': ({ title }) => `You previously hid the guided sample for “${String(title ?? '')}”. You can reopen it anytime, or move on and import your own manuscript.`,
  'library.demo.open': 'Open guided sample',
  'library.demo.start': 'Start guide',
  'library.demo.resume': 'Resume guide',
  'library.demo.reopen': 'Review guide',
  'library.demo.upload': 'Upload my .txt',
  'library.error.load': 'Failed to load',
  'library.error.unknown': 'Unknown error',
  'library.error.uploadFailed': 'Upload failed',
  'library.error.uploadTooLarge': ({ maxMb }) => `The file is too large. Please upload a .txt file no larger than ${String(maxMb ?? 30)} MB.`,
  'library.error.uploadTypeNotSupported': 'Only .txt novel files are supported right now.',
  'library.error.uploadParseFailed': 'The file uploaded, but NovWr could not parse it yet. Please clean up the chapter headings and try again.',
  'library.uploadOverlay.title': 'Uploading your novel',
  'library.uploadOverlay.description': 'Please wait. After the upload completes, NovWr will import the chapters and prepare the world data automatically.',
  'library.confirm.delete': 'Delete this novel? This action cannot be undone.',
  'library.empty.title': 'No novels yet—start writing your first one.',
  'library.workCard.meta': ({ chapterCount, relativeTime }) => `${String(chapterCount ?? 0)} ${Number(chapterCount) === 1 ? 'chapter' : 'chapters'} · updated ${String(relativeTime ?? '')}`,
  'library.workCard.delete': 'Delete',

  'time.justNow': 'just now',
  'time.minutesAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'minute' : 'minutes'} ago`,
  'time.hoursAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'hour' : 'hours'} ago`,
  'time.yesterday': 'yesterday',
  'time.daysAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'day' : 'days'} ago`,
  'time.weeksAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'week' : 'weeks'} ago`,
  'time.monthsAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'month' : 'months'} ago`,

  'llm.notice.hosted': 'Hosted beta uses platform-managed AI credentials only and does not accept browser-side BYOK overrides. Continuation, world generation, bootstrap, and background jobs all share the same platform config; if you need your own model credentials, self-host with Docker or environment variables.',
  'llm.notice.selfhost': 'For safety, this configuration is kept only in the current browser tab’s memory and is cleared on refresh. If you want to use your own key long-term, self-host with Docker or environment variables instead.',
  'llm.notice.desktop': 'This configuration is encrypted on this computer and remains available after restarts or overwrite installs. The API key is never shown again.',
  'llm.warning.partialConfig': 'Only part of the BYOK config is filled in. Provide Base URL, API Key, and Model together; otherwise continuation, world generation, and extraction will be rejected.',
  'llm.error.missingLocalConfig': 'Configure an AI model in Settings before trying again.',
  'llm.error.missingHostedConfig': 'The hosted AI service is not configured. Try again later or contact the service operator.',
  'llm.error.incompleteConfig': 'The current BYOK config is incomplete. Fill in Base URL, API Key, and Model together, or clear the current config.',
  'llm.error.incompleteHostedConfig': 'The hosted AI service configuration is incomplete. Try again later or contact the service operator.',
  'llm.error.invalidBaseUrl': 'Base URL must be an absolute HTTP(S) address without credentials, query parameters, fragments, or whitespace.',
  'llm.error.invalidApiKey': 'API key format is invalid. Enter a valid key without whitespace or control characters.',
  'llm.error.aiDisabled': 'AI is disabled on this instance, so model requests are unavailable right now.',
  'llm.error.budgetHardStop': 'This instance has exhausted its hosted AI budget. Please try again later or switch to your own API key.',
  'llm.error.budgetUnavailable': 'Hosted AI requests are temporarily unavailable on this instance. Please try again later or switch to your own API key.',
  'llm.error.modelUnavailable': 'The current model is unavailable. Check that Base URL, API Key, and Model match and that the endpoint supports JSON mode.',
  'llm.result.successFallback': ({ latencyMs }) => `Connection and compatibility check passed (${String(latencyMs ?? '')}ms)`,
  'llm.result.connectionFailed': 'Connection failed',
  'llm.result.providerConnectionFailed': 'The basic connection failed. Check that the Base URL, API key, and model match.',
  'llm.result.missingStreamCapability': 'The basic connection succeeded, but the endpoint does not support streaming, so continuation cannot work correctly.',
  'llm.result.missingJsonCapability': 'The basic connection succeeded, but the endpoint does not support JSON mode, so world generation and extraction cannot work correctly.',
  'llm.result.missingStreamAndJsonCapabilities': 'The basic connection succeeded, but the endpoint supports neither streaming nor JSON mode, so it cannot be used with NovWr.',
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

  'feedback.title': 'Product feedback',
  'feedback.description': 'Submit the form below to earn extra generation quota. Your feedback helps us a lot.',
  'feedback.question.rating': '1. How was the overall experience?',
  'feedback.question.issues': '2. What issues did you run into? (Multiple choice)',
  'feedback.question.suggestion': '3. Improvement ideas (optional)',
  'feedback.rating.great': 'Great, exceeded expectations',
  'feedback.rating.good': 'Pretty good, promising',
  'feedback.rating.okay': 'Average, needs work',
  'feedback.rating.poor': 'Not great, too many problems',
  'feedback.issue.speed': 'Generation is too slow',
  'feedback.issue.quality': 'Text quality is not good enough',
  'feedback.issue.ux': 'The workflow is not intuitive enough',
  'feedback.issue.bugs': 'I hit a bug',
  'feedback.issue.other': 'Other issue',
  'feedback.issue.none': 'No obvious issue for now',
  'feedback.placeholder.bug': 'Briefly describe the bug, for example: the page turned blank after uploading a novel',
  'feedback.placeholder.other': 'What exactly went wrong?',
  'feedback.placeholder.suggestion': 'Any ideas or suggestions?',
  'feedback.bonus.max': 'Submit now to get 30 extra generations',
  'feedback.bonus.upgrade': 'Write at least 20 characters of suggestions to raise the reward from 20 to 30 generations',
  'feedback.submit.loading': 'Submitting...',
  'feedback.submit.button': ({ count }) => `Submit feedback and get ${String(count ?? 20)} extra generations`,

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
