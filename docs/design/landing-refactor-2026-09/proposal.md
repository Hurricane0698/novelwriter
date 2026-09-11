# NovWr Landing 前端重构方案：「经纬」

日期：2026-09-09 · 状态：调研 + 提案（未改动任何产品代码）
范围：`/` 落地页及其复用的公共外壳（Navbar / Footer / 主题 token），不涉及 Studio / Atlas / Copilot 工作区。

配套材料（同目录）：

- `concept-brief.md` — 喂给 Codex 图像生成的设计简报
- `concepts/` — Codex 生成的 5 张概念图（方向参考，非像素稿）
- `baseline/` — 当前落地页亮 / 暗 / 移动端截图，以及 openai.com 风格参考截图

---

## 0. 一页结论

1. **现状**：落地页（`web/src/pages/Home.tsx` + `web/src/components/home/*`，共 24 个文件）结构完整、i18n 与埋点齐备，但视觉靠"截图 + 模糊光斑"堆出来，桌面高度 10 166px，5 幕滚动叙事和 3 行功能展示重复展示同一批截图；暗色主题下白色截图卡片与黑底割裂；hero 同时叠了 `AnimatedBackground` 3 个 `blur(100px)` 光斑 + 星空 + `HeroGraphBg` 3 个 framer 驱动的模糊层，无 GPU 的 headless 环境里空闲帧率只有 ~30fps（lite 模式 60fps）。
2. **参考**：从 openai.com 实际 CSS 中抓到的设计 token 说明其方法论是——**画布纯白 / 纯黑，灰阶全部用黑白的透明度阶梯，标题字重 500 + 负字距 + fluid clamp 字号，40px 药丸按钮，颜色只出现在媒体框里，首页没有 WebGL canvas（用 video）**。可借鉴的是"克制的骨架 + 一处放肆的媒体"，而不是照搬星系视频。
3. **概念**：「经纬」。世界模型是长篇的**经线**，正文是**纬线**；shader 画一张由细线织成的"设定织物"：散线在滚动中被拉直、打结成节点（实体），节点间的线是关系。浅色下是纸上的靛青印刷网线，深色下同一张图读成星图（呼应 Atlas 与现有星空主题）。整页只有这一处放肆。
4. **技术路线**：不用 three / R3F（20MB unpacked）也不整包引入 `@paper-design/shaders`（Apache-2.0，可做原型参考），而是写一个 ≤ 6KB 的 WebGL2 全屏三角形运行时 `useShaderSurface`，配 2 个手写 GLSL（`warpLattice`、`inkDither`），接入现有 `PerformanceModeContext` / `prefers-reduced-motion` / 路由表面 `data-route-surface` 做三级降级（WebGL → CSS 渐变 → 静态）。文字与可交互节点一律用 DOM，shader 只负责纹理。
5. **UX**：页面从 6 段压到 5 段、高度目标 ≤ 5 800px；hero 从"截图 + 光斑"改为**可交互的西游记世界模型舞台**（数据来自 `data/worldpacks/journey-to-the-west.json`）；新增"上下文注入"解释段（第二十七回真文本 + 表面/真相卡片）；5 幕叙事保留但缩短、进度条改为可点击；三界面展示改为单框 tab；CTA 去掉泛化统计，改为可验证的事实。
6. **实施**：分 4 个阶段，每阶段可独立合并；必须保留 `data-testid="home-start-writing"`、`#narrative` 锚点、`acquisition_*` 埋点、双语 message key 契约与 `homeScreenshotAssets` 预加载测试。

---

## 1. 现状审计（grounded）

### 1.1 结构与加载

| 层 | 文件 | 事实 |
| --- | --- | --- |
| 路由 | `web/src/App.tsx:83-93` | `/` 在共享 `Layout`（`PageShell` = `AnimatedBackground` + `Navbar`）下渲染 `Home`；三种运行模式（hosted / selfhost / desktop）都会显示落地页。桌面版启动地址固定为 `http://127.0.0.1:8000/`（`desktop/src-tauri/src/runtime.rs:19`），即**桌面用户每次启动先看到营销页**。 |
| 首屏 / 延迟 | `web/src/pages/Home.tsx:47-81` | `HeroSection` 同步渲染；`HomeDeferredSections` 在 `setTimeout(…,1)` 后 lazy 加载；占位 `DeferredSectionsFallback` 用固定高度 720 / 1200 / 640 / 560px。 |
| 主题 | `web/index.html:10-17`，`web/src/hooks/useTheme.ts` | `:root` 是暗色 token，`.light` 类覆盖；首访默认亮色。 |
| 性能模式 | `web/src/lib/performanceMode.ts`，`web/src/contexts/PerformanceModeContext.tsx` | `/`、`/login`、法务页被标记为 `marketing` 表面；`showAmbientBackground = !lite && marketing`；`?perf=lite` 可强制 lite；`html[data-perf-mode='lite']` 会关掉所有 `backdrop-blur`（`index.css:257`）。这套开关是本方案降级链的现成挂点。 |
| i18n | `web/src/lib/uiMessagePacks/home.ts` | zh / en 各 ~117 个 `home.*` key，按路由懒注册（契约见 `web/src/__tests__/uiMessagePacks.test.ts`）。其中 `home.scene.*` 约 30 个 key 已无组件引用（scenes 目录五个组件都只渲染截图），属于死文案。 |
| 资产 | `web/public/screenshots/home/*.png`（10 张，2.3MB） | 通过 `homeScreenshotAssets.ts` 加 `?v=BUILD_ID` 版本号；`preloadHomeProductStageScreenshots` 一次预热全部 10 张（含 hero 已 eager 的两张）。 |
| 构建产物 | `web/dist/assets` | `Home-*.js` 74KB、framer 相关 chunk `use-reduced-motion-*.js` 77KB、全站 CSS 92KB；framer-motion 在营销页外只被 `AtlasAssistWorkbench*` 两个文件使用。 |

### 1.2 视觉与交互问题（对照 `baseline/`）

1. **同一批截图出现三次**：`HeroVisual`（new_studio + new_atlas_overview）、`FeatureShowcase`（同两张 + copilot）、`StickyNarrative/ProductStage`（1–5.png）、`ClosingCTA`（再一次 new_studio）。信息重复，页面被撑到 10 166px。
2. **舞台外壳不随主题**：`StageShell.tsx:35,40,50` 硬编码 `bg-white`、`text-slate-400`、`border-black/8`；五个 `scenes/*.tsx` 也是 `#ffffff / #f8faff / #fcfaff` 硬编码。暗色截图（`baseline/current-hero-dark.png`）里白卡片像贴上去的贴纸。
3. **三个强调色稀释身份**：`homeContent.ts` / `screenshotManifest.ts` 里 `#5b6bf0`、`#4a7de8`、`#7a5cf0` 三个硬编码 hex，与 token `--accent: 235 74% 62%` 平行存在，且 `${accentHex}33` 这类字符串拼 alpha 无法随主题变化。
4. **氛围层叠加**：hero 下面同时有 `AnimatedBackground`（`fixed`，3 个 700px 级 `blur(100px)` 光斑 + 星空两层伪元素）和 `HeroGraphBg`（3 个 `blur-2xl/3xl` 光斑由 framer 无限 x/y 动画驱动）。实测（headless Chromium，1440×900，hero 静止 3s）：

   | 场景 | 平均帧间隔 | p95 | 每帧样式重算 |
   | --- | --- | --- | --- |
   | light default | 29.6ms（~34fps） | 50.1ms | ~1 次 / 帧 |
   | dark default | 32.1ms（~31fps） | 50.1ms | ~1 次 / 帧 |
   | light `?perf=lite` | 16.6ms（60fps） | 18.6ms | ~1 次 / 帧 |

   headless 没有 GPU 合成，数字偏悲观，但方向明确：**模糊层是主要成本**，framer 每帧写 inline transform 触发样式重算。一个 shader canvas 替换全部光斑后，主线程每帧只剩一次 uniform 上传。
5. **移动端 hero**：`HeroVisual` 固定 `h-[340px]` + `object-contain` 导致截图上下大面积留白（`baseline/current-hero-mobile.png`）。
6. **模板化痕迹**：每段一个全大写等宽眉标（`tracking-[0.22em] uppercase`）、`01/02/03` 水印数字、每张卡 `useInView` 淡入上移、hover 光晕、CTA 处三个泛化统计（"100万+字 / 结构化 / 全书"）。这些在 `frontend-design` 技能里被列为生成式页面的典型信号。
7. **可交互性为零**：整页除 CTA 与 `#narrative` 锚点外没有任何可操作元素；进度条（`StickyNarrative.tsx:121-139`）是纯展示。
8. **桌面版每次启动进入营销页**（见 1.1），对已安装用户是多余一跳。

### 1.3 必须保留的契约

- `data-testid="home-start-writing"`（`e2e/mock/app.spec.ts:13-16`、`e2e/production/startup.spec.ts:22`、`src/__tests__/PublicLocaleSurfaces.test.tsx:96`）；hosted 未登录 → `/login`，否则 `/library`。
- `Navbar` 在 `/` 上渲染 `<a href="#narrative">`（`Navbar.tsx:55`）。
- 埋点：`acquisition_landing_view`、`acquisition_cta_click`（meta.cta = `hero_start` / `footer`）。
- `PublicLocaleSurfaces.test.tsx:65-82` 断言英文标题文案（THREE SURFACES、Five steps…、Writers of long-form fiction…）——重构段落时需同步更新该测试，而不是保留死段落。
- `homeScreenshotAssets.test.ts`：预加载列表与 `homeProductStageScreenshotPublicPaths` 一致。
- 双语 key 契约：`home.*` 必须 zh / en 同时存在，且只能通过 `import '@/lib/uiMessagePacks/home'` 懒注册。

---

## 2. 外部调研

### 2.1 openai.com 设计语言（2026-09-09 用 Playwright 抓取实时 CSS）

来源：`/tmp/novwr-ref/openai-styles.json`（669 个语义变量 + 完整 primitive 色阶）。与本方案相关的结论：

| 维度 | openai.com 实际值 | 对 NovWr 的启发 |
| --- | --- | --- |
| 画布 | light `--color-background:#fff`；dark `#000` | 放弃当前 `235 60% 99%` 的淡靛白与 `233 34% 6%` 的靛黑，营销页改用纯白 / 纯黑，让色彩只留在媒体框内 |
| 灰阶 | `--color-primary-{2,4,12,44,60,80,100}` = 黑（暗色为白）的 2/4/12/44/60/80/100% alpha；实体灰 `#f1f1f1 / #1f1f1f` 作三级表面 | 用一个 `--lp-ink` + alpha 阶梯替代现在散落的 `foreground/6`、`slate-300`、`black/8` |
| 字体 | OpenAI Sans；**所有标题字重 500**；`h1` `clamp(2rem→4rem)`、字距 `-0.03em`；`xl` `clamp(4rem→7rem)`；正文 17px/28px；CTA 14px/500 | 标题从 600/700 降到 500，字号改 fluid；中文不加负字距 |
| 按钮 | 圆角 40px；主按钮 `#000` 填充白字；次按钮 `rgba(0,0,0,.04)` 填充；无阴影 | 去掉 `shadow-[0_12px_32px_hsl(var(--accent)/0.35)]` 光晕，主 CTA 用墨色而非强调色 |
| 强调色 | `--color-hue-{red,lime,magenta,blue,yellow}`（light `#f53255/#9dca1c/#eb56c5/#29bdfd/#ffaf00`，dark 版降饱和）；文字渐变 pale 组 `#ffe0cf/#8fdfff/#b3feef/#ffd9c6/#b9d7ff/#a9fff5/#fff7a8` | 强调色**成对定义**（亮 / 暗两版）而非一个 hex；pale 组的思路可用于 shader 线色 |
| 媒体 | 首页 0 个 `<canvas>`、3 个 `<video>`；主题色靠媒体卡片内的生成式视觉；`SolAsciiHeroBackdrop` 模块表明他们做过 ASCII 风格程序化背景 | 颜色 / 光效限制在圆角媒体框里；我们用实时 shader 取代 video，但同样"框内放肆、框外安静" |
| 排版节奏 | 大量留白、左对齐、卡片无边框、卡片与标题之间 24–32px | 去掉现在的分节渐变分割线与交替底色带 |

注意：仅参考方法与色阶结构，不复制其字体（OpenAI Sans 非开源）与星系素材。

### 2.2 Shader 技术路线

| 方案 | 体积（npm unpacked） | 评价 |
| --- | --- | --- |
| `three` + `@react-three/fiber` | 20.4MB + 2.2MB | 为 2D 背景纹理引入 3D 场景图，杀鸡用牛刀；与 `Home` 74KB 的 chunk 不成比例 |
| `ogl` 1.0.11 | 423KB | 精简 WebGL 库，但我们只需要一个全屏三角形 + uniform |
| `@paper-design/shaders` 0.0.80 / `-react` | 854KB / 427KB，零依赖，Apache-2.0，30 个现成 shader（mesh-gradient、grain-gradient、dithering、dot-grid、warp、waves…） | 快速原型的好参照；但 0.0.x 版本承诺会 break，且现成效果难以"与项目概念一致"。可在原型阶段用它比对手感，正式实现不依赖 |
| **自写 WebGL2 运行时 + GLSL** | ≤ 6KB（含两个 shader 字符串） | 完全可控：DPR 上限、可见性暂停、reduced-motion 单帧、context lost 降级、与 `PerformanceModeContext` 直接对接；概念与产品绑定 |

选择最后一项。理由除了体积，还有"精细化设计"的要求：线密度、节点位置、滚动驱动的 `uOrder` 都要和 DOM 层的实体标签精确对齐，第三方组件做不到。

---

## 3. 设计概念：「经纬」

### 3.1 一句话

> 长篇写到几十万字之后，设定还立得住——因为世界模型是这部小说的经线。

hero 舞台里的织物就是这句话的可视化：初始状态线是松散、微微弯曲的（散落在几百章里的设定）；随着页面加载 / 滚动，线被拉直，交点亮起成为实体节点（唐僧、孙悟空、花果山、紧箍咒…），节点间的线标出关系（师徒、约束、敌对）。深色主题下同一张图变成星图，对应产品里的 Atlas 和 `StarGraph` 关系视图（`web/src/components/world-model/relationships/StarGraph.tsx`）。

### 3.2 设计原则

1. **框内放肆，框外安静**。所有颜色、光、shader 只出现在 20px 圆角的媒体框内；框外只有纸、墨、排版。
2. **结构即信息**。编号只用于真正的顺序（五步工作流），眉标 / 分割线 / 卡片阴影一律去掉；灰阶用 alpha 阶梯表达层级。
3. **一次动效**。hero 的"织线成图"是唯一的非用户触发动效；其余动效只回应用户的滚动、悬停、点击。
4. **文字属于 DOM**。shader 永不承载文字或可点击对象；实体标签、关系标签是带 `button` 语义的 DOM 覆盖层，键盘可达。
5. **真实数据**。demo 内容来自内置示例《西游记》worldpack 和 `data/demo/西游记_前27回.txt` 第二十七回（公有领域）；不用编造的数字。
6. **三级降级**。WebGL2 → CSS 渐变 + SVG 线框 → 静态；`prefers-reduced-motion` 与 `perf=lite` 分别控制"动不动"和"画不画"。

### 3.3 色板（营销表面专用 token）

利用现有的 `html[data-route-surface='marketing']` 挂点（`performanceMode.ts:67-70`），在 `index.css` 中新增一组 `--lp-*` 覆盖，**不动工作区 token**：

```css
/* 浅色营销表面：纸与墨 */
html[data-route-surface='marketing'].light {
  --lp-paper: 0 0% 100%;            /* #FFFFFF 画布 */
  --lp-ink: 0 0% 0%;                /* 墨，正文用 /0.8，元信息 /0.6，禁用 /0.44，边框 /0.12，填充 /0.04 */
  --lp-frame: 0 0% 97%;             /* #F7F7F7 媒体框底（截图框） */
  --lp-thread: 235 74% 62%;         /* #5B6BF0 经线，沿用 --accent，保证与产品一致 */
  --lp-thread-soft: 228 100% 88%;   /* #C2D3FF 纬线 / 远景线 */
  --lp-knot: 236 62% 32%;           /* #1F2B85 节点 */
  --lp-truth: 38 92% 50%;           /* 沿用 --color-status-draft，"真相"层与草稿态同色系 */
}
/* 深色营销表面：黑纸与星图 */
html[data-route-surface='marketing']:not(.light) {
  --lp-paper: 0 0% 0%;
  --lp-ink: 0 0% 100%;
  --lp-frame: 233 30% 6%;           /* 框内保留一点靛黑，框外纯黑 */
  --lp-thread: 235 78% 74%;         /* #8B93F8，已在 --nw-copilot-glow-1 出现过 */
  --lp-thread-soft: 233 40% 30%;
  --lp-knot: 0 0% 100%;
  --lp-truth: 38 92% 60%;
}
```

主 CTA 用 `hsl(var(--lp-ink))` 填充 + 反色文字（对应 openai 的黑按钮），强调色只在焦点环、链接 hover 和媒体框内出现。工作区（Studio / Atlas）继续使用现有 periwinkle 玻璃体系，两者通过 `--accent` 同源保持一致。

### 3.4 字体

- **中文大标题**：宋体类衬线，字重 500，行高 1.08，字距 0。首选方案是把标题所用的几十个字从 Noto Serif SC 子集化（`pyftsubset`，仅 `home.hero.title` / 各段 h2 用字，估算 ≤ 30KB woff2，构建脚本放 `web/scripts/`），回退 `"Songti SC", "STSong", "Noto Serif CJK SC", "SimSun", serif`。原因：产品是小说工具，宋体标题比几何无衬线更能承载文学感，也是与 openai 式无衬线拉开距离的最便宜的一步。
- **英文大标题 / 正文**：继续 Outfit Variable（已在 `main.tsx` 引入），标题字重 500、字距 `-0.03em`；正文 17px / 1.65。
- **数据与代码**：JetBrains Mono，只用于章节号、实体计数等真正的"数据"，不再用于眉标。
- 通过 `html[data-ui-locale='zh']` / `'en'`（`index.html:24` 已写入）切换字族与字距。

Fluid 字号（参照 openai 的 clamp 结构）：

| 角色 | 尺寸 | 字重 |
| --- | --- | --- |
| display（hero h1） | `clamp(2.25rem, 1.4rem + 3.4vw, 4.25rem)` | 500 |
| h2 | `clamp(1.75rem, 1.2rem + 1.6vw, 2.5rem)` | 500 |
| h3 | `clamp(1.25rem, 1.05rem + 0.6vw, 1.5rem)` | 500 |
| body | `1.0625rem / 1.65` | 400 |
| meta | `0.875rem / 1.4` | 500 |

### 3.5 布局

保留 `max-w-7xl`（1280px）容器，左对齐；栅格 12 列，间距 24 / 32 / 48；媒体框圆角 20px、1px `--lp-ink/0.08` 描边、无阴影；段间距 128px（桌面）/ 80px（移动），不再用底色带和渐变分割线。

```
┌──────────────────────────────────────────────────────────────┐
│ NovWr                      功能 · 文档            [开始写作]  │  64px，纸底，无模糊
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  先理解世界，                                                 │  display，左对齐，宋体
│  再写出好故事                                                 │
│  连载写到几百万字，设定还能不打架？…（≤ 40 字）                │  body /0.6
│  [开始写作]  [下载桌面版 ↗]                                   │  墨色药丸 + 4% 填充药丸
│                                                              │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │  经纬舞台（16:9 → 移动 4:5）                               │ │  唯一的媒体框
│ │  · 背景：warpLattice shader                               │ │
│ │  · 覆盖：DOM 节点标签（唐僧 / 孙悟空 / 花果山 / 紧箍咒…）   │ │
│ │  · 悬停 / 聚焦节点 → 右侧小卡（类型 · 表面 · 真相）         │ │
│ │  · 底部一行：「23 个实体 · 20 条关系 · 5 个体系」来自示例   │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. UX 交互逻辑（分段）

目标：桌面总高度 ≤ 5 800px（现 10 166px）；每段一个明确的"证明"，不重复截图。

| # | 段落 | 现状 | 方案 | 交互 |
| --- | --- | --- | --- | --- |
| 1 | Hero「经纬舞台」 | 文案 + 两张截图 + 光斑 | 文案 + 可交互世界模型舞台 | 入场：线由乱到直 1.2s；hover / focus 节点显示表面 / 真相卡；点击关系线高亮两端；`uOrder` 与滚动绑定，离开首屏时织物"完成" |
| 2 | 「只注入这一章需要的设定」 | 无（`DetailsMatter` 里只有一句话） | 左：第二十七回一段真文本，实体名下划高亮（复用 `nw-drift-highlight` 的语义，颜色换 `--lp-thread`）；右：注入清单（3 个实体、2 条关系、1 条体系）与「表面 / 真相」切换 | hover 正文中的实体 → 右侧清单对应项亮起；切到「真相」→ 卡片显示作者私有信息并说明"AI 续写只看表面" |
| 3 | 五步工作流 | 5 幕 × 94vh，进度条不可点 | 保留 5 幕（文案不变），每幕 `min-h` 降到 70vh；右侧 sticky 舞台 = `inkDither` 底纹 + 一张截图 + 一条 DOM 标注；进度条改为 5 个 `button`，点击 `scrollIntoView` | 滚动驱动不变（`useNarrativeScroll` 保留）；键盘 ←/→ 切幕；`#narrative` 锚点保留 |
| 4 | 三个界面 | 3 行大截图 | 单个媒体框 + 三个 tab（写作台 / 世界地图 / AI 助手），tab 文案复用 `home.feature.*.eyebrow/title/description` | tab 切换用 `AnimatePresence`（已有依赖）或 CSS crossfade；移动端 tab 变横向可滚 |
| 5 | 收尾 CTA + 下载 | 截图 + 三个泛化统计 + 按钮 | 一句标题、一行说明、`[开始写作]` + 平台下载（Windows x64 / macOS Apple Silicon，链接取自 README 的 releases 地址，仅 hosted 显示）+ 一行事实：「BYOK：任何 OpenAI 兼容接口 · 数据在本机 SQLite · AGPLv3 开源」 | 埋点 `cta: 'footer'` 不变；新增 `cta: 'download_windows' / 'download_macos'` |
| — | Footer | `mt-20` 玻璃底 | 去玻璃，纯纸底 1px 顶线 | — |

删除：`FeatureShowcase.tsx`（并入 4）、`DetailsMatter.tsx`（并入 2）、`HeroVisual.tsx`、`HeroGraphBg.tsx`、`scenes/*.tsx`（舞台改为数据驱动的单组件）、`home.scene.*` 死文案。

### 4.1 Hero 舞台数据

新建 `web/src/components/home/demo/journeyWorldDemo.ts`，从 `data/worldpacks/journey-to-the-west.json` 抄一份**静态子集**（前端无法在运行时读 `data/`），并注明来源与公有领域许可：

- 实体 8 个：唐僧、孙悟空、猪八戒、观世音菩萨、白骨夫人（人物）、花果山（地点）、紧箍咒（物品）、天庭（势力）。每个带 `entity_type`、1 条 `surface`、1 条 `truth`（如紧箍咒「作用」：表面"唐僧控制悟空的手段" / 真相"不对等的权力工具"）。
- 关系 7 条：唐僧→孙悟空 师徒、观音→孙悟空 约束、如来→孙悟空 镇压（可选）、孙悟空→白骨夫人 敌对、白骨夫人→唐僧 觊觎、猪八戒→孙悟空 挑拨、天庭→孙悟空 招安-叛逆。
- 体系 1 个：取经团队层级（hierarchy）— 只在卡片里以一行文字提示，不画树。

节点布局：JS 侧用固定种子的简单力导向预计算（或直接手排 8 个归一化坐标），shader 通过 `uKnots[8]` uniform 接收同一组坐标，保证 DOM 标签与 shader 亮点严格重合。

### 4.2 「注入」段数据

`web/src/components/home/demo/chapter27Excerpt.ts`：取 `data/demo/西游记_前27回.txt:2957` 一段约 120 字（"那唐僧在马上，又唬得战战兢兢……他那脊梁上有一行字，叫做'白骨夫人'"），标注 4 处实体 span（唐僧、八戒、行者→孙悟空、白骨夫人）与 1 处体系触发（"念咒"→ 紧箍咒 / 取经戒律）。右侧清单展示"本章注入：3 个实体 · 2 条关系 · 1 条约束"，数字由数据长度算出而非硬编码。

### 4.3 桌面运行模式（待决策）

`getRuntimeMode() === 'desktop'` 时建议 `/` 直接 `Navigate` 到 `/library`（或仅在首次安装显示一次欢迎页）。这是产品决策，方案里只列出实现点：`App.tsx` 的 `/` 路由加一个 `RequireMarketing` 守卫，`PublicLocaleSurfaces.test.tsx` 中 `desktop` 用例需相应调整。

---

## 5. Shader 系统

### 5.1 运行时 `useShaderSurface`

文件：`web/src/components/home/shader/useShaderSurface.ts`（≈ 150 行）。

```ts
type ShaderUniforms = Record<string, number | readonly number[]>

type ShaderSurfaceOptions = {
  fragment: string                         // GLSL ES 3.00 片元着色器
  uniforms: () => ShaderUniforms           // 每帧读取（uTime/uOrder/uPointer/uKnots…）
  animate: boolean                         // false → 只渲染一帧（reduced-motion / 舞台完成后）
  maxDpr?: number                          // 默认 1.5
  fps?: 30 | 60                            // 默认 60；舞台离开首屏后可降 30
}

export type ShaderSurfaceState = 'webgl' | 'fallback' | 'idle'

export function useShaderSurface(
  canvasRef: RefObject<HTMLCanvasElement>,
  options: ShaderSurfaceOptions,
): ShaderSurfaceState
```

行为约定：

1. `usePerformanceMode().isLite` 为真、或 `getContext('webgl2')` 返回 null、或收到 `webglcontextlost` → 返回 `'fallback'`，组件渲染 CSS / SVG 兜底（第 5.4 节）。
2. `matchMedia('(prefers-reduced-motion: reduce)')` → `animate=false`：编译、渲染一帧 `uTime=8.0, uOrder=1.0` 的"完成态"，然后不再申请 rAF。
3. `IntersectionObserver`（threshold 0.05）不可见时停帧；`document.visibilityState !== 'visible'` 时停帧。
4. `ResizeObserver` 驱动 `canvas.width/height = size * min(devicePixelRatio, maxDpr)`，并设置 `uResolution`。
5. 单个 `WebGLProgram`，顶点用 3 顶点全屏三角形，无 VAO 以外的资源；卸载时 `loseContext()` 释放。
6. 渲染前置检查 `gl.getShaderParameter(COMPILE_STATUS)`，失败 → `'fallback'` 并 `console.warn` 一次（dev only）。

### 5.2 `warpLattice.frag`（hero 舞台）

uniforms：`uResolution`、`uTime`、`uOrder`（0 松散 → 1 成形）、`uPointer`（归一化）、`uKnots[8]`（节点坐标）、`uPaper / uThread / uThreadSoft / uKnot`（由 `--lp-*` 解析成 vec3 传入，主题切换时重新读取）。

核心结构（伪 GLSL，说明算法而非最终代码）：

```glsl
float noise(vec2 p);                       // 2D value noise + 2 层 fbm
vec2 uv = gl_FragCoord.xy / uResolution;   // 保持宽高比

// 经线：竖向细线，位移随 (1-uOrder) 衰减
float chaos = (1.0 - uOrder) * 0.35;
float wx = uv.x + chaos * (noise(uv * 3.0 + uTime * 0.05) - 0.5);
float warp = 1.0 - smoothstep(0.0, 1.6 / uResolution.x * 40.0, abs(fract(wx * 40.0) - 0.5));
// 纬线：横向更稀疏、更淡
float wy = uv.y + chaos * 0.6 * (noise(uv * 2.0 - uTime * 0.04) - 0.5);
float weft = 1.0 - smoothstep(0.0, 1.6 / uResolution.y * 14.0, abs(fract(wy * 14.0) - 0.5));

// 节点：到最近 knot 的距离场，亮度由 uOrder 门控
float knot = 0.0;
for (int i = 0; i < 8; i++) {
  float d = length((uv - uKnots[i]) * vec2(uResolution.x / uResolution.y, 1.0));
  knot += smoothstep(0.035, 0.0, d) * uOrder;
}

vec3 col = uPaper;
col = mix(col, uThreadSoft, weft * 0.35);
col = mix(col, uThread, warp * mix(0.10, 0.28, uOrder));
col = mix(col, uKnot, knot);
// 指针附近 6% 的提亮，作为"读者的目光"
col += uThread * 0.06 * smoothstep(0.25, 0.0, length(uv - uPointer));
```

关系线不在 shader 里画：DOM 覆盖层用一个 `<svg>` 画 7 条 `<line>`，颜色 `--lp-thread`，与标签共享坐标；这样 hover 高亮、`aria-label`（"唐僧 与 孙悟空：师徒"）都在 DOM 层解决。

### 5.3 `inkDither.frag`（工作流舞台 / 三界面框底纹）

4×4 Bayer 有序抖动作用于一条从 `--lp-frame` 到 `--lp-thread-soft/0.2` 的对角渐变，产出"印刷网点"质感——呼应"稿子 / 印刷"，成本极低，**默认静态**（`animate=false`），只在 `uOrder` 切幕时重绘一帧。这条 shader 也可以完全用 CSS `mask-image` + `repeating-conic-gradient` 近似，作为 fallback。

### 5.4 降级链

| 条件 | 舞台表现 |
| --- | --- |
| WebGL2 可用、无 reduced-motion、非 lite | 完整动画 |
| reduced-motion | 单帧完成态 + DOM 标签直接就位（无入场动画） |
| `perf=lite` 或无 WebGL2 或 context lost | `fallback`：`<div>` 上 `repeating-linear-gradient` 画经纬线（CSS），节点用 SVG 圆；无动画 |
| 移动端（`pointer: coarse`） | `maxDpr=1`，`fps=30`，`uPointer` 固定在中心 |

### 5.5 性能与可访问性门禁

- `Home` chunk 增量 ≤ 12KB gzip（运行时 + 两段 GLSL + demo 数据），framer 从 hero 移除后应为净减少。
- 首屏 LCP 元素改为 h1 文本（不再是 `new_studio.png`）；hero 不再 eager 加载任何截图。
- hero 静止 3s 的 rAF 帧间隔 p95 ≤ 20ms（复用本次测量脚本，见附录 A），lite 模式与 default 差距 ≤ 2ms。
- 所有节点标签 `button` 化，`:focus-visible` 环用 `--lp-thread`；shader canvas `aria-hidden`。
- 对比度：正文 `--lp-ink/0.8` 在纯白上 ≈ 12:1；元信息 `/0.6` ≈ 7:1；`/0.44` 只用于禁用态。
- `prefers-reduced-motion` 与 `?perf=lite` 都要在 `performanceMode.test.tsx` 增加一条断言：`useShaderSurface` 返回 `'fallback'`。

---

## 6. 文件级实施方案

### 6.1 新增

```
web/src/components/home/
  shader/useShaderSurface.ts        WebGL2 运行时
  shader/warpLattice.frag.ts        GLSL 字符串（导出 const）
  shader/inkDither.frag.ts
  shader/readLandingPalette.ts      读取 --lp-* → vec3；监听 .light 切换
  stage/WorldLatticeStage.tsx       hero 舞台：canvas + SVG 关系线 + 节点按钮 + 详情卡
  stage/LatticeFallback.tsx         CSS/SVG 兜底
  demo/journeyWorldDemo.ts          西游记子集（实体 / 关系 / 坐标）
  demo/chapter27Excerpt.ts          第二十七回节选 + 实体 span 标注
  InjectionSection.tsx              第 2 段
  SurfaceTabs.tsx                   第 4 段（替代 FeatureShowcase）
  DownloadRow.tsx                   第 5 段平台下载
web/scripts/subset-display-font.mjs 从 home 文案生成宋体子集（可选，阶段 C）
```

### 6.2 修改

- `web/src/index.css`：新增 `--lp-*` 两组覆盖；删除 `--lp-surface / --lp-cta-*`（4 个）；`.animated-blob` 系列保留给 `/login`（`Login.tsx` 直接渲染 `AnimatedBackground`），但 `/` 不再显示——在 `PageShell` 之外，`Home` 通过 `data-route-surface` + 新增 `showAmbientBackground` 判定跳过（`PerformanceModeContext.tsx:50` 增加 `pathname !== '/'` 或新增 `ambientSurface` 字段）。
- `web/src/components/home/HeroSection.tsx`：去 framer，入场用 CSS `@keyframes`（一次）；`HeroVisual` → `WorldLatticeStage`；第二个按钮"下载桌面版"仅 hosted。
- `web/src/components/home/StickyNarrative.tsx`：进度条 `button` 化 + 键盘；`NarrativeAct` 去水印数字与全大写眉标；`ProductStage` 改为读 `sceneManifest` 的单组件，底纹用 `inkDither`。
- `web/src/components/home/StageShell.tsx`：颜色全部 token 化（`--lp-frame`、`--lp-ink/0.08`）。
- `web/src/components/home/homeContent.ts`、`screenshotManifest.ts`：删除 `accentHex`，改为语义 `tone: 'studio' | 'atlas' | 'copilot'` 映射到 token。
- `web/src/components/home/HomeDeferredSections.tsx`、`Home.tsx`：段落顺序 Hero → Injection → Narrative → SurfaceTabs → ClosingCTA → Footer；`DeferredSectionsFallback` 高度改为 `min-h-[60vh]` × 段数，避免固定像素 CLS。
- `web/src/components/layout/Navbar.tsx`：营销页去 `backdrop-blur-xl`（纸底 + 1px 线），新增「文档」链接到 README / docs（hosted）；`SiteFooter.tsx` 去玻璃。
- `web/src/lib/uiMessagePacks/home.ts`：删除 `home.scene.*`、`home.cta.stat.*`、`home.details.*`（并入新 key）；新增 `home.lattice.*`（节点卡片文案：类型、表面、真相、关系动词）、`home.injection.*`、`home.download.*`；zh / en 同步。
- `web/src/__tests__/PublicLocaleSurfaces.test.tsx`：更新英文标题断言为新段落；新增"节点按钮可聚焦并展示表面 / 真相"用例。
- `web/src/__tests__/homeScreenshotAssets.test.ts`：预加载列表随 `screenshotManifest` 缩减（hero 不再预热 `new_studio/new_atlas_overview`）。
- `web/e2e/mock/app.spec.ts`、`e2e/production/startup.spec.ts`：不变（testid 保留）。

### 6.3 删除

`HeroVisual.tsx`、`HeroGraphBg.tsx`、`FeatureShowcase.tsx`、`DetailsMatter.tsx`、`scenes/*.tsx`（5 个）、`ScreenshotStageAsset.tsx` 中的白色渐变遮罩（改 token）；`public/screenshots/home/detail.png`、`detail2.png`、`atlas_entity_edit.png` 若第 2 段不再使用则一并移除。

---

## 7. 分阶段路线图

| 阶段 | 内容 | 验证 | 可独立合并 |
| --- | --- | --- | --- |
| A 骨架（1–2 天） | `--lp-*` token、Navbar / Footer 去玻璃、字号 fluid 化、去除眉标 / 水印 / 淡入、StageShell token 化、hero 去 framer、关闭 `/` 的 `AnimatedBackground`；段落顺序与 `DeferredSectionsFallback` 调整 | `npm run test:run`、`test:e2e:mock`、`test:e2e:production`；帧间隔脚本 p95 ≤ 20ms；亮 / 暗截图对比 | 是 |
| B 经纬舞台（3–4 天） | `useShaderSurface` + `warpLattice` + `WorldLatticeStage` + demo 数据 + fallback；`performanceMode.test.tsx` 增加降级断言 | 手测 WebGL 关闭（`--disable-webgl`）、`perf=lite`、reduced-motion 三条路径截图；chunk 增量 ≤ 12KB gzip | 是 |
| C 内容段（2–3 天） | `InjectionSection`、`SurfaceTabs`、CTA / 下载行、i18n 清理、`PublicLocaleSurfaces` 更新、宋体子集脚本（可选） | 双语渲染测试；键盘遍历；移动端 390px 截图 | 是 |
| D 收口（1 天） | 工作流舞台 `inkDither`、进度条按钮化、桌面模式 `/` 跳转决策落地、README 截图更新 | 全量测试 + `docs/` 截图刷新 | 是 |

每阶段结束用附录 A 的脚本重新截图到 `docs/design/landing-refactor-2026-09/after-<phase>/`，与 `baseline/` 对照。

---

## 8. 风险与待决策

1. **桌面版是否跳过营销页**（4.3）——影响首次启动体验与 `PublicLocaleSurfaces` 的 desktop 用例。建议：跳过，并在 Library 空态里保留一条"了解 NovWr 如何工作"的链接回 `/`。  可以
2. **中文宋体标题的字体来源**：子集化 Noto Serif SC（SIL OFL，可再分发）需要新增一个构建脚本与 ≤ 30KB 静态资产；若不接受，回退到系统宋体栈，Windows 上 SimSun 大字号偏细，需要把字重换成 600 补偿。接受
3. **Hosted 下载按钮指向 GitHub Releases**（README 中的固定版本 URL 会过期）：建议链接 `releases/latest` 并在 hosted 配置里暴露版本号，而不是硬编码 `v0.5.2`。同意
4. **WebGL 在 Windows WebView2 / 低端 GPU 的表现**：`e2e/desktop-installed` 通过 CDP 附着真实 WebView2，可在阶段 B 增加一条"舞台状态为 webgl 或 fallback 之一，且无 console error"的探针。
5. **`@paper-design/shaders` 只作原型对照**：如需快速看手感，可在本地分支临时 `npm i @paper-design/shaders-react` 比对 `warp` / `dot-grid` 的参数感觉，但不进入依赖。
6. **英文文案**：新段落需要新的 en 文案（`home.injection.*` 等），双语契约测试会强制补齐。

---

## 附录 A：本次使用的测量与抓取脚本

- 基线截图（亮 / 暗 / 移动 / 叙事中段）：`/tmp/novwr-landing-baseline/shoot.mjs`，在 `web/` 目录用 `node` 运行，需先 `npm run dev -- --port 5199`。
- 帧间隔与 CDP Performance 指标：见第 1.2 节表格，脚本逻辑为 `Performance.enable` → 静止 3s 采样 rAF 间隔 → 读取 `TaskDuration / RecalcStyleCount`。
- openai.com 样式抓取：Playwright 打开首页后遍历 `document.styleSheets` 收集 `--*` 变量、`h1/h2/p/button` 的 `getComputedStyle`，结果存 `/tmp/novwr-ref/openai-styles.json`。

## 附录 B：概念图索引

见 `concepts/README.md`（由 Codex `image_generation` 生成，附每张图与简报的偏差说明）。
