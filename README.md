# NovelWriter

让创意变得廉价——在持久化的世界模型中自由生成、丢弃、打磨你的小说。

NovelWriter 是一个 AI 辅助小说续写工具。它不只是“续写下一段”，而是维护一个完整的世界模型（人物、关系、体系），让 AI 真正理解你的故事世界，生成风格一致、逻辑自洽的续写内容。

![NovelWriter](docs/screenshot.png)

## 仓库说明

**这个 GitHub 仓库现在作为公开发布仓使用，不再同步私有主仓的每一次开发提交。**

- 私有主仓：日常开发、修 bug、试验功能、整理内部工作流
- 公开发布仓：提供稳定快照、版本标签、安装说明，并接收结构化反馈
- `main`：最新一次公开发布的代码快照，不代表实时开发分支
- `v0.3.2` 这类版本标签：代表一次明确的公开发布

这个公开仓只保留运行、安装、反馈所需的公开信息；内部发布说明、运维文档和设计源文件不再随公开快照同步。

## 核心特性

- **世界模型驱动续写** — 实体、关系、体系构成知识图谱，AI 续写时自动注入相关上下文，而非盲目续写
- **流式生成** — 逐字输出，所见即所得
- **多版本对比** — 一次生成多个续写方案，挑选最满意的
- **Bootstrap 管线** — 导入已有小说文本，自动提取世界模型（人物、关系、势力、体系）
- **Worldpack 导入/导出** — 世界观设定可打包分享，一键导入
- **世界模型编辑器** — 可视化编辑实体、关系图、层级体系，完全掌控世界观
- **叙事约束** — 定义体系级规则（如“禁用现代心理描写”），AI 严格遵守
- **BYOK (Bring Your Own Key)** — 自部署模式下使用你自己的 LLM API，支持任何 OpenAI 兼容接口

## 快速开始

### Docker 部署（推荐）

```bash
git clone https://github.com/Hurricane0698/novelwriter.git
cd novelwriter
cp .env.example .env
# 编辑 .env，填入你的 LLM API 配置
docker compose up -d
```

打开浏览器访问 `http://localhost:8000`。

说明：

- 设置页里的“测试连接”会检测基础连通性、流式输出和 JSON 模式兼容性；如果某项能力缺失，会直接提示可能受影响的功能。

### 本地开发

**后端**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env
uvicorn app.main:app --reload --port 8000
```

**前端**

```bash
cd web
npm install
npm run dev
```

前端开发服务器默认运行在 `http://localhost:5173`。

## 发布节奏

- 日常开发先在私有主仓完成，不保证实时公开同步
- 公开仓在版本标签发布或手动发布时更新
- 每次公开发布都会尽量对应一个明确版本号，便于定位和回报问题
- 紧急修复会以补丁版本（如 `v0.3.3`）形式尽快发布

## 反馈与支持

- **可复现 bug**：请使用 GitHub 的 Bug Report 模板，带上版本号、部署方式、环境信息、复现步骤和日志
- **功能建议**：请使用 Feature Request 模板，说明你的场景、痛点和预期方案
- **Linux.do / 社区讨论**：适合交流体验、讨论方向、催更；需要持续跟踪的问题请回到 GitHub Issue
- **Pull Request**：欢迎小范围修复，但当前不承诺及时 review；较大改动请先开 Issue 对齐方向

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | 是 | LLM API 密钥 |
| `OPENAI_BASE_URL` | 否 | API 地址（默认 OpenAI，可改为任何兼容接口） |
| `OPENAI_MODEL` | 否 | 模型名称 |
| `JWT_SECRET_KEY` | 生产环境必填 | JWT 签名密钥，请使用随机长字符串 |
| `DATABASE_URL` | 否 | 数据库地址（默认 SQLite） |

完整配置见 [`.env.example`](.env.example)。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI · SQLAlchemy · SQLite/PostgreSQL |
| 前端 | React 19 · TypeScript · Tailwind CSS · React Query |
| AI 集成 | OpenAI 兼容 API（支持 OpenAI / Gemini / DeepSeek 等） |
| 部署 | Docker · docker-compose |

## 项目结构

```text
app/              # FastAPI 后端
  api/            # 路由层
  core/           # 业务逻辑（生成、上下文组装、Bootstrap）
  models.py       # SQLAlchemy 数据模型
  config.py       # 配置管理
web/              # React 前端
  src/pages/      # 页面组件
  src/components/ # UI 组件
data/             # 数据文件（Worldpack、演示数据）
tests/            # 后端测试
scripts/          # 工具脚本
```

## 许可证

本项目基于 [AGPLv3](LICENSE) 许可证开源。
