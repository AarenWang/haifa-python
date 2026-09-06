# AArch64 模拟器项目规划

## 背景

当前 `compiler/armv9_vm.py` 中的 `HaifaArmV9VM` 是一个"ARMv9 风格的教学 VM"。它借用 ARM 的寄存器命名（X0–X15、SP/FP/LR/PC、NZCV）和概念（BL/RET、LDR/STR），但本质上是：

- 寄存器里存任意 Python 对象，不是固定宽度整数
- 内存是四个独立 Python 容器（const_pool / stack / heap / globals），不是统一字节寻址地址空间
- 指令是 Python 对象 `ArmV9Instruction`，没有二进制编码
- 条件码 V 恒为 False，C 简化处理
- 无法执行真实 ARM 汇编代码

这些限制使得它无法让学习者观察"真实 CPU 如何从二进制机器码执行程序"。本项目要新建一个独立的 AArch64 模拟器，弥补这一缺口。

## 定位与目标

### 定位

**教学型 AArch64 模拟器**：能编码、能解码、能执行真实 AArch64 汇编子集，让学习者理解"CPU 如何从字节执行程序"。

不是：
- 不是完整 ARMv9-A CPU 模拟（不模拟 SVE2/PAC/MTE/MMU/Cache/多核）
- 不是 ARM 官方架构验证工具
- 不是面向性能的 JIT 模拟器（如 QEMU）

### 核心目标

1. **二进制编码 + 解码**：实现 AArch64 定长 4 字节指令的编码器（assembler）与解码器（disassembler），理解 ARM 指令的 bit-field 编码格式。
2. **统一字节寻址内存**：实现线性字节地址空间，支持指针运算、任意宽度读写、栈操作。
3. **真实标志位运算**：NZCV 四个标志位全部按 ARM Architecture Reference Manual 规范计算，包括进位（C）与溢出（V）。
4. **约 60–80 条核心指令**：覆盖算术、逻辑、移位、比较、条件选择、分支、load/store，能编写和执行完整的汇编程序（循环、函数调用、递归、数组操作）。
5. **完整 fetch-decode-execute 循环**：PC → 从内存取 4 字节 → 解码 → 执行 → 更新 PC，模拟真实 CPU 执行流程。

### 与现有项目的关系

新模拟器是独立模块，不修改现有 `HaifaArmV9VM`。未来的衔接路径：

```
现有 Haifa 高级字节码 (compiler/bytecode.py)
    |
    v
现有 lowering (compiler/armv9_lowering.py)  ──→  HaifaArmV9VM（教学 VM，保留）
    |
    v（未来扩展）
AArch64 汇编器 → 二进制机器码 → 新 AArch64 模拟器执行
```

当前阶段只做模拟器本身，不涉及从 Haifa 字节码到 AArch64 的编译路径。

## 选型说明

### 为什么选 AArch64（ARMv8-A 基础 ISA）

- **当前部署量最大**：ARMv8-A AArch64 覆盖树莓派 3/4、Apple Silicon（M1–M4）、骁龙、天玑等主流芯片。
- **与 v9 兼容**：ARMv9-A 的核心 64 位执行状态与 v8-A 共享相同基础 ISA，学一套通吃。
- **编码干净**：2011 年重新设计，定长 4 字节编码，比 ARMv7 的 Thumb/ARM 混合模式简单得多。
- **文档充分**：ARM 官方 Architecture Reference Manual + 大量社区教程。

### 为什么不选其他

- **ARMv7-A（32 位）**：遗产架构，Thumb/ARM 双模式编码复杂，学习收益低。
- **x86-64**：变长 1–15 字节编码，历史包袱重，不适合从零教学。
- **完整 ARMv9-A**：SVE2/PAC/MTE 等扩展极复杂，偏离教学目标。

## 架构设计

```
arm_emulator/
├── __init__.py
├── registers.py          # 寄存器文件：X0–X30、SP、PC、PSTATE(NZCV)
├── memory.py             # 统一字节寻址内存： bytearray + 读写辅助
├── instructions.py       # 指令定义：编码格式常量、枚举、bit-field 工具
├── encoder.py            # 汇编器：文本汇编 → 4 字节二进制编码
├── decoder.py            # 反汇编器：4 字节二进制 → 文本汇编
├── executor.py           # 执行引擎：fetch-decode-execute 循环
├── cli.py                # 命令行：汇编/反汇编/运行
└── tests/
    ├── test_registers.py
    ├── test_memory.py
    ├── test_encoder.py
    ├── test_decoder.py
    └── test_executor.py
```

### 核心数据模型

#### 寄存器（registers.py）

- 31 个 64 位通用寄存器 X0–X30，存储为固定宽度整数（使用 Python int + 掩码截断）
- SP（栈指针）、PC（程序计数器），各 64 位
- PSTATE 条件标志：N、Z、C、V（四个布尔值）
- W0–W30 是 X0–X30 的低 32 位视图（写入时高 32 位清零）
- 读写时按 32/64 位宽度自动处理符号扩展与零扩展

#### 内存（memory.py）

- 底层为 `bytearray`，统一字节寻址线性地址空间
- 小端序（little-endian）
- 支持读/写 8/16/32/64 位数据，自动处理对齐（教学版默认不抛对齐异常，但记录对齐状态）
- 支持加载程序到指定地址、读取指令、读写数据
- 预留内存映射 I/O 区域（如约定 0x0900_0000 为串口输出，写入即打印）

#### 指令编码（instructions.py）

- 定义 AArch64 指令的 bit-field 编码常量（如 ADD 的 sf/opc/shift/Rm/imm6/Rn/Rd 字段）
- 提供位域提取/拼接工具函数
- 指令类型枚举与助记符映射

#### 汇编器（encoder.py）

- 输入：文本汇编（如 `ADD X0, X1, X2`、`MOV X0, #42`）
- 输出：4 字节二进制编码
- 支持：寄存器、立即数、移位修饰（LSL/LSR/ASR/ROR）、寻址模式
- 两遍扫描：第一遍收集标签地址，第二遍生成编码

#### 反汇编器（decoder.py）

- 输入：4 字节二进制
- 输出：文本汇编
- 按 AArch64 编码格式逐位匹配指令类型

#### 执行引擎（executor.py）

- fetch：从 PC 地址读取 4 字节
- decode：调用 decoder 解析指令
- execute：执行对应操作，更新寄存器与标志位
- update PC：默认 PC += 4，分支指令修改 PC
- 支持单步执行、断点、运行到结束
- 可选执行日志：每步打印 PC、指令、寄存器变化

## 指令集范围

### 第一阶段：核心指令（必做）

#### 数据处理 — 算术

| 指令 | 说明 |
| --- | --- |
| `ADD`  | 加法，支持立即数与寄存器操作数，可选移位 |
| `ADDS` | 加法并更新标志位 |
| `SUB`  | 减法 |
| `SUBS` | 减法并更新标志位 |
| `MUL`  | 乘法（低 64 位） |
| `SDIV` | 有符号除法 |
| `UDIV` | 无符号除法 |
| `CMP`  | 比较（SUBS 的别名，丢弃结果） |
| `CMN`  | 比较取反（ADDS 的别名，丢弃结果） |
| `NEG`  | 取负（SUB 的别名） |
| `NEGS` | 取负并更新标志位 |

#### 数据处理 — 逻辑与移位

| 指令 | 说明 |
| --- | --- |
| `AND`  | 位与 |
| `ANDS` | 位与并更新标志位 |
| `ORR`  | 位或（MOV 的底层编码） |
| `EOR`  | 位异或 |
| `MOV`  | 寄存器间移动（ORR Xd, XZR, Xm 的别名） |
| `MVN`  | 位取反移动 |
| `LSL`  | 逻辑左移 |
| `LSR`  | 逻辑右移 |
| `ASR`  | 算术右移 |
| `ROR`  | 循环右移 |

#### 数据处理 — 立即数加载

| 指令 | 说明 |
| --- | --- |
| `MOVZ` | 零扩展加载立即数（支持 16 位 + LSL 移位到指定位置） |
| `MOVN` | 取反加载立即数 |
| `MOVK` | 保持其他位不变，加载 16 位到指定位置 |

#### 比较与条件选择

| 指令 | 说明 |
| --- | --- |
| `CSEL`  | 条件选择 |
| `CSET`  | 条件置位（CSEL 的别名） |
| `CSINC` | 条件选择并自增 |
| `CMP`   | 比较（见算术部分） |

#### 控制流

| 指令 | 说明 |
| --- | --- |
| `B`     | 无条件跳转 |
| `BL`    | 带链接跳转（函数调用，X30=返回地址） |
| `BR`    | 跳转到寄存器地址 |
| `BLR`   | 带链接跳转到寄存器地址 |
| `RET`   | 返回（默认跳转 X30） |
| `B.cond`| 条件跳转，cond 覆盖 EQ/NE/CS/CC/MI/PL/VS/VC/HI/LS/GE/LT/GT/LE/AL |

#### Load / Store

| 指令 | 说明 |
| --- | --- |
| `STR`  | 存储（64/32/16/8 位） |
| `LDR`  | 加载（64/32/16/8 位，带符号扩展或零扩展） |
| `STP`  | 成对存储 |
| `LDP`  | 成对加载 |

#### 寻址模式

| 模式 | 语法 | 说明 |
| --- | --- | --- |
| 偏移 | `[Xn, #imm]` | base + offset，不修改 base |
| 前索引 | `[Xn, #imm]!` | base + offset，结果写回 base |
| 后索引 | `[Xn], #imm` | 先访问 base，再 base += imm |
| 寄存器偏移 | `[Xn, Xm]` | base + 寄存器值 |

### 第二阶段：可选扩展（按需）

| 类别 | 内容 |
| --- | --- |
| 浮点基础 | F0–F31 寄存器，FADD/FSUB/FMUL/FDIV（仅 64 位 double） |
| 位域操作 | BFM/UBFM/SBFM、BFI/BFXIL |
| 简单 I/O | 约定内存地址为串口输出（MMIO），写入即打印 |
| 简单系统调用 | SVC 指令 + 约定系统调用号（如 write/print） |

### 不实现（明确排除）

| 类别 | 原因 |
| --- | --- |
| SVE2 / NEON / SIMD | 向量指令集极庞大，需要可变向量长度模拟 |
| PAC（指针认证） | 安全特性，需要密钥与加密算法 |
| MTE（内存标记） | 需要为每个内存粒度维护 tag |
| MMU / 虚拟内存 / TLB / 页表 | 系统级特性，复杂度等于另一个项目 |
| EL0–EL3 特权级 | 需要完整异常向量表与安全状态机 |
| Cache 模拟 | 需要缓存一致性协议 |
| 多核 | 并发一致性、内存屏障，复杂度过高 |
| 完整 ARMv9-A ISA | 数千条指令，不现实 |

## 任务拆分

每个里程碑产出可运行、可测试的增量。

### 里程碑 1：寄存器与内存模型

**目标**：建立 CPU 的核心数据结构。

**文件**：
- `arm_emulator/__init__.py`
- `arm_emulator/registers.py`
- `arm_emulator/memory.py`
- `arm_emulator/tests/test_registers.py`
- `arm_emulator/tests/test_memory.py`

**任务**：
1. `RegisterFile` 类：X0–X30（64 位）、SP、PC，使用 Python int + 64 位掩码截断
2. W 寄存器视图（写 Wn 清高 32 位，读 Wn 返回低 32 位零扩展）
3. `PSTATE` 类：N/Z/C/V 四个布尔标志，提供按 ARM 规范的标志更新方法
4. `Memory` 类：`bytearray` 底层、字节/半字/字/双字读写（小端序）
5. 内存初始化、加载程序到指定地址
6. 测试：寄存器读写截断、W 视图、标志位、内存各宽度读写、边界地址

**完成标准**：
- 寄存器读写自动截断到 64 位，Wn 视图正确
- NZCV 标志位的算术更新逻辑独立可测
- 内存支持 8/16/32/64 位读写，小端序正确

### 里程碑 2：指令定义与位域工具

**目标**：建立指令编码格式的基础设施。

**文件**：
- `arm_emulator/instructions.py`
- `arm_emulator/tests/test_instructions.py`

**任务**：
1. 定义 `Instruction` 数据类：助记符、操作数列表、原始 4 字节编码
2. 定义 `Mnemonic` 枚举（覆盖第一阶段所有指令）
3. bit-field 工具函数：`extract_bits(value, start, width)`、`insert_bits(value, start, width, field_value)`、`sign_extend(value, bits)`
4. 定义各指令类型的编码模板常量（如 ADD 编码的 sf 位、操作码位、寄存器位的位置）
5. 测试：位域提取/拼接/符号扩展正确性

**完成标准**：
- 能正确提取和拼接 AArch64 指令的各个 bit field
- 符号扩展函数覆盖正数与负数

### 里程碑 3：解码器（反汇编器）

**目标**：从 4 字节二进制解析出指令。

**文件**：
- `arm_emulator/decoder.py`
- `arm_emulator/tests/test_decoder.py`

**任务**：
1. 主入口 `decode(word: int) -> Instruction`：按 bit-field 模式匹配指令类型
2. 解码数据处理指令（ADD/ADDS/SUB/SUBS/MUL/SDIV/UDIV/CMP/NEG）
3. 解码逻辑与移位指令（AND/ANDS/ORR/EOR/MOV/MVN/LSL/LSR/ASR/ROR）
4. 解码立即数加载（MOVZ/MOVN/MOVK）
5. 解码条件选择（CSEL/CSET/CSINC）
6. 解码分支（B/BL/BR/BLR/RET/B.cond）
7. 解码 load/store（LDR/STR/LDP/STP + 寻址模式）
8. 未识别指令抛出 `DecodeError` 并提供原始 32 位值
9. 测试：每类指令至少一个已知编码的 round-trip 测试（编码 → 二进制 → 解码 → 验证字段）

**完成标准**：
- 能正确解码第一阶段所有指令类型
- 寻址模式正确识别偏移/前索引/后索引/寄存器偏移
- 条件码正确解析（16 种条件）

### 里程碑 4：汇编器（编码器）

**目标**：从文本汇编生成 4 字节二进制编码。

**文件**：
- `arm_emulator/encoder.py`
- `arm_emulator/tests/test_encoder.py`

**任务**：
1. 词法分析：识别助记符、寄存器名、立即数（十进制/十六进制 `0x`）、标签、分隔符
2. 语法分析：解析操作数（寄存器、立即数、移位修饰、内存操作数 `[Xn, ...]`）
3. 两遍扫描：
   - 第一遍：收集标签地址（每个标签对应当前指令序号 × 4 + 加载基址）
   - 第二遍：生成编码，解析标签引用为偏移量
4. 编码数据处理指令
5. 编码逻辑与移位指令
6. 编码立即数加载（MOVZ/MOVN/MOVK 的 16 位立即数 + LSL 移位）
7. 编码条件选择指令
8. `.skip`、`.word`、`.string` 伪指令（用于数据布局）
9. 测试：每类指令的文本 → 二进制 → 解码 round-trip 验证

**完成标准**：
- 能汇编包含标签、函数调用、循环的完整程序
- `.word` / `.string` 伪指令正确布局数据
- 汇编 + 反汇编 round-trip 一致

### 里程碑 5：执行引擎

**目标**：实现 fetch-decode-execute 循环。

**文件**：
- `arm_emulator/executor.py`
- `arm_emulator/tests/test_executor.py`

**任务**：
1. `Executor` 类：持有 `RegisterFile`、`Memory`，从指定 PC 开始执行
2. fetch：从 PC 读取 4 字节（小端序）
3. decode：调用 decoder
4. execute：按指令类型执行，更新寄存器、内存、标志位
5. ADDS/SUBS/ANDS 的 NZCV 按规范计算（含真实 C 和 V）
6. 分支指令更新 PC，BL/BLR 写 X30，RET 读 X30
7. load/store 执行各寻址模式
8. HALT 指令（伪指令，停止执行）
9. 单步执行（`step()`）与连续运行（`run()`），支持步数上限防死循环
10. 可选执行日志：每步打印 PC、解码后的指令、关键寄存器变化
11. 测试：
    - 算术运算与溢出标志
    - 循环（如 1 加到 100）
    - 函数调用与返回（如阶乘递归）
    - load/store 与数组求和
    - 条件分支（如求最大值）

**完成标准**：
- 能执行完整汇编程序，结果正确
- NZCV 标志位在 ADDS/SUBS 后符合 ARM 规范
- 递归调用不栈溢出（在合理深度内）

### 里程碑 6：CLI 与集成

**目标**：提供命令行工具，串联汇编 → 编码 → 加载 → 执行全流程。

**文件**:
- `arm_emulator/cli.py`
- `arm_emulator/tests/test_cli.py`

**任务**：
1. 子命令 `assemble`：读 `.s` 汇编文件 → 输出二进制（`.bin`）或 hexdump
2. 子命令 `disassemble`：读二进制 → 输出汇编文本
3. 子命令 `run`：读 `.s` 或 `.bin` → 加载到内存 → 执行 → 输出结果
4. `--trace` 选项：逐指令打印执行日志
5. `--dump-regs` 选项：执行结束后打印所有寄存器
6. `--dump-mem <addr> <len>` 选项：打印内存区域
7. `--load-addr <addr>` 选项：指定程序加载地址
8. 测试：CLI 端到端用例（汇编 + 运行 + 验证输出）

**完成标准**：
- `python -m arm_emulator.cli assemble prog.s -o prog.bin` 生成二进制
- `python -m arm_emulator.cli run prog.s --trace` 逐指令执行并打印
- `python -m arm_emulator.cli disassemble prog.bin` 反汇编
- 端到端用例通过

### 里程碑 7：示例程序与文档

**目标**：用完整示例验证模拟器，撰写教学文档。

**文件**：
- `examples/arm/`（新目录）
  - `sum_1_to_100.s`：循环求和
  - `factorial.s`：递归阶乘
  - `array_sum.s`：数组求和
  - `fibonacci.s`：递归或迭代斐波那契
- `docs/arm_emulator_guide.md`：使用指南
- `docs/arm_emulator_design.md`：设计说明（编码格式表、指令对照表、内存布局）

**任务**：
1. 编写示例汇编程序，验证模拟器正确性
2. 编写用户指南：安装、CLI 用法、示例讲解
3. 编写设计文档：指令编码格式、内存模型、标志位计算规则
4. 更新 `README.md` 或 `README_CN.md`，添加 AArch64 模拟器路径说明

**完成标准**：
- 4 个示例程序均能在模拟器上正确运行
- 文档覆盖安装、使用、指令集、编码格式
