# HaifaArmV9VM 规划

## 背景

当前 Haifa VM 是面向语言实现的高级寄存器虚拟机。它的寄存器是无限命名槽位，实际承担了 CPU 寄存器、局部变量槽、临时变量、全局变量入口以及部分运行时状态的角色。这对 Lua/Scheme 前端很友好，也便于快速扩展闭包、多返回值、表、协程和调试能力。

如果希望让寄存器和内存模型更接近手机芯片中的 ARM CPU，建议保留现有 `BytecodeVM`/HaifaVM，并新增一个低层目标：`HaifaArmV9VM`。它不追求完整模拟真实 ARMv9-A CPU，而是实现一个 ARMv9 风格的教学与后端 VM：

- 有固定数量的通用寄存器。
- 显式区分寄存器、栈、堆、全局区和常量池。
- 采用 load/store 架构，普通运算只作用于寄存器。
- 有调用约定、栈帧、链接寄存器和条件码。
- 通过 lowering 从当前高级字节码生成 ARMv9 风格字节码。

## 总体目标

1. 保留当前 `BytecodeVM` 作为高级语言语义 VM，确保 Lua/Scheme/JQ 现有路径不被破坏。
2. 新增 `HaifaArmV9VM` 作为独立 VM，文件建议放在 `compiler/armv9_vm.py`。
3. 新增 ARMv9 风格指令定义，文件建议放在 `compiler/armv9_bytecode.py`。
4. 新增 lowering 层，把当前 `Opcode` 高级字节码转换为 ARMv9 风格指令。
5. 复用现有 GUI/TUI 调试器的交互能力，但通过调试快照适配器显示 ARMv9 的寄存器和内存。

## 非目标

- 不实现完整真实 ARMv9-A ISA。
- 不模拟 EL0/EL1/EL2/EL3、MMU、TLB、异常向量表、中断、SVE/SME、Pointer Authentication、Memory Tagging 等复杂硬件特性。
- 不把 Lua/Scheme 前端一次性迁移到 `HaifaArmV9VM`。
- 不删除或替换当前 `BytecodeVM` 指令集。

## 架构定位

推荐 pipeline：

```text
Lua/Scheme AST
    |
    v
当前 Haifa 高级字节码 Opcode
    |
    v
ArmV9 lowering
    |
    v
HaifaArmV9Instruction
    |
    v
HaifaArmV9VM
```

这样做有三个好处：

- 现有语言编译器不用立刻重写。
- `BytecodeVM` 继续承担动态语言语义验证基准。
- `HaifaArmV9VM` 可以逐步成为教学用低层 VM、优化后端或未来 JIT/汇编输出的中间目标。

## 寄存器模型

`HaifaArmV9VM` 使用 AArch64/ARMv9 风格的 64 位通用寄存器命名：

| 名称 | 角色 |
| --- | --- |
| `X0` - `X7` | 参数和返回值寄存器，`X0` 为第一返回值 |
| `X8` - `X15` | 调用方保存临时寄存器 |
| `X16` - `X18` | 内部临时寄存器，`X18` 保留给平台/VM |
| `X19` - `X28` | 被调用方保存寄存器 |
| `X29` | `FP`，帧指针 |
| `X30` | `LR`，链接寄存器 |
| `SP` | 栈指针 |
| `PC` | 程序计数器 |
| `NZCV` | 条件码：negative、zero、carry、overflow |

为了教学清晰，第一阶段可以只支持 `X0` - `X15`、`FP`、`LR`、`SP`、`PC`、`NZCV`。后续再补齐完整寄存器集。

## 内存模型

`HaifaArmV9VM` 需要显式内存空间：

| 区域 | 用途 |
| --- | --- |
| code | 指令区，只读 |
| const_pool | 常量池，保存字符串、数字、布尔、nil、函数元数据 |
| stack | 栈内存，保存栈帧、溢出变量、返回地址、保存寄存器 |
| heap | 堆对象，保存 Lua table、closure、cell、多返回值对象 |
| globals | 全局环境，可作为独立字典，也可映射为 heap/global segment |

寄存器只保存原始值或对象引用。变量不再默认都是寄存器名，而是经过寄存器分配后进入固定寄存器；放不下的变量 spill 到栈。

## 指令集草案

### 数据传送

| 指令 | 语义 |
| --- | --- |
| `MOV dst, src` | 寄存器间移动 |
| `MOVI dst, imm` | 加载小立即数 |
| `LDR dst, [base, offset]` | 从内存加载 |
| `STR src, [base, offset]` | 写入内存 |
| `LDRC dst, const_id` | 从常量池加载 |
| `ADR dst, label` | 取标签地址 |

### 算术与位运算

| 指令 | 语义 |
| --- | --- |
| `ADD dst, lhs, rhs` | 加法 |
| `SUB dst, lhs, rhs` | 减法 |
| `MUL dst, lhs, rhs` | 乘法 |
| `SDIV dst, lhs, rhs` | 有符号除法 |
| `MOD dst, lhs, rhs` | 取模，教学扩展 |
| `NEG dst, src` | 取负 |
| `AND dst, lhs, rhs` | 位与 |
| `ORR dst, lhs, rhs` | 位或 |
| `EOR dst, lhs, rhs` | 位异或 |
| `LSL dst, lhs, rhs` | 逻辑左移 |
| `LSR dst, lhs, rhs` | 逻辑右移 |
| `ASR dst, lhs, rhs` | 算术右移 |

### 比较与条件码

| 指令 | 语义 |
| --- | --- |
| `CMP lhs, rhs` | 设置 `NZCV` |
| `CMPI lhs, imm` | 与立即数比较 |
| `CSET dst, cond` | 条件成立写入 `1`，否则写入 `0` |

### 控制流

| 指令 | 语义 |
| --- | --- |
| `B label` | 无条件跳转 |
| `B.EQ label` | zero 为真时跳转 |
| `B.NE label` | zero 为假时跳转 |
| `B.LT label` | 小于跳转 |
| `B.GT label` | 大于跳转 |
| `BL label` | 调用函数，写入 `LR` |
| `BR reg` | 跳转到寄存器地址 |
| `RET` | 跳回 `LR` |
| `HALT` | 停机 |

### 运行时对象

真实 ARM 不会有这些高级对象指令，但 HaifaArmV9VM 需要保留动态语言教学可读性：

| 指令 | 语义 |
| --- | --- |
| `NEW_TABLE dst` | 创建 Lua table 对象，返回 heap 引用 |
| `TABLE_GET dst, table, key` | 表读取 |
| `TABLE_SET table, key, value` | 表写入 |
| `NEW_CLOSURE dst, label, env` | 创建闭包对象 |
| `CELL_GET dst, cell` | upvalue/cell 读取 |
| `CELL_SET cell, src` | upvalue/cell 写入 |
| `CALL_RUNTIME name` | 调用 VM 内置运行时函数 |

这些指令属于 Haifa 扩展，不是 ARMv9 原生指令。文档和 UI 中应明确标注为 runtime pseudo-op。

## 调用约定

第一版建议采用简化 AArch64 调用约定：

- `X0` - `X7` 传递前 8 个参数。
- `X0` 返回第一个值。
- 多返回值通过 heap 中的 `MultiReturn` 对象返回，引用放在 `X0`。
- `BL` 写入 `LR`。
- 函数入口保存 `FP`、`LR`，建立新栈帧。
- 函数退出恢复 `FP`、`LR`，执行 `RET`。
- `X8` - `X15` 由调用方负责保存。
- `X19` - `X28` 后续补齐时由被调用方负责保存。

栈帧布局建议：

```text
高地址
+------------------+
| 参数溢出区       |
| 局部变量 spill   |
| 保存寄存器       |
| old FP           | <- FP
| return LR        |
+------------------+
低地址             <- SP
```

## Lowering 策略

当前 `BytecodeVM` 是无限命名寄存器，lowering 需要做三件事：

1. 把无限命名寄存器映射到有限 `Xn` 寄存器。
2. 对超出寄存器容量的变量生成 `STR`/`LDR` spill。
3. 把高级指令拆成 ARMv9 风格指令序列。

示例：

```text
Haifa Opcode:
  LOAD_IMM t1, 1
  ADD t2, a, t1

HaifaArmV9:
  MOVI X9, #1
  LDR  X10, [FP, a_slot]
  ADD  X11, X10, X9
  STR  X11, [FP, t2_slot]
```

第一阶段 lowering 可以不做复杂寄存器分配，先采用保守策略：

- 固定 `X9` - `X15` 为 scratch。
- 每个高级寄存器都有一个 stack slot。
- 每条高级指令先 `LDR` 输入，再执行运算，最后 `STR` 输出。

这样代码较慢，但正确性简单，适合教学与调试。后续再引入 liveness 和 register allocation。

## GUI/TUI Debugger 影响

结论：不需要完全重新开发，但需要改造为 VM 无关的调试快照模型。

当前 GUI/TUI visualizer 直接依赖 `BytecodeVM` 的字段：

- `instructions`
- `pc`
- `registers`
- `stack`
- `call_stack`
- `pending_params`
- `last_return`
- `output`
- coroutine snapshots/events

`HaifaArmV9VM` 的核心状态会变成：

- `instructions`
- `pc`
- `regs`
- `nzcv`
- `memory.stack`
- `memory.heap`
- `frames`
- `globals`
- `output`

因此推荐新增一个调试协议，而不是复制一份 GUI：

```python
class DebugSnapshot(Protocol):
    instructions: Sequence[object]
    pc: int
    registers: Mapping[str, object]
    memory_sections: Mapping[str, object]
    call_stack: Sequence[object]
    output: Sequence[str]
    events: Sequence[object]
```

然后提供两个适配器：

- `BytecodeVMDebugAdapter`
- `ArmV9VMDebugAdapter`

GUI/TUI 继续负责布局、单步、断点、自动运行、源码高亮；适配器负责把不同 VM 的内部状态转换为统一快照。

### GUI 最小改造

- 把 visualizer 构造函数从只接受 `BytecodeVM` 改成接受 `vm` 加 `debug_adapter`。
- register 面板改为显示 adapter 提供的 `registers`。
- 新增 memory 面板或复用 stack/upvalue 区域显示 `stack`、`heap`、`globals`。
- 指令列表支持 `HaifaArmV9Instruction` 的格式化。
- reset 逻辑通过 adapter 创建同类型 VM。

### GUI 后续增强

- ARMv9 模式下突出显示 `PC`、`SP`、`FP`、`LR`、`NZCV`。
- 显示当前栈帧布局和 spill slot。
- 支持点击内存引用跳转到 heap 对象详情。
- 在教学 HTML demo 中展示 "高级 HaifaVM 指令 -> ARMv9 lowering 指令" 双栏对照。

## Phase 拆分

### Phase 0：规格冻结与测试基线

- [x] 建立 `docs/haifa_armv9_vm_plan.md`。
- [x] 明确 `HaifaArmV9VM` 是新增 VM，不替换 `BytecodeVM`。
- [x] 记录当前 Lua/Scheme/VM 测试基线。
- [x] 列出最小可执行 ARMv9 风格指令集。

#### HaifaArmV9VM 定位声明

`HaifaArmV9VM` 是**新增的独立 VM**，不替换 `BytecodeVM`：

- `BytecodeVM`（`compiler/bytecode_vm.py`）继续作为 Lua/Scheme/JQ 的高级语言语义 VM，现有前端编译流水线（lexer → parser → analysis → compiler → bytecode → BytecodeVM）保持不变。
- `HaifaArmV9VM`（`compiler/armv9_vm.py`）作为并行存在的低层教学目标，通过 `compiler/armv9_lowering.py` 从高级字节码 lowering 生成 ARMv9 风格指令。
- 两者共享调试基础设施（通过 debug adapter 协议），但执行引擎、寄存器模型、内存模型完全独立。
- 任何对 `HaifaArmV9VM` 的改动不得修改 `BytecodeVM` 的指令集、执行逻辑或现有 Lua/Scheme/JQ 默认执行路径。

#### 测试基线（Phase 0 时间点）

在 Phase 0 时间点，现有测试套件状态：

| 测试范围 | 测试数 | 状态 |
| --- | --- | --- |
| `compiler/tests/` | 170 | 全部通过 |
| `haifa_lua/tests/` | 134 | 全部通过 |
| 合计（compiler + lua） | 304 | 全部通过 |
| 全量（含 jq/scheme/vm/其它） | 626 | 626 通过，1 预存失败* |

\* 预存失败：`test_chinese_gui.py::test_chinese_display`，因无头环境下 pygame.font 未初始化导致，与 ARMv9 VM 无关，不纳入回归基线。

后续每个 Phase 完成后需确认：上述测试无新增失败。

#### 最小可执行 ARMv9 风格指令集

Phase 0 冻结的最小可执行指令集，覆盖算术、比较、分支、停机，足以编写简单的循环与条件程序：

| 指令 | 语义 | 操作数 |
| --- | --- | --- |
| `MOVI dst, imm` | 加载立即数 | dst=寄存器, imm=整数 |
| `MOV dst, src` | 寄存器间移动 | dst=寄存器, src=寄存器 |
| `ADD dst, lhs, rhs` | 加法 | dst, lhs, rhs=寄存器 |
| `SUB dst, lhs, rhs` | 减法 | dst, lhs, rhs=寄存器 |
| `CMP lhs, rhs` | 比较并设置 NZCV | lhs, rhs=寄存器 |
| `B label` | 无条件跳转 | label |
| `B.EQ label` | Z=1 时跳转 | label |
| `B.NE label` | Z=0 时跳转 | label |
| `HALT` | 停机 | 无 |

后续 Phase 将在此基础上增量扩展：

- **Phase 2**：补齐 `MUL`、`B.LT`、`B.GT`、`CSET`、`LDRC`。
- **Phase 3**：补齐 `BL`、`RET`、`LDR`、`STR`、栈帧与调用约定。
- **Phase 4**：补齐 `SDIV`、`MOD`、`NEG`、`AND`、`ORR`、`EOR`、`LSL`、`LSR`、`ASR`、`CMPI`、`BR`、`ADR`。
- **Phase 5–6**：补齐运行时对象指令（`NEW_TABLE`、`TABLE_GET/SET`、`NEW_CLOSURE`、`CELL_GET/SET`、`CALL_RUNTIME`）。

验收标准：

- 文档合入。
- 现有测试全部通过。
- 没有修改现有 Lua/Scheme 默认执行路径。

### Phase 1：ArmV9 字节码数据结构

- [x] 新增 `compiler/armv9_bytecode.py`。
- [x] 定义 `ArmV9Opcode`、`ArmV9Instruction`、`ArmV9Debug`。
- [x] 提供指令 pretty printer。
- [x] 添加序列化/反序列化辅助，便于 demo 与调试。

验收标准：

- 可以构造和打印 ARMv9 风格指令。
- AST syntax check 和单元测试通过。

### Phase 2：最小 HaifaArmV9VM

- [x] 新增 `compiler/armv9_vm.py`。
- [x] 实现寄存器文件：`X0` - `X15`、`FP`、`LR`、`SP`、`PC`、`NZCV`。
- [x] 实现内存模型：const pool、stack、heap、globals。
- [x] 实现最小指令：`MOVI`、`MOV`、`ADD`、`SUB`、`CMP`、`B`、`B.EQ`、`B.NE`、`HALT`。
- [x] 添加 VM 单元测试。

验收标准：

- 可以运行手写 ARMv9 风格程序完成算术、比较和分支。
- VM 状态可被快照读取。

### Phase 3：栈帧与调用约定

- [x] 实现 `BL`、`RET`、`LDR`、`STR`。
- [x] 建立 `FP`/`SP` 栈帧布局。
- [x] 支持 `X0` - `X7` 参数传递和 `X0` 返回。
- [x] 添加递归函数测试，例如 factorial。

验收标准：

- 手写 ARMv9 风格 factorial 可以运行。
- 调用栈和栈帧快照可视化数据完整。

### Phase 4：从 Haifa Opcode 到 ArmV9 lowering

- [x] 新增 `compiler/armv9_lowering.py`。
- [x] 支持 lowering：`LOAD_IMM`、`LOAD_CONST`、`MOV`、`ADD`、`SUB`、`MUL`、`EQ`、`LT`、`GT`、`JMP`、`JZ`、`JNZ`、`PRINT`、`HALT`。
- [x] 先采用 stack-slot-only 保守寄存器分配。
- [x] 添加高级 bytecode 与 ARMv9 bytecode 输出对照测试。

验收标准：

- 简单 Lua 编译出的高级 bytecode 可以 lowering 并在 `HaifaArmV9VM` 中跑通。
- 输出结果与 `BytecodeVM` 一致。

### Phase 5：运行时对象与 Lua table

- [x] 实现 heap object 引用模型。
- [x] 支持 `NEW_TABLE`、`TABLE_GET`、`TABLE_SET`。
- [x] 支持字符串、布尔、nil、LuaTable 的 const pool 表达。
- [x] 添加 Lua table 构造、索引和更新测试。

验收标准：

- Lua table 基础脚本在 `BytecodeVM` 与 `HaifaArmV9VM` 下输出一致。
- heap 对象可在调试器中查看。

### Phase 6：闭包、cell 与多返回值

- [x] 支持 `NEW_CLOSURE`、`CELL_GET`、`CELL_SET`。
- [x] 支持 upvalue 环境对象。
- [x] 支持 `MultiReturn` heap 对象。
- [x] lowering 覆盖 `MAKE_CELL`、`CELL_GET`、`CELL_SET`、`CLOSURE`、`CALL_VALUE`、`RETURN_MULTI`、`RESULT_LIST`。

验收标准：

- Lua closure counter、多返回值、vararg 的核心案例输出一致。
- 调试器可显示 closure 引用和 cell 内容。

### Phase 7：调试器适配

- [x] 新增 VM debug adapter 协议。
- [x] 为 `BytecodeVM` 实现兼容 adapter。
- [x] 为 `HaifaArmV9VM` 实现 adapter。
- [x] GUI visualizer 使用 adapter 读取状态（`_vm_snapshot()`，支持 `HaifaArmV9VM`）。
- [x] TUI visualizer 使用 adapter 读取状态（`_vm_snapshot()`，支持 `HaifaArmV9VM`）。

验收标准：

- 现有 `BytecodeVM` GUI/TUI 行为不退化。
- `HaifaArmV9VM` 能在 GUI/TUI 中单步、断点、查看寄存器和内存。

### Phase 8：教学 HTML Demo

- [x] 扩展 `docs/lua-vm-demo`，增加 ARMv9 模式。
- [x] 同一段 Lua 源码展示高级 bytecode 和 ARMv9 lowering bytecode。
- [x] 显示 `X0` - `X15`、`SP`、`FP`、`LR`、`NZCV`（新增 NZCV 面板，高亮置位标志）。
- [x] 显示 stack/heap/global memory（const_pool/stack/heap/globals 分区渲染）。

验收标准：

- 入门同学可以通过浏览器看到 "变量 -> 高级寄存器 -> ARMv9 寄存器/内存" 的映射过程。
- demo 数据由真实 VM 执行快照导出，不手写伪状态。

### Phase 9：寄存器分配优化

- [x] 增加 liveness analysis。
- [ ] 实现线性扫描寄存器分配。
- [x] 减少不必要的 `LDR`/`STR`（basic-block 寄存器缓存，支持开关）。
- [x] 输出 spill report 供教学使用（`ArmV9RegisterAllocationReport`）。

验收标准：

- lowering 后指令数明显减少。
- 优化前后输出一致。
- 调试器可切换查看 naive lowering 与 allocated lowering。

## 推荐提交节奏

1. 文档和测试基线单独提交。
2. `armv9_bytecode.py` 单独提交。
3. 最小 `armv9_vm.py` 单独提交。
4. lowering 基础单独提交。
5. 调试器 adapter 单独提交。
6. HTML demo ARMv9 模式单独提交。

这样每一步都可 review、可回滚，也不会影响当前稳定的 Lua/Scheme 执行路径。
