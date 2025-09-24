# 实施计划：协程可视化与 Lua 风格错误调试

本计划覆盖三个维度：

1. **VM 事件钩子与数据采集** —— 为协程行为建立统一的事件流。
2. **可视化器 UI 升级** —— 利用事件流呈现协程状态、切换视角并改进调试体验。
3. **Lua 风格栈回溯与 CLI 调试开关** —— 提供与 Lua 一致的错误输出，并在命令行暴露调试级别控制。

每个部分均列出目标、关键改动、详细步骤与交付物，以支撑后续迭代落地。

---

## 1. VM 事件钩子与数据采集

### 1.1 目标

- 捕获协程生命周期事件（创建、恢复、挂起、结束）以及它们之间的调用关系。
- 保持事件结构化、可重放，便于 CLI 与 UI 同时消费。
- 在不启用可视化器时对现有执行路径影响最小（零或可忽略的性能开销）。

### 1.2 关键改动

| 模块 | 调整内容 |
| --- | --- |
| `vm/bytecode_vm.py` | 新增 `CoroutineEvent` 数据类、事件缓冲区、`snapshot_state()`/`drain_events()` 观察接口；为协程调度点埋点。 |
| `vm/coroutine.py` | 协程实例持有 `coroutine_id`、入口函数标签及最近一次 resume/yield 的参数与返回值。 |
| `vm/events.py`（新） | 可选：集中声明事件类型与序列化逻辑，便于 CLI/GUI 共享。 |

事件类型初稿：
- `CoroutineCreated(id, func_label, parent_id, upvalues)`
- `CoroutineResumed(id, args, scheduler_pc)`
- `CoroutineYielded(id, values, yield_pc)`
- `CoroutineCompleted(id, results=None, error=None)`

每条事件记录当前 VM `pc`、活动栈摘要（函数名、栈深、寄存器窗口）以及触发时间戳，以便时间轴展示。

### 1.3 实施步骤

1. **事件模型与缓冲区**
   - 定义事件数据结构和 `BytecodeVM.emit_event(event)` 方法，内部将事件附加到 `self._event_buffer`。
   - 复用/扩展现有的 `execution_log` 机制，确保老日志消费者仍工作。

2. **钩子注入**
   - 在 `LuaCoroutine.__init__`、`resume`、`yield_from_vm`、`close` 等节点调用 `emit_event`。
   - 在 `BytecodeVM.run_step`、`call_function`、`return_from_call` 中补充当前协程标识。

3. **状态快照接口**
   - 提供 `snapshot_state()`，返回：当前协程 ID、所有协程的 `status`、活动栈帧概览、寄存器与 upvalue 视图。
   - 支持增量获取：`drain_events()` 清空缓冲并返回最新事件列表。

4. **测试与校验**
   - 单元测试：模拟协程创建→多次 `resume/yield`→完成的序列，断言事件顺序与载荷。
   - 回归测试：执行非协程脚本，确保事件缓冲为空、性能退化可忽略。

交付物：事件模型文档、API 说明、自动化测试。

---

## 2. 可视化器 UI 升级

### 2.1 目标

- 在图形化与 Headless（日志）模式下直观展示协程状态变化。
- 允许调试者快速切换查看不同协程的栈帧、寄存器、upvalue 及事件时间线。
- 将新事件流与现有执行指令时间轴融合，保持 UI 一致性。

### 2.2 工作包

| 组件 | 改动要点 |
| --- | --- |
| 状态面板 (`state_panel.py`) | 新增 "Coroutines" 分区，表格列出 `ID`、`status`、最近的 resume/yield 参数；支持点击选中。 |
| 时间线视图 (`timeline.py`) | 将协程事件插入到指令时间线，`yield`/`resume` 使用不同颜色与图标。 |
| 栈视图 (`stack_view.py`) | 支持根据选中协程渲染其调用栈，并展示寄存器窗口、upvalue 绑定。 |
| 事件日志 (`headless_visualizer.py`) | 在 CLI 输出中添加协程事件段落，可通过过滤器隐藏或显示。 |

### 2.3 实施步骤

1. **数据接入层**
   - 更新可视化器数据源，调用 `vm.drain_events()` 与 `vm.snapshot_state()`。
   - 对旧版数据格式增加兼容转换，确保无协程脚本仍能显示。

2. **UI 组件扩展**
   - State Panel：实现协程列表组件，保持与现有栈帧列表一致的交互（键盘/鼠标导航）。
   - Timeline：为每个事件生成节点，与指令节点共用缩放/滚动逻辑。
   - Stack View：当用户切换协程时刷新寄存器、upvalue；增加顶部提示当前协程标签。

3. **交互改进**
   - 添加“自动跟随当前协程”开关：勾选后 UI 自动跳转到 `CoroutineResumed` 事件对应的协程。
   - 在事件详情面板中显示 resume/yield 参数序列化结果，支持 JSON/表格切换。

4. **测试与文档**
   - 编写端到端示例脚本，验证协程事件在 GUI 与 Headless 模式下呈现一致。
   - 更新用户文档与截图，说明如何解读新的协程面板、时间线和日志输出。

交付物：改造后的 UI、新的交互测试、文档更新。

---

## 3. Lua 风格栈回溯与 CLI 调试开关

### 3.1 目标

- 在编译与运行时收集足够的元信息，将 VM 错误映射回 Lua 源文件与行号。
- 输出与 Lua 5.1+ 兼容的错误消息和 `stack traceback` 文本。
- 在 CLI 提供 `--trace`、`--stack`、`--break-on-error` 等调试开关，与可视化器联动。

### 3.2 元信息与运行时支撑

1. **编译阶段**
   - 扩展 `compiler/instruction.py`（或相关结构）以携带 `source_span`（文件、起始/结束行列）。
   - 构建 `debug_info` 映射：`pc -> (function_label, source_span)`，存储在函数原型/Chunk 中。
   - 生成函数定义时记录显示名称（函数名、匿名函数 fallback，如 `function <anonymous:line>`）。

2. **运行阶段**
   - `BytecodeVM` 捕获运行时异常，将当前 `pc` 与调用栈逐帧转换成 `TracebackFrame`：包含函数名、源文件、行号、协程 ID。
   - 协程错误传播：
     - 出错协程内抛出 `LuaRuntimeError`，序列化为 Lua 风格字符串。
     - `coroutine.resume` 在 Python 层返回 `(False, error_string)`；若宿主 Lua 代码继续抛出，则在主协程栈追加 resume 现场。

3. **格式化工具链**
   - 新增 `debug/traceback.py`：
     - `format_lua_error(message, frame0)` 生成顶层错误信息（`file.lua:line: message`）。
     - `format_traceback(frames)` 输出 `stack traceback:` 块。
   - 提供 API 供 CLI、可视化器及测试共享。

### 3.3 CLI 调试开关路线图

| 开关 | 行为 | 依赖 |
| --- | --- | --- |
| `--trace[=<filter>]` | 打印执行指令与事件（可选仅协程事件）；支持输出到文件。 | 事件钩子与元信息（步骤 1、2 完成）。 |
| `--stack` | 出错时自动打印 Lua 风格 `stack traceback`；可与 `--trace` 叠加。 | Traceback 格式化工具。 |
| `--break-on-error` | 捕获异常后暂停，等待用户在可视化器或 REPL 中检查状态。 | VM 提供错误上下文、可视化器的协程快照。 |

实现顺序建议：
1. 在 CLI 层解析参数并将配置注入 VM/Visualizer 会话对象。
2. `--trace` 先支持基础日志；待协程事件完成后扩展过滤器。
3. `--stack` 在 Lua 风格栈回溯稳定后启用。
4. `--break-on-error` 最后实施，与可视化器交互测试同步进行。

### 3.4 验收标准

- 单元测试：
  - `debug_info` 编解码正确。
  - `format_traceback` 输出符合 Lua 期望（与示例字符串对比）。
- 集成测试：
  - 运行包含协程的脚本触发错误，验证 `coroutine.resume` 返回值与 CLI 输出。
  - CLI 启用各开关组合时行为正确、互不冲突。
- 文档与示例：提供错误输出示例、CLI 使用说明、常见问题排查指南。

---

## 4. 里程碑与依赖关系

1. **Milestone A：VM 事件钩子**（~1 sprint）
   - 完成 §1 的事件模型、缓冲区、基础测试。
   - 暂以简单日志驱动可视化器，验证事件流完整性。

2. **Milestone B：可视化器 UI**（~1 sprint）
   - 在事件流稳定后迭代 UI，交付新的协程面板与时间线。
   - 更新文档与演示脚本。

3. **Milestone C：Lua 栈回溯 + CLI 开关**（~1–1.5 sprint）
   - 编译期元信息 → 运行期错误映射 → CLI 调试开关依次完成。
   - 与可视化器协同测试，确保错误触发后能正确暂停并展示协程状态。

完成以上步骤后，协程调试体验将覆盖事件采集、可视化、错误诊断全链路，可为后续高级调试功能（断点、性能分析）提供坚实基础。
