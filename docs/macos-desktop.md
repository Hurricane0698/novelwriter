# macOS 桌面构建

首版目标为 Apple Silicon、macOS 14 及以上。Tauri 使用系统 WKWebView 加载同源的本地前端，Python 3.13 后端和 Rust 索引扩展随应用分发。最低系统版本同时受 WebKit 和原生库约束；仅构建成功不能证明所有旧系统都已实测。

## 从源码构建

构建机需要原生 arm64 环境、Xcode Command Line Tools、Node.js 20.19.5、Rust 1.85.0 和 `.uv-version` 指定的 uv 0.10.4。各工具须在当前 shell 的 `PATH` 中；不要在 Rosetta 终端构建。脚本通过 uv 选择或下载受管理的独立 Python 3.13.12，保证本地与 CI 使用同一种发行版；不使用系统 Python.framework。依赖版本来自现有 npm、uv、Cargo 锁文件。

```bash
bash scripts/build_macos_desktop.sh
```

脚本使用独立的 `desktop/build/macos-venv`，构建前端、编译 Rust 扩展，再以 PyInstaller 生成运行时，最后构建 Tauri 应用和 DMG。运行时可以单独生成，也可以复用一个明确提供的运行时进行应用壳迭代：

```bash
bash scripts/build_macos_runtime.sh
bash scripts/build_macos_desktop.sh desktop/runtime-dist/macos/novwr-runtime
```

最终文件位于 `desktop/desktop-dist/macos/`：`NovWr.app`、版本化的 `*_aarch64.dmg`、`SHA256SUMS` 和 `BUILD_INFO.json`。构建信息记录源码提交、构建前工作区是否干净、是否重建运行时以及安装包摘要。校验程序检查必要资源、Rust 扩展、原生架构、签名及应用包结构。保持应用包完整，不要单独移动 `Contents/MacOS/NovWr` 或内部 Python 运行时。

## 安装与使用

打开 DMG，将 NovWr 拖到「应用程序」。应用随包内置后端，正常使用不依赖构建工具或仓库。首次运行在设置页配置 OpenAI 兼容接口；模型连接测试会检查普通请求、流式输出和 JSON 模式。

| 内容 | 位置或行为 |
| --- | --- |
| 正文、SQLite、持久运行时密钥 | `~/Library/Application Support/NovWr` |
| 日志 | `~/Library/Logs/NovWr` |
| 模型配置与 API Key | 当前用户 Keychain，按数据目录区分条目 |
| 关闭窗口 / `⌘W` | 隐藏现有窗口；Dock 或再次启动恢复 |
| `⌘Q` | 暂停编辑并等待正文保存成功，再关闭后端和应用；失败可重试、继续编辑或明确放弃保存 |
| 异常终止应用壳 | 进程守护逻辑回收对应后台进程组，释放本地端口 |

本地服务固定监听 `127.0.0.1:8000`。端口被其他程序占用时，应用显示启动错误；不会接管或停止其他服务。Windows 继续使用原有 Job Object、DPAPI 和 NSIS 构建，平台选择集中在适配层。

`MAX_CONCURRENT_LLM_CALLS` 和 `MAX_BACKGROUND_CONCURRENT_LLM_CALLS` 都是**每个 Python 进程**的容量限制。桌面应用的 server、worker 使用各自的许可池；总量设为 1 时，前台和后台仍可能各进行 1 个请求。它们不承诺应用级或供应商账号级硬上限；费用或供应商并发约束需要在共享 API 网关或供应商侧实施。详见 [并发配置](concurrency.md)。

## 验证

```bash
desktop/build/macos-venv/bin/python scripts/verify_macos_artifact.py \
  --app desktop/desktop-dist/macos/NovWr.app
desktop/build/macos-venv/bin/python scripts/smoke_macos_desktop.py \
  --app desktop/desktop-dist/macos/NovWr.app
```

烟测需要已登录的 macOS 图形会话、Node.js 和空闲的端口 8000。它启动完整应用，使用独立数据目录及本地受控模型接口，检查导入、Rust 索引、正文保存、Keychain、正常退出、重复启动、强制退出后的回收与重启。测试只删除自身创建的精确 Keychain 条目，保留独立测试目录和日志供检查，不会清空日常使用的数据。

`NOVWR_DESKTOP_DATA_ROOT` 可将所有业务数据与日志放到指定绝对路径；为隔离系统 WebKit 数据，设置该变量时使用非持久 WebView。此模式下浏览器缓存和 localStorage 不跨重启，SQLite 和 Keychain 仍会持久保存。日常使用无需设置此变量。

API 烟测不替代原生窗口检查。发布前仍需在目标 macOS 的真实应用窗口内确认首屏、导入、中文编辑与 `⌘` 快捷键、设置页、窗口关闭后 Dock 恢复，以及重启后的内容。CI 在 PR 和 main 推送时调用 `.github/workflows/build-macos-desktop.yml`，构建并烟测 arm64 安装包；PR 构建明确检出 PR 的 head commit。通过后从 Actions 的 `novwr-macos-desktop-arm64` artifact 下载 DMG、校验文件和构建信息，保存 7 天。该流程也支持手动调用；本地验证不代表远端 CI 已执行。

## 签名与分发

发布门禁还包括旧版本覆盖安装：在独立数据目录中先用旧包保存正文、配置和 Keychain 条目，再替换为新包，验证数据迁移、重启、设置读取和模型连接。沿用稳定签名身份；如系统要求 Keychain 授权，由用户处理，不放宽条目访问控制。新安装烟测不替代此升级路径。

当前配置使用 ad-hoc 签名，可构建并在本机运行，不代表通过 Developer ID 身份认证或 Apple 公证。对外正式分发需要为 Tauri 应用和内嵌 Python 可执行文件使用稳定的 Developer ID 签名，并对最终应用进行公证与 stapling。不能仅给外层应用重新签名而忽略内嵌运行时。

Keychain 使用系统默认访问控制。更换内嵌可执行文件签名后，系统可能要求用户重新授权读取原有条目；应用不会自动批准系统提示。测试时使用独立配置路径，避免开发构建访问已有真实密钥。详见 [Tauri macOS 签名文档](https://v2.tauri.app/distribute/sign/macos/) 和 [PyInstaller 6.16 macOS 签名说明](https://pyinstaller.org/en/v6.16.0/feature-notes.html#macos-binary-code-signing)。
