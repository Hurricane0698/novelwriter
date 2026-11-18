<div align="center">

<picture>
  <img src="docs/banner.png"  width="80%" />
</picture>

**为长篇小说续写而做的世界模型引擎**

<p>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPLv3-blue?style=flat-square" alt="License" /></a>
  <a href="https://github.com/Hurricane0698/novelwriter/releases/download/v0.6.0/NovWr_0.6.0_x64-setup.exe"><img src="https://img.shields.io/badge/download-Windows-0078D4?style=flat-square" alt="下载 Windows 桌面版" /></a>
  <a href="https://github.com/Hurricane0698/novelwriter/releases/download/v0.6.0/NovWr_0.6.0_aarch64.dmg"><img src="https://img.shields.io/badge/download-macOS%20Apple%20Silicon-222222?style=flat-square&logo=apple&logoColor=white" alt="下载 macOS 桌面版" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/frontend-React%2019-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React 19" /></a>
</p>

</div>

NovelWriter（NovWr）是一个非商业化的开源写作项目，提供 Windows、macOS 桌面版和 Docker 自部署方式。它帮助长篇小说作者在续写时核对人物、关系和世界设定。

做法是把设定从散落的备忘录变成一个结构化的世界模型——实体、关系、体系——每次续写时只把当前章节真正需要的设定注入给模型。写什么、采不采纳，始终由作者决定。

<div align="center">
<br />
<img src="docs/screenshot.jpg" alt="NovWr Studio 工作区" width="90%" />
<br />
<sub>Studio 工作区：章节栏 · 阅读与编辑 · 续写设置 / Atlas / 助手按需切换</sub>
<br /><br />
<table>
  <tr>
    <td align="center" width="50%"><img src="web/public/screenshots/home/atlas-light.jpg" alt="Atlas 世界模型" width="100%" /><br /><sub>Atlas：实体、关系与审核</sub></td>
    <td align="center" width="50%"><img src="web/public/screenshots/home/continuation-light.jpg" alt="续写工作流" width="100%" /><br /><sub>续写：按当前章节注入世界模型</sub></td>
  </tr>
</table>
<br /><br />
</div>

## 快速开始

### 桌面版（推荐）

下载后直接安装，无需命令行、Python、Rust 或 Docker。

| 系统 | 下载 v0.6.0 | 安装方式 |
| --- | --- | --- |
| Windows 10（2004+）/ 11，x64 | [下载 Windows 安装包](https://github.com/Hurricane0698/novelwriter/releases/download/v0.6.0/NovWr_0.6.0_x64-setup.exe) | 双击安装，当前用户安装无需管理员权限 |
| macOS 14+，Apple Silicon（M 系列） | [下载 macOS DMG](https://github.com/Hurricane0698/novelwriter/releases/download/v0.6.0/NovWr_0.6.0_aarch64.dmg) | 打开 DMG，将 NovWr 拖入「应用程序」 |

打开 NovWr，在作品库选择「新建作品」即可写第一章，也可以用「导入书稿」打开 TXT 或 Markdown。Markdown 可以用 `# 章节名` 分章，分卷书稿用 `# 卷名` 和 `## 章节名`。需要 AI 续写时，在「设置 → AI 模型配置」填写 OpenAI 兼容接口并测试连接。

当前安装包尚未完成 Windows 代码签名 / Apple 公证，首次运行可能出现系统安全提示。提示处理、数据位置和覆盖升级步骤见 [桌面版安装指南](docs/desktop-install.md)。全部安装包和更新说明见 [Releases](https://github.com/Hurricane0698/novelwriter/releases/latest)。

### Docker 自部署

适合 Linux、服务器或希望自行管理服务的用户。

**一键安装**

需要本机已安装 Docker；不需要 Git。

```bash
curl -fsSL https://raw.githubusercontent.com/Hurricane0698/novelwriter/main/install.sh | bash
```

脚本会安装 `uv` 与 `novwr` CLI，初始化 `~/.novwr`，并拉起官方镜像。常用命令：`novwr init` / `run` / `doctor` / `upgrade` / `uninstall`。

**Docker Compose v2.24+（手动）**

```bash
git clone https://github.com/Hurricane0698/novelwriter.git
cd novelwriter
cp .env.example .env   # 填入 LLM API 配置
docker compose up -d   # 访问 http://localhost:8000
```

### Selfhost 说明

- 默认 `selfhost` 模式，前后端集成，仅监听 `127.0.0.1:8000`
- Compose 同时启动 Web 服务与后台 worker（导入、索引、自动提取由 worker 处理）
- 首次启动自动创建管理员账号，并内置《西游记》示例项目
- 需要一个 OpenAI 接口兼容的 LLM API Key；设置页有「测试连接」做连通性与 JSON Mode 预检
- 官方镜像：`ghcr.io/hurricane0698/novelwriter:latest`

## 核心概念

**世界模型** 记录后文要用的事实，例如谁保管钥匙、谁知道一个秘密、哪条承诺尚未兑现。续写根据最近的正文和作者指令选取已确认设定。场景提到某人的关系时，可以带出另一端的人物。体系默认在场景相关时使用，也可以在 Atlas 中指定每次续写使用或隐藏。

**Studio 与 Atlas** 分别用于写作和维护设定。导入的章节一旦可读，就能开始编辑。全书索引和设定提取在后台进行。续写候选只有在作者采纳后才成为章节。

**写作助手** 可以检索前文、核对草稿。章节上的「本章改变了什么？」会保存正文并提出有原文依据的设定变化。作者可以逐条比较原值、建议值和出处，再决定是否采纳。

## 配置

Selfhost 常用环境变量（完整清单见 [`.env.example`](.env.example)）：

| 变量 | 说明 |
|---|---|
| `OPENAI_API_KEY` | LLM API 密钥（启用 AI 时必填） |
| `OPENAI_BASE_URL` / `OPENAI_MODEL` | 兼容网关地址与默认模型 |
| `JWT_SECRET_KEY` | JWT 签名密钥（用于本地会话） |
| `DATABASE_URL` | 数据库连接；默认 SQLite |
| `MAX_CONTEXT_CHAPTERS` / `DEFAULT_CONTINUATION_TOKENS` | 续写上下文与长度上限 |

## 本地开发

后端（Python 环境由 `pyproject.toml` + `uv.lock` + repo 内 `.venv` 唯一确定）：

```bash
scripts/setup_python_env.sh
cp .env.example .env
scripts/uv_run.sh uvicorn app.main:app --reload --port 8000
scripts/uv_run.sh pytest tests/          # 单元测试
```

`setup_python_env.sh` 会确保 `_novwr_state_proto` Rust 扩展就位；缺少 Rust toolchain 会直接失败并给出提示。

前端（开发服务器 `http://localhost:5173`，经 Vite 代理访问后端）：

```bash
cd web
npm ci
npm run dev
```

技术栈：FastAPI · SQLAlchemy · SQLite/PostgreSQL · React 19 · TypeScript · Tailwind · Docker。

桌面端开发与打包见 [macOS 桌面构建](docs/macos-desktop.md)；Windows 构建入口为 `scripts/build_windows_desktop.ps1`。发布标签会同时构建并验证两端安装包，通过后附到同一份 Release 草稿，确认安装包后再发布。

## 反馈与协作

本仓库是 NovelWriter 的稳定发布仓库，用于版本发布、问题反馈与社区协作。

- **Bug 反馈**：请附版本号、部署方式、模型供应商与复现路径
- **功能建议**：描述你的创作场景与具体痛点
- **PR**：常规修复欢迎直接提交；重大架构改动建议先开 Issue 对齐

觉得有用的话，欢迎点个 Star。

## 开源协议

[AGPLv3](LICENSE)

## 友情链接

[Linux.do](https://linux.do)
