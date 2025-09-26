# Haifa VM 指令集参考手册

本手册整理了项目中三个主要虚拟机（核心 BytecodeVM、教学用 RegisterVM、教学用 StackVM）的指令集。文档结构参照 Intel® 64/IA-32 与 Arm® Architecture Reference Manual 的组织方式，按照“助记符 / 操作数 / 语义 / 说明”四列给出每条指令的精确含义，便于检索和对照实现。

## 1. 阅读约定

- **助记符（Mnemonic）**：指令名称，全部使用大写。
- **操作数（Operands）**：按出现顺序列出寄存器、常量、标签或其它操作数类型。若包含可选部分以括号表示。
- **语义（Operation）**：以伪代码描述执行效果，必要时展示栈效果或寄存器赋值形式。
- **说明（Notes）**：补充 Lua 语义、变长返回、异常情况或与 CPU 指令集风格的对照信息。

## 2. BytecodeVM 核心指令集

> 对应实现：`compiler/bytecode_vm.py` 中的 `BytecodeVM`。所有算术、比较、位运算都会尝试触发 Lua 元方法（如 `__add`、`__lt`），若未命中则回退到原生操作。

### 2.1 数据传送与常量加载

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `LOAD_IMM` | `dst, imm` | `R[dst] ← int(imm)` | 解析整数字面量；用于快速加载立即数。 |
| `MOV` | `dst, src` | `R[dst] ← value(src)` | `src` 可为寄存器或立即数；内部使用 `resolve_value`。 |
| `LOAD_CONST` | `dst, const` | `R[dst] ← deepcopy(const)` | 支持列表 / 字典常量，保证每次加载互不影响。 |
| `CLR` | `dst` | `R[dst] ← 0` | 清零目标寄存器。 |
| `CMP_IMM` | `dst, src, imm` | `R[dst] ← sign(value(src) - imm)` | 结果为 `-1/0/1`；`imm` 可为立即数或寄存器名。 |

### 2.2 算术运算

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `ADD` / `SUB` / `MUL` | `dst, lhs, rhs` | `R[dst] ← value(lhs) ±/* value(rhs)` | 首先尝试 `__add`/`__sub`/`__mul` 元方法。 |
| `DIV` | `dst, lhs, rhs` | 若均为整数则整除，否则执行浮点除法 | 匹配 `__div` 元方法；整型输入使用“地板”除法。 |
| `MOD` | `dst, lhs, rhs` | `R[dst] ← value(lhs) % value(rhs)` | 支持 `__mod` 元方法。 |
| `POW` | `dst, lhs, rhs` | `R[dst] ← value(lhs) ** value(rhs)` | 幂运算，兼容 `__pow`。 |
| `IDIV` | `dst, lhs, rhs` | `R[dst] ← floor(value(lhs) / value(rhs))` | 对应 Lua `//` 语义；支持 `__idiv`。 |
| `NEG` | `dst, src` | `R[dst] ← -value(src)` | 支持 `__unm` 元方法。 |
| `CONCAT` | `dst, lhs, rhs` | `R[dst] ← tostring(lhs) .. tostring(rhs)` | 数字、布尔、`nil` 会转换为 Lua 兼容字符串。 |

### 2.3 比较与逻辑

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `EQ` | `dst, lhs, rhs` | `R[dst] ← bool(lhs == rhs)` | 若存在 `__eq` 元方法，使用其结果。 |
| `GT` / `LT` | `dst, lhs, rhs` | `R[dst] ← bool(lhs >/< rhs)` | 通过 `__lt` 互换比较以匹配 Lua 行为。 |
| `AND` / `OR` | `dst, lhs, rhs` | `R[dst] ← bool(lhs) &&/|| bool(rhs)` | 结果为布尔值。 |
| `NOT` | `dst, src` | `R[dst] ← !bool(src)` | 一元逻辑取反。 |

### 2.4 位运算

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `AND_BIT` / `OR_BIT` / `XOR` | `dst, lhs, rhs` | `R[dst] ← int(lhs) &/|/^ int(rhs)` | 支持 `__band`、`__bor`、`__bxor` 元方法。 |
| `NOT_BIT` | `dst, src` | `R[dst] ← ~int(src)` | 支持 `__bnot`。 |
| `SHL` | `dst, lhs, rhs` | `R[dst] ← int(lhs) << int(rhs)` | 左移；支持 `__shl`。 |
| `SHR` | `dst, lhs, rhs` | `R[dst] ← (int(lhs) mod 2^32) >> int(rhs)` | 逻辑右移，兼容 `__shr`。 |
| `SAR` | `dst, lhs, rhs` | `R[dst] ← int(lhs) >> int(rhs)` | 算术右移；同样复用 `__shr` 元方法。 |

### 2.5 控制转移

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `JMP` | `label` | `PC ← label` | 绝对跳转。 |
| `JZ` | `cond, label` | `if !bool(cond): PC ← label` | 条件为假跳转。 |
| `JNZ` | `cond, label` | `if bool(cond): PC ← label` | 条件为真跳转。 |
| `JMP_REL` | `offset` | `PC ← PC + offset` | 相对跳转，常用于循环。 |
| `LABEL` | `name` | 无操作 | 占位，供跳转与闭包索引使用。 |

### 2.6 函数调用与协程互操作

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `PARAM` | `src` | `pending_params.push(value(src))` | 准备调用参数。 |
| `PARAM_EXPAND` | `src` | 将列表/多返回值扩展入参数队列 | 支持 Lua `f(table.unpack(x))` 形式。 |
| `CALL` | `label` | 调用静态标签 | 复制寄存器帧，跳入函数入口。 |
| `CALL_VALUE` | `callee` | 调用寄存器中的值 | 支持闭包、内建函数、`__call` 元方法；可能触发协程 `yield`。 |
| `ARG` | `dst` | `R[dst] ← param_stack.pop_front()` | 函数体读取参数。 |
| `RETURN` | `(src)` | 以单值返回 | 留空表示 `nil`。 |
| `RETURN_MULTI` | `src1, src2, ...` | 按序收集所有返回值 | 列表会被展开。 |
| `RESULT` | `dst` | `R[dst] ← last_return[0]` | 获取最近一次返回的首个值。 |
| `RESULT_MULTI` | `dst1, dst2, ...` | 将多返回值写入目标寄存器 | 缺失位置填 `nil`。 |
| `RESULT_LIST` | `dst` | `R[dst] ← list(last_return)` | 捕获全部返回值。 |
| `VARARG` | `dst` | `R[dst] ← list(param_stack)` | 用于 Lua 变长参数。 |
| `VARARG_FIRST` | `dst, src` | `R[dst] ← first(value(src)) or nil` | 取列表首元素。 |
| `BIND_UPVALUE` | `dst, index` | `R[dst] ← current_upvalues[index]` | 将外部闭包捕获的 `Cell` 绑定到局部寄存器。 |

### 2.7 闭包与 Upvalue 管理

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `MAKE_CELL` | `dst, src` | `R[dst] ← Cell(value(src))` | 为 upvalue 创建可变封装。 |
| `CELL_GET` | `dst, cell` | `R[dst] ← cell.value` | 若目标非 `Cell` 会抛出运行时错误。 |
| `CELL_SET` | `cell, src` | `cell.value ← value(src)` | 更新 upvalue 内容。 |
| `CLOSURE` | `dst, label, cell1...` | 构造闭包对象 | 保存目标函数标签与捕获的 `Cell` 列表。 |

### 2.8 容器与数组操作

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `PUSH` | `src` | `stack.push(value(src))` | 辅助数据栈。 |
| `POP` | `dst` | `R[dst] ← stack.pop() or nil` | 栈空时返回 `nil`。 |
| `ARR_INIT` | `name, size` | `Array[name] ← [0] * size` | 分配固定长度数组。 |
| `ARR_SET` | `name, index, src` | `Array[name][index] ← value(src)` | 越界写将被忽略。 |
| `ARR_GET` | `dst, name, index` | `R[dst] ← Array[name][index] or nil` | 越界读取返回 `nil`。 |
| `ARR_COPY` | `dst, src, start, length` | `Array[dst] ← Array[src][start:start+length]` | 长度为负时得到空数组。 |
| `LEN` | `dst, src` | `R[dst] ← len(value(src))` | 支持元方法 `__len`、Lua 表、数组、字符串。 |
| `TABLE_NEW` | `dst` | `R[dst] ← LuaTable()` | 需要 Lua 表支持。 |
| `TABLE_SET` | `table, key, value` | `table[key] ← value`（考虑 `__newindex`） | 若已有键直接写入，否则尝试元方法。 |
| `TABLE_GET` | `dst, table, key` | 查找键，若缺失走 `__index` 链 | 结果写入 `R[dst]`。 |
| `TABLE_APPEND` | `table, value` | `table.append(value)` | 对应 Lua 序列追加。 |
| `TABLE_EXTEND` | `table, values` | `table.extend(coerce(values))` | 支持多返回值拼接。 |
| `LIST_GET` | `dst, src, index` | `R[dst] ← value(src)[index] or nil` | 主要用于处理多返回值列表。 |

### 2.9 类型检测与空合并

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `IS_OBJ` | `dst, src` | `R[dst] ← int(isinstance(value(src), dict))` | 判断是否为 Python 字典。 |
| `IS_ARR` | `dst, src` | `R[dst] ← int(isinstance(value(src), list))` | 判断是否为 Python 列表。 |
| `IS_NULL` | `dst, src` | `R[dst] ← int(value(src) is None)` | `nil` 检测。 |
| `COALESCE` | `dst, lhs, rhs` | `R[dst] ← lhs if lhs is not None else rhs` | 类似 SQL `COALESCE`。 |

### 2.10 输出与终止

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `PRINT` | `src` | `output.append(value(src))` | 将值写入 VM 输出缓冲。 |
| `HALT` | — | 终止执行循环 | 置 VM 状态为 `halt`。 |

### 2.11 结构化伪指令

`STRUCT_IF`、`STRUCT_ELSE`、`STRUCT_ENDIF`、`STRUCT_WHILE`、`STRUCT_ENDWHILE`、`STRUCT_BREAK` 仅用于可视化和调试（例如 AST/字节码渲染），不会进入核心执行循环。

## 3. RegisterVM（v2）指令集

> 对应实现：`vm/register_vm_v2.py:RegisterVMFinalSafe`。使用显式寄存器、标签和函数调用栈，主要用于教学演示。

### 3.1 数据与算术

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `MOV` | `dst, src` | `R[dst] ← value(src)` | 立即数或寄存器。 |
| `ADD/SUB/MUL/DIV/MOD` | `dst, lhs, rhs` | 常规二元算术 | `DIV` 为整除，`MOD` 对零安全（返回 0）。 |
| `NEG` | `dst, src` | `R[dst] ← -value(src)` | |

### 3.2 比较与逻辑

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `EQ/GT/LT` | `dst, lhs, rhs` | 比较后写入 `0/1` | 布尔结果以 `0/1` 表示。 |
| `AND/OR` | `dst, lhs, rhs` | 逻辑与/或 | 基于 Python 真值。 |
| `NOT` | `dst, src` | `R[dst] ← int(not bool(src))` | |

### 3.3 数组

| 指令 | 操作数 | 语义 |
| --- | --- | --- |
| `ARR_INIT name size` | 初始化长度为 `size` 的整型数组 |
| `ARR_SET name index value` | 写入数组元素 |
| `ARR_GET dst name index` | 读取数组元素到寄存器 |
| `LEN dst name` | 获取数组长度 |

### 3.4 流程控制

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `LABEL name` | — | 定义跳转位置 | |
| `JMP label` | — | 无条件跳转 | |
| `JZ cond label` | — | 条件为零时跳转 | |
| `IF cond` ... `ELSE` ... `ENDIF` | — | 结构化分支 | 通过匹配关键字定位。 |
| `WHILE cond` ... `ENDWHILE` | — | 条件循环 | `BREAK` 可提前退出。 |

### 3.5 函数与参数

| 指令 | 操作数 | 语义 | 说明 |
| --- | --- | --- | --- |
| `FUNC name` / `ENDFUNC` | — | 函数定义块 | 主程序执行时会跳过函数体。 |
| `CALL name` | — | 调用函数 | 保存返回地址与参数栈。 |
| `PARAM src` | — | 压入调用参数 | 按顺序排入。 |
| `ARG dst` | — | 读取形参 | 若不足则得 `0`。 |
| `RETURN src` | — | 设置返回值 | |
| `RESULT dst` | — | 复制返回值到寄存器 | |

### 3.6 输入输出

| 指令 | 操作数 | 语义 |
| --- | --- | --- |
| `PRINT reg` | 将寄存器值写入输出列表 |
| `DUMP` | 输出寄存器与数组快照 |

## 4. StackVM 指令集

> 对应实现：`vm/stack_vm.py:StackVM`。所有操作以数据栈为核心，适合演示基于栈的汇编风格。

### 4.1 栈与算术操作

| 指令 | 语义 | 栈效果 |
| --- | --- | --- |
| `PUSH imm` | 将立即数压栈 | `… → …, imm` |
| `ADD/SUB/MUL/DIV/MOD` | 弹出两个操作数，执行算术，再压回 | `…, a, b → …, a±/*b`；`DIV` 取整。 |
| `NEG` | 对栈顶取负 | `…, a → …, -a` |
| `EQ/GT/LT` | 比较两个栈顶元素 | 结果为 `0/1` 压栈。 |
| `AND/OR` | 逻辑运算 | 对弹出的布尔值求与/或。 |
| `NOT` | 逻辑非 | 单操作数。 |

### 4.2 栈管理

| 指令 | 语义 |
| --- | --- |
| `DUP` | 复制栈顶元素。 |
| `DROP` | 弹出栈顶。 |
| `SWAP` | 交换顶部两个元素。 |
| `OVER` | 复制次栈顶到栈顶。 |
| `ROT` | 将第三个元素旋转到栈顶 (`a b c → b c a`)。 |

### 4.3 输出与调试

| 指令 | 语义 |
| --- | --- |
| `PRINT` | 弹出栈顶并写入输出。 |
| `DUMP` | 将当前栈快照写入输出（不修改栈）。 |

### 4.4 分支结构

| 指令 | 语义 |
| --- | --- |
| `IF` | 弹出条件，若为零跳转到匹配的 `ELSE/ENDIF`。 |
| `ELSE` | 跳转到对应的 `ENDIF`。 |
| `ENDIF` | 结构结尾，无操作。 |

## 5. 参考资料

- Intel® 64 and IA-32 Architectures Software Developer’s Manual, Volume 2（指令参考）
- Arm® Architecture Reference Manual Armv8（A-profile）
- 项目源码：`compiler/bytecode.py`, `compiler/bytecode_vm.py`, `vm/register_vm_v2.py`, `vm/stack_vm.py`
