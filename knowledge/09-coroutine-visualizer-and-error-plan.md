# 方案草案：协程可视化与 Lua 风格错误报告

本方案分为两部分：
1. 扩展 VM 可视化器以呈现协程状态与 `resume`/`yield` 事件。
2. 规划 Lua 风格的错误栈回溯，实现字节码 → 源位置映射，为 CLI 调试模式奠定基础。

---

## 1. 协程可视化增强

### 1.1 数据流改造

- **BytecodeVM 扩展**
  - 暴露 `current_coroutine`、`last_event`、`yield_values`、`awaiting_resume` 等状态，通过观察接口（如 `vm.snapshot_state()`）统一输出。
  - 在 `run(step)` 过程中抛出结构化事件：
    - `CoroutineCreated(id, label, upvalues)`
    - `CoroutineResumed(id, args)`
    - `CoroutineYielded(id, values)`
    - `CoroutineCompleted(id, results|error)`
  - 事件对象存入 `vm.emit_stack` 并在视觉层消费，确保现有 jq 功能兼容：若非 Lua 模式，可忽略协程事件。

- **LuaCoroutine 标识**
  - 每一协程分配自增 `coroutine_id`，保存在 `LuaCoroutine` 与 `BytecodeVM` 中，便于可视化器区分。
  - Resume 时附带调用栈快照（labels + PC），为 UI 展示提供数据。

### 1.2 可视化 UI 更新

- **State Panel**：新增 "Coroutines" 面板，列表显示：
  - `ID / status (running|suspended|dead)`
  - 当前 resume/yield 参数
  - 函数标签与 upvalue 引用
- **Timeline (事件流)**：使用现有指令执行时间线，插入协程事件节点；`yield` 节点可高亮指令位置。
- **Stack View**：
  - 扩展栈帧展示，对运行中的协程标注来源；
  - 支持在 UI 中切换查看不同协程的寄存器/upvalue。
- **交互**：
  - 允许从协程列表点击切换到对应 VM 状态；
  - 可选自动跟随当前运行协程。

### 1.3 兼容性与实现步骤

1. 在 `BytecodeVM` 添加事件收集与快照 API，更新 LuaCoroutine 创建/恢复流程以推送事件。
2. 修改 `vm_visualizer`（GUI/Headless）读取新事件。
3. 增加测试：
   - 单元：事件顺序（create → resume → yield → resume → complete）。
   - 集成：Headless 模式输出包含协程状态。
4. 文档：更新可视化器指南，说明协程面板与日志格式。

---

## 2. Lua 风格错误报告规划

### 2.1 元信息收集

- **编译期**：
  - 在 `LuaCompiler` 输出 `Instruction` 时附带源位置（行列）。方案：为 `Instruction` 增加可选 `meta` 字段或维护并行 `debug_info` 列表。
  - 函数定义的 `LABEL` 与 `RETURN` 记录所在 Chunk/Function 名称。
- **运行期**：
  - VM 捕获异常时，根据 `pc` 和 call stack 读取对应源位置和函数名。
  - 协程 resume/yield 栈需合并：
    - 出错协程：从其调用栈 + `LuaCoroutine` 入口函数构造栈层级。
    - Resume 端：`coroutine.resume` 返回 false 和错误消息（Lua 行为：`false, error_string`).

### 2.2 栈回溯格式

目标格式参考 Lua：
```
stack traceback:
	function_name (file.lua:line)
	...
```

- 顶层错误字符串示例：
  - `test.lua:12: attempt to call nil value`
  - `stack traceback:` 后跟帧列表
- 协程错误：
  - `coroutine.resume` 返回 `[False, "test.lua:12: ..."]`
  - 若 resume 调用在 Lua 脚本中继续抛出，VM 将错误向上传递。

### 2.3 CLI 调试模式

待错误映射完成后，CLI 可提供：
- `--trace`：打印每条指令执行日志（可选过滤协程事件）。
- `--stack`：错误时自动输出完整栈。
- `--break-on-error`：遇到异常时暂停在可视化器/调试器。

### 2.4 实现步骤

1. 扩展 `Instruction` 或维护 `debug_info`，确保代码生成器写入位置信息。
2. 修改 VM 调度：
   - `BytecodeVM.run` 捕获 `RuntimeError`，包装为 `LuaRuntimeError`，附带栈帧信息。
   - `LuaCoroutine.resume` 返回 false + 错误字符串。
3. 新增格式化工具：`format_traceback(frames)` 生成 Lua 风格文本。
4. 更新 `run_source`：
   - 在异常情况下抛出 Python `RuntimeError` 前，利用上述格式化生成易读文本。
5. 测试：
   - 编译器：检查 debug 元信息。
   - VM：模拟错误，验证 traceback 内容。
   - 协程：确保错误沿 resume 流程返回。

---

此方案将协程可视化与错误调试串联，完成后即可进入 Milestone 3 余下任务的具体实现阶段。
