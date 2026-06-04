# Scheme Bytecode Compiler 与 VM 调试集成方案

本文档描述 `haifa_scheme` 从当前 tree-walking interpreter 扩展为“解释器后端 + BytecodeVM 编译后端”的整体技术方案。目标不是替换现有解释器，而是在保留当前稳定语义的基础上，为 Scheme 增加可编译、可运行、可视化、可调试的 VM 后端，使 Scheme 代码最终可以像 Lua 代码一样进入当前 VM debugger 工具链。

---

## 1. 现状

### 1.1 Scheme 当前执行模型

当前 `haifa_scheme` 是一个独立的 tree-walking interpreter：

```text
Scheme source
  -> reader.parse_source(...)
  -> Python datum: Symbol / list / DottedList / Vector / literal
  -> haifa_scheme.runtime._eval(...)
  -> Environment chain + Procedure + BuiltinFunction
  -> Python value
```

核心实现分布在：

- `haifa_scheme/reader.py`：读取 Scheme 源码，产出 Python datum。
- `haifa_scheme/runtime.py`：解释执行特殊形式、函数调用、尾调用 trampoline、continuation。
- `haifa_scheme/environment.py`：词法环境链。
- `haifa_scheme/stdlib.py`：内置函数。
- `haifa_scheme/values.py`：Scheme pair、empty list、char、vector、port、formatter。
- `haifa_scheme/macros.py`：`define-syntax` / `syntax-rules` 的实用子集。
- `haifa_scheme/cli.py`：`pyscheme` 命令行和 REPL。

当前 runtime 已经支持较完整的教学型 Scheme Core+：

- 词法作用域、闭包、递归。
- `quote`、`if`、`define`、`lambda`、`begin`、`set!`。
- `let`、named `let`、`let*`、`letrec`。
- `and`、`or`、`cond`、`case`、`do`。
- pair/list、vector、char、number、string、symbol、boolean。
- `apply`、`procedure?`、`map`、`for-each` 等高阶过程。
- 当前宏展开能力：top-level `define-syntax` 和实用 `syntax-rules` 子集。
- 通过 `_TailExpression` 实现关键 tail position 的 trampoline。
- textual ports、current ports、`read`、`write`、`display`、file ports。
- escape-only `call/cc` / `call-with-current-continuation`。

### 1.2 当前 Scheme 的调试短板

Scheme reader 目前直接产出普通 Python 值，位置只用于语法错误文本，并没有把稳定 source location 绑定到每个 datum 或 AST 节点。因此当前 interpreter 很难做到：

- 每条执行动作映射回 Scheme 源码行。
- debugger 单步时高亮当前 Scheme 表达式。
- runtime traceback 显示函数名、文件、行列。
- macro expansion 后保留宏调用点和展开点信息。

也就是说，现有 Scheme 语义已经较完整，但“可编译性”和“可调试性”的基础数据结构还没有准备好。

### 1.3 当前 Lua / VM 调试链路

Lua 已经走通从源码到 BytecodeVM 的链路：

```text
Lua source
  -> lexer
  -> parser AST with line/column
  -> analysis: locals / captured locals / upvalues
  -> LuaCompiler
  -> compiler.bytecode.Instruction
  -> BytecodeVM
  -> VMVisualizer / traceback / CLI trace
```

关键点是 Lua compiler 产出的每条 `Instruction` 可以携带：

```python
InstructionDebug(
    SourceLocation(source_name, line, column),
    function_name,
)
```

`BytecodeVM` 和 visualizer 只依赖这些通用 VM 信息：

- `Instruction.debug.location`：当前 PC 对应源码位置。
- `Instruction.debug.function_name`：traceback 中的函数名。
- `BytecodeVM.snapshot_state()`：寄存器、调用栈、upvalue、输出、协程快照。
- `BytecodeVM.drain_events()`：事件流。
- `VMRuntimeError.frames`：运行时错误的调用栈。

因此 Scheme 要接入现有 debugger，核心不是复用 Lua parser，而是产出同一种 `Instruction` 和 debug metadata。

---

## 2. 目标架构

### 2.1 双后端策略

Scheme 后续应保持双后端：

```text
haifa_scheme
  ├─ interpreter backend  # 当前稳定实现，默认路径
  └─ vm backend           # 新增编译路径，逐步覆盖语义和 debugger 能力
```

解释器后端继续作为语义真相源和兼容路径。VM 后端分阶段实现，并在每个阶段用解释器结果作为 oracle 对比，避免一次性重写 Scheme runtime。

推荐初期 CLI 行为：

- 默认仍使用 interpreter。
- 通过 `--backend vm` 或专用调试开关进入 VM 后端。
- VM 后端未支持的高级语义必须明确报错或 fallback，不能静默走出不一致结果。

### 2.2 编译链路

目标 VM 后端链路如下：

```text
Scheme source
  -> located reader / AST
  -> macro expansion
  -> lexical analysis
  -> SchemeCompiler
  -> compiler.bytecode.Instruction[]
  -> BytecodeVM
  -> output / return values / VMVisualizer / traceback
```

各阶段职责：

1. **located reader / AST**
   - 解析源码并保留每个 datum 的 source span。
   - 保持现有 `parse_source()` 兼容，新增编译器专用 parse API。

2. **macro expansion**
   - 编译期维护 macro environment。
   - `define-syntax` 不进入运行时字节码。
   - VM 后端只编译展开后的表达式。

3. **lexical analysis**
   - 识别 local/global binding。
   - 识别被 closure 捕获的变量。
   - 生成函数级 `FunctionInfo`，供 codegen 决定 register/cell/upvalue。

4. **SchemeCompiler**
   - 独立于 `haifa_lua.compiler.LuaCompiler`。
   - 复用 `compiler.bytecode.Opcode`、`Instruction`、`InstructionDebug`。
   - 根据 Scheme truthiness、tail position、multi-value 语义生成指令。

5. **BytecodeVM execution**
   - 复用当前 VM 的 register、call frame、cell、closure、callable、debugger 基础设施。
   - 在必要处新增语言无关的 VM 能力，例如 tail call opcode，而不是添加 Scheme 专用黑盒 evaluator opcode。

### 2.3 模块布局建议

建议新增或扩展：

- `haifa_scheme/ast.py`
  - 定义 located datum / Scheme AST 节点。
  - 所有节点携带 `line`、`column`，必要时携带 end line/column 或 source offset。

- `haifa_scheme/compiler.py`
  - 定义 `SchemeCompiler`。
  - 提供 `compile_source(...)` / `compile_to_bytecode(...)`。

- `haifa_scheme/analysis.py`
  - 做 lexical binding、captured locals、upvalue 分析。

- `haifa_scheme/vm_runtime.py`
  - 将 Scheme `BuiltinFunction` 包装为 VM callable。
  - 管理 Scheme global environment 与 VM registers 的同步。

- `haifa_scheme/debug/traceback.py`
  - 将 `VMRuntimeError` 转换为 Scheme 风格错误。
  - 格式化 Scheme stack traceback。

- `haifa_scheme/cli.py`
  - 增加 backend、trace、stack、break-on-error、visualize 参数。

---

## 3. 底层基础设施改进

### 3.1 Reader / AST Source Map

当前 reader 的 Python datum 很轻，但缺少 debug 所需元信息。VM 编译后端需要新增 located representation。

设计原则：

- 不破坏现有 public API：`parse_source(source)` 继续返回旧式 datum。
- 新增 API，例如 `parse_source_with_locations(source)`，返回 located datum 或 AST。
- `Symbol`、literal、list、dotted list、vector、reader shorthand 都要有位置。
- quote shorthand 例如 `'x` 展开为 `(quote x)` 时，debug 位置应优先指向 quote 表达式本身。

可选实现：

```python
@dataclass(frozen=True)
class SourceSpan:
    file: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None

@dataclass(frozen=True)
class LocatedDatum:
    value: object
    span: SourceSpan
```

后续如果需要更强语义，可再从 located datum lowering 到 explicit AST：

```text
LocatedDatum(list[...])
  -> IfExpr / LambdaExpr / DefineExpr / CallExpr / LiteralExpr / SymbolRef
```

第一阶段不强制一次性建立完整 AST；但 compiler 内部必须能稳定拿到 source location。

### 3.2 Scheme Compiler 与 Lexical Analysis

Scheme 的 lexical analysis 应独立实现，不能依赖 Lua 的 scope 规则。

需要识别：

- top-level binding。
- lambda 参数。
- `let` / `let*` / `letrec` local binding。
- named `let` 自递归 binding。
- 被内层 lambda 捕获的 local。
- `set!` 对 nearest existing binding 的 mutation。

第一版可以保守地将所有 local binding 都放入 `Cell`，以简化 closure mutation；后续优化为：

- 未捕获且不被 `set!` 修改的 local：普通 register。
- 被捕获或需要 mutation 可见性的 local：cell register。

### 3.3 VM 语言语义隔离

当前 `BytecodeVM._is_truthy` 是 Lua/jq 语义：`False` 和 `None` 都是假。Scheme 只有 `#f` 是假，`()` 和 unspecified / void 都不应被当作假。

不能直接修改 VM 全局 truthiness，否则会破坏 Lua/jq。Scheme 编译器在条件跳转时应显式生成：

```text
LOAD_CONST false_reg, False
EQ is_false, condition_reg, false_reg
JNZ is_false, false_label
```

也就是说：

- Scheme `if`、`and`、`or`、`cond`、`do` termination 都使用 Scheme truthiness lowering。
- Lua/jq 继续使用 VM 原有 `JZ` / `JNZ` truthiness。
- 如后续发现重复逻辑过多，可以新增语言无关 opcode，例如 `JSCHEME_FALSE`，但第一版不建议急着扩 opcode。

### 3.4 Scheme Stdlib VM Adapter

当前 stdlib 函数签名是：

```python
func(args: Sequence[Any], context: BuiltinContext | None) -> Any
```

VM 的 callable 路径支持：

- Python callable。
- 带 `__lua_builtin__` 的 VM-aware builtin。
- VM closure dict。
- LuaTable metamethod。

Scheme VM 后端应新增 adapter，而不是修改 Scheme stdlib 函数体：

```python
class SchemeBuiltinAdapter:
    __lua_builtin__ = True

    def __call__(self, args: Sequence[object], vm: BytecodeVM) -> object:
        context = build_scheme_builtin_context(vm)
        return scheme_builtin(args, context)
```

`BuiltinContext` 中的能力要由 VM runtime 提供：

- `apply_func`：可以调用 Scheme builtin adapter 或 VM closure。
- `is_procedure_func`：识别 Scheme builtin adapter、VM closure、escape continuation。
- `call_cc_func`：Phase 9 前可标记 unsupported。
- current input/output port：从 Scheme VM runtime session 注入。

### 3.5 Scheme Debug Traceback

新增 Scheme 专用错误包装：

```text
VMRuntimeError
  -> SchemeRuntimeError with frames
  -> Scheme execution failed: file.scm:line: message
```

traceback 可借鉴 Lua 的结构，但文本使用 Scheme 命名：

```text
stack traceback:
    examples/factorial.scm:4: in function 'fact'
    examples/factorial.scm:7: in function '<chunk>'
```

函数名规则：

- top-level：`<chunk>`。
- `(define (fact n) ...)`：`fact`。
- `(define fact (lambda ...))`：尽量推断为 `fact`。
- 匿名 lambda：`<lambda:line>`。
- macro expansion：第一版使用宏调用点；后续可增加 expanded-from 信息。

### 3.6 CLI / REPL / Visualizer 接入

`pyscheme` 应逐步对齐 `pylua` 的调试能力：

- `--backend interpreter|vm`
- `--trace [all|instructions]`
- `--stack`
- `--break-on-error`
- `--visualize gui|curses`

REPL 需要额外处理：

- interpreter backend 保持当前行为。
- VM backend 每次输入都编译成 chunk 并运行。
- global runtime environment 和 macro environment 需要跨 REPL 输入保留。
- `:backend`、`:trace`、`:env` 可作为后续增强，不要求第一批完成。

### 3.7 Tail Call 与 Continuation

Scheme 的 tail call 是核心语义，不能长期依赖普通 VM call stack。

短期：

- VM MVP 可先实现普通调用，明确标记 tail call 尚未优化。
- 用测试保护已有 interpreter 的 tail trampoline。

中期：

- 新增 `TAIL_CALL_VALUE` 或等价 frame replacement。
- Scheme compiler 标注 tail position。
- 尾调用时复用当前 call frame，不增长 `call_stack`。

continuation 更复杂：

- 当前 interpreter 的 escape-only `call/cc` 基于 Python exception。
- VM 后端不能直接让 continuation jump 被 `BytecodeVM.step()` 包装成普通 `VMRuntimeError`。
- Phase 9 单独设计 escape continuation passthrough 或 VM-level control transfer。
- full re-entrant continuation 不进入第一轮目标。

---

## 4. 分阶段实施计划

### Phase 1: Source Map 与 Located Datum

目标：为 Scheme 编译器和 debugger 建立源码位置基础。

主要改动：

- 增加 `SourceSpan` / located datum 或轻量 AST。
- reader token 解析时计算 line/column。
- 保持现有 `parse_source()` 返回值不变。
- 新增编译器专用 parse API，例如 `parse_source_with_locations(...)`。
- quote、quasiquote、vector、dotted list 都保留表达式位置。

测试验收：

- reader 旧测试保持通过。
- 新增 located parse 测试，覆盖 literal、symbol、list、nested list、quote shorthand。
- 多行表达式能返回正确起始行列。
- 语法错误仍保持现有清晰报错。

边界：

- 不实现 VM 编译。
- 不改变 runtime evaluator。
- 不要求 macro expansion source map 完整，只需保留原始 datum 位置。

### Phase 2: 最小 VM 编译闭环

目标：跑通 Scheme source 到 BytecodeVM 的最短路径，并能进入 visualizer。

主要改动：

- 新增 `SchemeCompiler` skeleton。
- 编译 literal：number、string、boolean、char、vector、empty list、pair datum。
- 编译 `quote`。
- 编译 `begin`。
- 编译简单过程调用：先覆盖 builtin call，例如 `(+ 1 2)`。
- 生成 `InstructionDebug(SourceLocation(...), "<chunk>")`。
- 新增 VM runtime environment，将 Scheme builtin 注册到 VM registers。

测试验收：

- `(+ 1 2 3)` VM 后端结果与 interpreter 一致。
- `'(1 2 x)` VM 后端格式化结果与 interpreter 一致。
- `begin` 返回最后一个表达式。
- visualizer 能显示 source，并高亮当前行。

边界：

- 不支持 user-defined binding。
- 不支持 lambda。
- 不支持宏。
- 不改变 `pyscheme` 默认后端。

### Phase 3: Global Define、Symbol Lookup、Set

目标：让 VM 后端支持 top-level 程序状态。

主要改动：

- 编译 top-level `(define name expr)`。
- 编译 symbol lookup。
- 编译 `(set! name expr)`。
- 定义 Scheme global register mangling，例如：

```text
G_SCHEME_<escaped-symbol-name>
```

- VM 运行前将 Scheme global environment 写入 registers。
- VM 运行后将变化同步回 Scheme global environment。

测试验收：

- `(define x 1) x` 返回 `1`。
- `(define x 1) (set! x 2) x` 返回 `2`。
- 未绑定 symbol 报 Scheme 风格错误。
- REPL 或多次 `run_source` 使用同一 environment 时，global binding 可延续。

边界：

- `define-syntax` 不在本阶段处理。
- local lexical scope 仍不支持。

### Phase 4: Lambda、Lexical Scope、Closure

目标：让 Scheme VM 后端支持用户过程、词法作用域和闭包。

主要改动：

- 编译 `lambda`。
- 编译函数调用。
- 编译 `(define (name params...) body...)`。
- 编译 local binding 基础结构。
- lexical analysis 识别 captured local。
- 复用 VM `MAKE_CELL`、`CELL_GET`、`CELL_SET`、`CLOSURE`、`BIND_UPVALUE`。
- 为函数体生成 function label 和 `function_name` debug metadata。

测试验收：

- 简单 lambda 调用。
- recursive factorial。
- closure counter。
- closure 捕获变量后，`set!` mutation 可见。
- 错误 traceback 能显示函数名。

边界：

- tail call 仍可先用普通调用。
- `letrec` 的 uninitialized read 语义可在 Phase 5 完成。

### Phase 5: Control Forms 与 Scheme Truthiness

目标：覆盖 Scheme Core+ 控制结构，并确保条件语义不受 Lua truthiness 影响。

主要改动：

- 编译 `if`，包含 optional alternate。
- 编译 `and` / `or` short-circuit。
- 编译 `cond`。
- 编译 `case`，使用 `equal_value` 或等价 builtin helper。
- 编译 `let`、named `let`、`let*`、`letrec`。
- 编译 `do`，保持 initializer 在 outer environment 求值、step simultaneous update。
- 条件判断统一 lower 为 `value == False`，不直接依赖 VM `_is_truthy`。

测试验收：

- `(if #f 1 2)` 返回 `2`。
- `(if '() 1 2)` 返回 `1`。
- `(if (begin) 1 2)` 或 void-like 值不被误判为假。
- named let tail-recursive factorial 结果正确。
- `case` datum matching 与 interpreter 一致。
- `do` initializer、step、termination、result expressions 与 interpreter 一致。

边界：

- tail call optimization 仍不作为验收要求。
- macro expansion 仍不进入 VM 后端。

### Phase 6: Debugger / CLI 集成

目标：让 Scheme VM 后端获得接近 Lua 的调试体验。

主要改动：

- `pyscheme` 增加：
  - `--backend interpreter|vm`
  - `--trace`
  - `--stack`
  - `--break-on-error`
  - `--visualize gui|curses`
- 新增 Scheme traceback formatter。
- 将 `VMRuntimeError` 包装为 Scheme 风格错误。
- visualizer 初始化时注入 Scheme VM environment。
- CLI debug path 支持 instruction trace。

测试验收：

- `python -m haifa_scheme.cli -e "(+ 1 2)" --backend vm --print-output` 输出正确。
- `--visualize curses` 能打开 headless visualizer 并读取源码行。
- runtime error 显示 `file.scm:line: message`。
- `--stack` 输出 stack traceback。
- interpreter backend 行为不变。

边界：

- 不要求 REPL 完整支持 visualizer。
- 不要求 macro expansion traceback 展示展开链。

### Phase 7: Macro 编译期展开

目标：将现有 macro 能力接入 VM compiler。

主要改动：

- VM compiler 维护 compile-time macro environment。
- top-level `define-syntax` 更新 macro environment，不生成 runtime instruction。
- 普通表达式编译前先 macro expand。
- 复用 `haifa_scheme/macros.py` 的 `SyntaxRulesMacro` 和 `parse_syntax_rules`。
- expansion 后的节点保留宏调用点 source location。

测试验收：

- `when` / `unless` 类基础宏在 VM 后端运行正确。
- literal identifier matching 行为与 interpreter 一致。
- 当前已支持的 ellipsis 子集在 VM 后端可用。
- 宏展开错误能指出宏调用位置。

边界：

- 不扩大当前 macro 能力边界。
- full hygiene 和 nested ellipsis 仍按现有路线图处理。
- 不引入独立 macro VM。

### Phase 8: Tail Call 支持

目标：让 Scheme VM 后端满足 Scheme 核心尾调用要求。

主要改动：

- 在 compiler 中标注 tail position：
  - lambda body 最后一项。
  - `begin` 最后一项。
  - `if` consequent / alternate。
  - `let` family body。
  - `cond` / `case` selected body。
  - `do` termination result。
- 新增 VM tail call 能力：
  - 首选 `TAIL_CALL_VALUE` opcode。
  - 或在 `CALL_VALUE` 增加 tail flag，但保持 Lua 行为不变。
- tail call 执行时替换当前 frame 参数和 registers，不追加 call frame。
- visualizer / traceback 保持当前 tail frame 可理解。

测试验收：

- 大规模 tail-recursive countdown 不增长 VM call stack。
- tail-recursive factorial 结果正确。
- 非 tail recursive 调用仍保留完整 traceback。
- Lua call 行为不变。

边界：

- 不要求 full continuation。
- 不要求跨 Python builtin C-call boundary 的 tail call。

### Phase 9: 高级语义与完整兼容

目标：补齐 Scheme VM 后端与 interpreter 的高级能力差距。

主要改动：

- 完整接入 textual ports 和 current ports。
- 完整支持 higher-order builtins：
  - `apply`
  - `procedure?`
  - `map`
  - `for-each`
- 设计 escape-only `call/cc` 的 VM 后端：
  - continuation object 捕获当前动态 extent。
  - continuation jump 不被误包装为普通 runtime error。
  - escaped continuation 失效后再次调用报错。
- 对 macro hygiene 和 source expansion trace 做后续增强设计。

测试验收：

- ports 相关测试在 VM 后端通过。
- `map` / `for-each` 可调用 VM closure。
- `apply` 可展开 proper list 参数并调用 VM closure / builtin。
- full re-entrant / multi-shot `call/cc` 在 VM 后端通过。
- continuation escape 经过 higher-order builtin callback 仍正确。

边界：

- binary ports、append-mode file ports、完整 R5RS/R7RS 兼容继续保持 out of scope。

已完成能力清单（当前实现状态）：

- textual ports 与 current ports 已接入 VM 后端：
  - `run_source_vm(...)` 支持注入 `input` / `output`。
  - `current-input-port` / `current-output-port` 在 VM 后端可用。
  - `display` / `write` / `newline` / `read` / `open-input-file` / `open-output-file` /
    `close-input-port` / `close-output-port` / `input-port?` / `output-port?`
    已在 VM 黑盒测试中覆盖。
- higher-order builtins 已与 VM closure / builtin 互通：
  - `apply` 可展开 proper list 参数并调用 builtin 或 VM closure。
  - `procedure?` 可识别 builtin、VM closure、escape continuation。
  - `map` 可调用 VM closure，且行为与 interpreter 对齐。
  - `for-each` 可调用 VM closure，且副作用会正确回写到 VM 全局环境。
- `call/cc` 已在 VM 后端升级为可恢复 continuation：
  - continuation object 会捕获可恢复的 VM 控制状态快照，而不再只是一段 escape token。
  - 同一 continuation 可在同一 VM 执行中被多次恢复，支持 full re-entrant / multi-shot 语义。
  - continuation 脱离原始 dynamic extent 后仍可恢复到捕获点，并保留共享 store / `set!` 副作用。
  - continuation resume 经过 `map` / `for-each` callback 等 higher-order builtin 边界仍可正确回到捕获点。
  - continuation resume 不会被 `BytecodeVM.step()` 误包装为普通 `VMRuntimeError`。
- 共享 VM 回归已验证：
  - `haifa_scheme` 全量测试通过。
  - `haifa_lua` 全量测试通过，说明本阶段没有破坏 Lua 既有调用/控制流语义。

剩余 out of scope / 后续增强项：

- continuation 目前仍以“单次 `run_source_vm(...)` 执行期内可恢复”为边界：
  - 仍不支持把 continuation 持久化到另一台 `BytecodeVM` / 另一轮 `run_source_vm(...)` 中恢复。
  - `dynamic-wind` / 参数对象等与 continuation 的更完整动态语义尚未设计。
  - 当前实现保留 Scheme 风格共享 store 语义，不会回滚已经发生的 I/O / 端口副作用。
- ports 仍保持当前教学型边界：
  - binary ports 仍未纳入。
  - append-mode file ports 仍未纳入。
  - 更完整的 current port / dynamic-wind 交互语义仍未设计。
- macro 相关增强仍未进入本阶段实现：
  - full hygiene 仍未补齐。
  - source expansion trace 仍未进入 debugger / traceback 展示链路。
- 更完整的 Scheme 兼容性仍待后续阶段推进：
  - 多值（multiple values）与 higher-order builtin / continuation 的联动语义尚未扩展。
  - 完整 R5RS/R7RS number / port / library 系统继续保持 out of scope。

---

## 5. 风险与原则

### 5.1 不破坏 Lua / jq

所有 VM 基础设施改动都必须保持语言语义隔离：

- 不修改全局 `_is_truthy` 来适配 Scheme。
- 不改变 Lua closure、metatable、coroutine、module 行为。
- 新 opcode 必须有清晰的 backward-compatible 行为。
- visualizer 对无 Scheme metadata 的旧 bytecode 保持兼容。

每个涉及 VM 的阶段都需要至少跑一个 Lua smoke regression。

### 5.2 不把 Scheme 塞进 Lua Compiler

Scheme compiler 应独立实现。Lua compiler 的价值是参考：

- instruction emission 模式。
- debug metadata 模式。
- closure/upvalue lowering 模式。
- CLI debug path 模式。

但 Scheme 不应复用 Lua AST、Lua scope rule 或 Lua truthiness。

### 5.3 解释器继续作为语义真相源

VM 后端早期覆盖不完整是正常状态。每个阶段应做到：

- interpreter backend 行为不变。
- VM backend 支持的功能与 interpreter 对齐。
- VM backend 不支持的功能明确报错。
- 不用 fallback 掩盖语义差异，除非 CLI 明确标记 fallback 行为。

### 5.4 高风险语义分阶段处理

以下功能不能过早混入 MVP：

- `call/cc`
- full hygiene
- full re-entrant continuation
- macro expansion trace
- 完整 R5RS/R7RS number / port / library 系统

这些功能应在 VM 编译、debugger、closure、tail call 稳定后再逐项推进。

### 5.5 每阶段独立测试与可回滚

后续实现建议遵循：

- 每个 Phase 单独提交。
- 每个功能点有单元测试。
- Phase 内先做黑盒语义测试，再补 bytecode shape / debugger 测试。
- Windows 验证命令使用：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest haifa_scheme\tests
python -m pytest haifa_lua\tests\test_parser_tables.py
```

文档阶段本身只新增 Markdown，不需要运行测试。
