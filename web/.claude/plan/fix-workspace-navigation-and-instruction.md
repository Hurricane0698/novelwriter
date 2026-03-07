# 修复 Workspace 导航和续写指令功能

## 问题描述
1. **导航逻辑问题**：从作品详情页点击「继续续写」进入 Workspace 后显示空白上传界面，而非自动加载小说内容
2. **功能缺失**：缺少用户续写指令输入框，用户无法指定续写方向

## 解决方案
采用 **方案 A：侧边栏集成** - 在 ParamPanel 中添加续写指令输入框

## 修改范围

### 前端修改

#### 1. `src/services/api.ts`
- 扩展 `generateContinuation` 函数签名，添加可选 `prompt` 参数
- 在请求体中传递 prompt 字段

#### 2. `src/components/workspace/ParamPanel.tsx`
- 添加 `instruction` 和 `setInstruction` props
- 添加「续写指令」Textarea 组件
- 使用 Label 组件保持一致性

#### 3. `src/pages/Workspace.tsx`
- 添加 `instruction` 状态
- 添加 `isLoadingContent` 状态
- 添加 `useEffect` 在有 novelId 时自动加载章节内容
- 修改 `handleGenerate` 传递 instruction 参数
- 添加加载状态 UI

### 后端修改

#### 4. `app/schemas.py`
- 在 `ContinueRequest` 中添加可选 `prompt: str | None` 字段

#### 5. `app/api/continuations.py`
- 修改 `create_continuation` 端点，传递 prompt 到 `continue_novel`

#### 6. `app/core/generator.py`
- 修改 `continue_novel` 函数签名，添加 `prompt` 参数
- 在生成 prompt 时注入用户指令

## 状态流转

```
WorkDetail --[novelId]--> Workspace
                              |
                              v
                    useEffect: 加载章节内容
                              |
                              v
                    TextInput: 显示小说内容
                              |
用户输入指令 --> ParamPanel --> instruction 状态
                              |
                              v
                    handleGenerate()
                              |
                              v
                    api.generateContinuation(id, count, prompt)
                              |
                              v
                    后端处理 + 返回结果
```

## 边界情况处理
- 加载中：显示 "正在加载小说内容..." 提示
- 加载失败：console.error 记录，保持空白编辑器可用
- 空章节：inputText 为空字符串
- 后端不支持 prompt：优雅降级，忽略该字段

## 实施顺序
1. 后端：schemas.py → continuations.py → generator.py
2. 前端：api.ts → ParamPanel.tsx → Workspace.tsx
3. 测试验证
