# 桌面版安装指南

桌面版已经包含后端和索引引擎，无需安装 Python、Rust 或 Docker。当前提供 Windows x64 和 macOS Apple Silicon 安装包；Intel Mac 暂无安装包。

## Windows

适用于 Windows 10（2004 及以上）和 Windows 11 x64。

1. 在 [最新版本](https://github.com/Hurricane0698/novelwriter/releases/latest) 下载以 `_x64-setup.exe` 结尾的安装包。
2. 双击安装。应用安装到当前用户目录，无需管理员权限。
3. 打开 NovWr，在「设置 → AI 模型配置」填写接口地址、模型和 API Key，点击「测试连接」。不使用 AI 时也可以导入、阅读和编辑正文。

安装包会检查 WebView2；缺少时自动引导安装，需要联网下载。Windows 11 通常已包含此组件，详见 [微软 WebView2 分发说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)。

当前 Windows 安装包未做代码签名。如果 SmartScreen 显示「Windows 已保护你的电脑」，确认下载来自本仓库的 Release 后，可选择「更多信息 → 仍要运行」。

## macOS

适用于 macOS 14 及以上、Apple Silicon（M 系列）Mac。可在苹果菜单的「关于本机」查看芯片与系统版本。

1. 在 [最新版本](https://github.com/Hurricane0698/novelwriter/releases/latest) 下载以 `_aarch64.dmg` 结尾的安装包。
2. 打开 DMG，将 NovWr 拖入「应用程序」，然后从「应用程序」打开 NovWr。
3. 在「设置 → AI 模型配置」填写接口地址、模型和 API Key，点击「测试连接」。

当前 macOS 安装包使用 ad-hoc 签名，尚未经过 Apple 公证。如果首次打开时提示无法验证开发者，确认下载来源后，在「系统设置 → 隐私与安全性」找到 NovWr，选择「仍要打开」并确认。该入口需要先尝试打开应用才会出现。若系统明确报告应用损坏或包含恶意软件，请重新核对下载与系统提示，不要按普通开发者提示处理。详见 [Apple 的 App 打开说明](https://support.apple.com/zh-cn/102445)。

关闭窗口或按 `⌘W` 会隐藏窗口；点击 Dock 图标可恢复。按 `⌘Q` 会等待正文保存后退出；保存失败时，可以重试、继续编辑或明确放弃尚未保存的修改。

## 更新与数据

应用目前通过下载新版安装包更新。

1. 等待正文保存完成，退出 NovWr。备份重要小说或数据目录。
2. Windows 直接运行新版安装包；macOS 将新版 NovWr 拖入「应用程序」并替换旧应用。
3. 重新打开并确认小说与模型设置。更新 macOS 应用后，系统可能要求重新授权读取钥匙串中的模型配置；请在系统对话框中处理。

覆盖安装保留独立数据目录，无需先卸载。不要删除以下目录：

| 内容 | Windows | macOS |
| --- | --- | --- |
| 小说与数据库 | `%LOCALAPPDATA%\NovWr` 下的数据目录 | `~/Library/Application Support/NovWr` |
| 日志 | `%LOCALAPPDATA%\NovWr\logs` | `~/Library/Logs/NovWr` |
| 模型配置与 API Key | 当前用户的 DPAPI 加密配置 | 当前用户的 macOS 钥匙串 |

桌面版使用本机端口 `8000`。如果启动时提示端口占用，请先退出占用该端口的另一份 NovWr 或本地服务，再重新打开。

Release 同时提供 `SHA256SUMS` 和 `BUILD_INFO.json`，可用于核对安装包完整性、源码版本和构建来源。
