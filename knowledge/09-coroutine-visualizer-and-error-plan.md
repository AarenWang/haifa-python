# 方案草案：协程可视化与 Lua 风格错误报告

本方案分为两条主线：
1. 扩展 VM 事件钩子与可视化器，使协程生命周期、堆栈和寄存器流动都可追踪。
2. 规划 Lua 风格错误栈回溯与 CLI 调试开关，形成调试体验的“采集—展示—控制”闭环。

---

## 1. 协程可视化增强

### 1.1 VM 事件钩子设计

- **事件结构定义**
  - 新建 `VmEvent` 数据类型，包含通用字段（`timestamp`、`vm_tick`、`coroutine_id`、`pc`、`payload`）。
  - 针对协程生命周期定义事件子类或 `kind`：
    - `coroutine.create`
    - `coroutine.resume`
    - `coroutine.yield`
    - `coroutine.done`（包含成功或错误结果）
  - 扩展指令执行事件 `instruction.step`，确保在协程上下文切换时携带 `active_coroutine_id`。

- **事件钩子 API**
  - 在 `BytecodeVM` 增加 `subscribe(event_kind, callback)` 与 `emit(event)`，默认可视化器注册为观察者。
  - 以 `contextmanager`/`with` 模式提供 `vm.capture_events()`，便于测试与 CLI 直接读取。
  - `LuaCoroutine` 创建与恢复时调用 `vm.emit(...)`，确保 resumable 协程与主线程统一编号。

- **状态快照**
  - `vm.snapshot_state()` 返回 `{active_coroutine, callstack, registers, event_buffer}`。
  - Resume 时附带调用栈快照（函数标签、PC、upvalues、pending_yield_values），以供 UI/CLI 可选展开。

### 1.2 可视化 UI 更新

- **State Panel**：新增 "Coroutines" 面板，列表显示：
  - `ID / status (running|suspended|dead)`
  - 当前 resume/yield 参数
  - 函数标签与 upvalue 引用
- **Timeline (事件流)**：
  - 复用指令执行时间线，插入协程事件节点并用颜色区分事件类型。
  - `yield` 节点支持 hover 时显示发起协程与 resume 端行号，对应 `instruction.step` 事件。
- **Stack View**：
  - 扩展栈帧展示，对运行中的协程标注来源；
  - 支持在 UI 中切换查看不同协程的寄存器/upvalue。
- **交互**：
  - 允许从协程列表点击切换到对应 VM 状态；
  - 可选自动跟随当前运行协程。

### 1.3 集成与兼容策略

- **Headless 模式**：事件以 NDJSON 输出，便于 CLI 与测试消费。
- **向后兼容**：
  - 未启用协程时 `VmEvent` 退化为 `instruction.step`。
  - `vm_visualizer` 采用特性开关 `showCoroutines`；旧项目可关闭避免 UI 改动。
- **性能考量**：提供 `vm.emit_buffer_size` 配置，防止事件过多导致内存上涨。

### 1.4 实施步骤

1. **事件基础设施**
   - 定义 `VmEvent` 类型与 `emit/subscribe` 机制，编写单元测试验证事件顺序与钩子管理。
2. **协程事件植入**
   - 在 `LuaCoroutine.create/resume/yield`、`BytecodeVM.step` 中发射事件，补充调用栈快照。
3. **可视化器适配**
   - GUI：新增协程面板、时间线事件卡片、栈帧切换。
   - Headless：支持 `--format events` 输出所有事件，含 resume/yield 细节。
4. **文档与示例**
   - 更新可视化器指南，增加示例脚本和截图。
5. **验证**
   - 单元：事件序列（create → resume → yield → resume → done）。
   - 集成：运行示例脚本，通过快照断言 UI 数据模型。

---

## 2. Lua 风格错误报告规划

### 2.1 元信息收集

- **编译期**：
  - 在 `LuaCompiler` 输出 `Instruction` 时附带源位置（行列）。方案：为 `Instruction` 增加可选 `meta` 字段或维护并行 `debug_info` 列表，落地前先选用并行列表以降低入侵性。
  - 函数定义的 `LABEL` 与 `RETURN` 记录所在 Chunk/Function 名称，并记录 upvalue 名称，便于回溯时展示。
- **运行期**：
  - VM 捕获异常时，根据 `pc` 和 call stack 读取对应源位置和函数名，结合协程 ID，生成帧结构 `{func_label, file, line, coroutine_id}`。
  - 协程 resume/yield 栈需合并：
    - 出错协程：从其调用栈 + `LuaCoroutine` 入口函数构造栈层级。
    - Resume 端：`coroutine.resume` 返回 false 和错误消息；在 CLI `--trace` 打开时，还会附带 resume 方调用点。

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
- `--trace`：打印每条指令执行日志，可选 `--trace=coroutine` 仅输出协程事件；依赖 1.x 阶段事件钩子。
- `--stack`：错误时自动输出完整栈，可与 `--trace` 叠加。
- `--break-on-error`：遇到异常时暂停在可视化器/调试器，利用事件系统通知前端进入暂停态。
- `--no-color`：为 CI/快照测试提供稳定输出（可选）。

### 2.4 路线图与阶段划分

1. **Phase A：元信息与帧结构**
   - 扩展 `Instruction` 或维护 `debug_info`，确保代码生成器写入位置信息。
   - 构建 `StackFrame` 数据结构，补充单元测试覆盖函数/协程嵌套场景。
2. **Phase B：运行时错误聚合**
   - 修改 `BytecodeVM.run` 捕获 `RuntimeError`，包装为 `LuaRuntimeError` 并附带帧列表。
   - 更新 `LuaCoroutine.resume` 返回 `(False, error_string, frames)`，旧 API 兼容只取前两个值。
3. **Phase C：格式化与 CLI**
   - 新增 `format_traceback(frames, style="lua")` 生成 Lua 风格文本；在 CLI 和可视化器中共享。
   - 实装 CLI 选项 `--trace/--stack/--break-on-error/--no-color`，并与事件系统打通。
4. **Phase D：集成测试与文档**
   - 为 CLI 增加快照测试，验证错误输出与开关组合。
   - 文档更新：错误格式说明、CLI 参数表、与可视化器联动示例。

---

此方案强调事件采集（VM 钩子）→ 状态展示（可视化器）→ 错误回溯（Lua 栈与 CLI 开关）的流水线式实现路径。完成上述阶段后，可无缝衔接 Milestone 3 其他调试增强任务。
