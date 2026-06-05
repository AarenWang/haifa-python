# Haifa Python

[English](README.md) | 简体中文

Haifa Python 是一个用 Python 编写的、面向教学的编译器、解释器与虚拟机实验平台。它的重点不是把语言实现藏成黑盒，而是让学习者可以直接观察一段代码如何经过词法分析、语法分析、AST、语义分析、字节码生成、虚拟机执行、调试可视化，并进一步 lowering 到更低层的 VM 目标。

当前项目包含四条互相连接的学习路径：

- `pyjq`：jq 风格的 JSON 查询/运行时工具
- `pylua`：Lua 子集，支持字节码编译、表、闭包、协程、trace 与标准库
- `pyscheme`：小型 Scheme 运行时与字节码编译器，支持词法作用域、pair/list/vector、控制形式、闭包与 REPL
- `HaifaArmV9VM`：ARMv9 风格教学 VM，支持固定寄存器、显式栈/堆/全局内存、从 Haifa 字节码 lowering、调试快照与寄存器分配教学报告

## 项目目的

Haifa Python 希望让语言实现变得可读、可运行、可修改、可教学。仓库中的模块尽量保持小而清晰，并配有示例、测试和可视化工具，适合：

- 编译原理与解释器课程
- 编程语言实现自学
- 字节码设计与运行时行为实验
- 闭包、cell/upvalue、表、协程、变长参数、多返回值等语义机制演示
- 对比高级“虚拟寄存器 VM”和更低层的 ARMv9 风格 load/store VM
- 在可复用 VM 基础设施之上实现 jq 风格数据处理

## 当前能力

### 核心 Haifa BytecodeVM

- 基于命名虚拟寄存器的寄存器式字节码 VM
- 函数调用、调用帧、参数、返回、尾调用、变长参数与多返回值
- 闭包、可变 cell、捕获 upvalue 与闭包调用
- Lua 表操作、数组辅助指令、位运算与运行时对象
- 源码/debug 元数据、traceback、协程事件、VM 快照与可视化器支持

### HaifaArmV9VM

`HaifaArmV9VM` 不替换现有 `BytecodeVM`，而是在其旁边新增一个 ARMv9 风格的低层教学目标：

- 固定寄存器：`X0`-`X15`、`SP`、`FP`、`LR`、`PC`、`NZCV`
- 显式内存区：常量池、栈、堆、全局区
- load/store 执行模型，支持 `LDR` / `STR`
- `BL` / `RET` 调用帧与递归函数
- 堆上的 table、cell、closure、多返回值对象
- 通过 `compiler.armv9_lowering` 从 Haifa 高级字节码 lowering
- 可选寄存器缓存优化与 liveness/report 输出：`compiler.armv9_register_alloc`
- 通过 `compiler.vm_debug_adapter` 导出统一调试快照

它不是完整 ARM CPU 模拟器，而是受 AArch64/ARMv9 概念启发的教学 VM。

### jq 运行时

- jq 风格 parser、compiler、VM、runtime 与 CLI
- 支持字段/索引访问、pipe、`map`、`select`、`flatten`、`reduce`、`foreach`、`paths`、`setpath`、`del`、`walk`、`input`、`inputs` 等
- 支持对象字面量与数组字面量
- 当系统 `jq` fallback 不可用时，会包装成项目自己的 `JQRuntimeError`

### Lua 运行时

- Lua lexer/parser/compiler 完整链路
- 局部变量、全局变量、函数、闭包、upvalue、变长参数、多返回值
- 表、字段/索引访问、方法调用、数值/泛型循环、`break`、`repeat`、`do`、`goto`、label
- 协程运行时、协程事件与 trace 输出
- 核心标准库、模块加载、Lua 风格错误与 traceback

### Scheme 运行时

- reader/parser、tree-walking runtime 与字节码编译路径
- 词法作用域、lambda、闭包、递归、`let`/`let*`/`letrec`、named let、`begin`、`set!`、`cond`、`case`、`and`、`or`、`do`
- symbol、pair、list、vector、string、character、boolean、number 等 Scheme 值
- CLI 与 REPL

### 调试与可视化

- 基于 `pygame` 的 GUI 可视化器
- 可用环境下的终端/curses 可视化器
- Windows 无 `_curses` 时，headless visualizer 仍可安全 import 并完成测试 mock
- `BytecodeVM` 与 `HaifaArmV9VM` 共用统一 debug adapter 快照模型
- 静态浏览器 demo：[`docs/lua-vm-demo`](docs/lua-vm-demo/README.md)，同一段 Lua 可在 BytecodeVM 和 ARMv9 两种模式下单步查看

## 项目结构

- `compiler/`：核心字节码 VM、ARMv9 VM、lowering、debug adapter、可视化器、指令定义与兼容 wrapper
- `haifa_jq/`：jq AST、parser、compiler、VM、runtime 与 CLI
- `haifa_lua/`：Lua lexer、parser、compiler、runtime、stdlib、coroutine、module 与 CLI
- `haifa_scheme/`：Scheme reader、runtime、compiler、values、stdlib 与 CLI
- `docs/`：用户文档、VM 参考、里程碑说明与浏览器 demo
- `knowledge/`：深入设计笔记与架构计划
- `examples/`：可运行的 Lua 与 Scheme 示例
- `benchmark/`：基准脚本、运行器与结果
- `vm/`：早期 VM 实验与参考材料

## 快速开始

### 环境要求

- Python 3.11+
- 可选：`pygame`，用于 GUI 可视化器
- 可选：Node.js，用于对浏览器 demo 的 JS 做 `node --check`

### 从源码安装

Unix/macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install .
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install .
```

如需启用 GUI 可视化器：

```bash
python3 -m pip install ".[gui]"
```

### 运行测试

```bash
pytest
```

Windows 开发时建议避免写入 `.pyc`：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest compiler\tests haifa_lua\tests haifa_scheme\tests -q
```

最新迭代后的全量测试状态：

```text
541 passed
```

## 体验各运行时

### Lua

运行脚本：

```bash
python3 -m haifa_lua.cli examples/hello.lua --print-output
```

执行内联代码：

```bash
python3 -m haifa_lua.cli -e 'x = 1; y = 2; return x + y' --print-output
```

启动 REPL：

```bash
python3 -m haifa_lua.cli --repl
```

查看 trace 或可视化执行：

```bash
python3 -m haifa_lua.cli examples/coroutines.lua --trace coroutine
python3 -m haifa_lua.cli examples/coroutines.lua --visualize curses
```

### Scheme

运行脚本：

```bash
python3 -m haifa_scheme.cli examples/factorial.scm --print-output
```

使用 VM backend 并开启 trace：

```bash
python3 -m haifa_scheme.cli examples/factorial.scm --backend vm --trace --print-output
```

执行内联代码：

```bash
python3 -m haifa_scheme.cli -e '(letrec ((fact (lambda (n) (if (= n 0) 1 (* n (fact (- n 1))))))) (fact 5))' --print-output
```

启动 REPL：

```bash
python3 -m haifa_scheme.cli --repl
```

### jq 风格运行时

查询 JSON 文件：

```bash
python3 -m haifa_jq.jq_cli '.items[] | .name' --input compiler/sample.json
```

从标准输入读取 JSON：

```bash
cat compiler/sample.json | python3 -m haifa_jq.jq_cli '.items[] | .price'
```

使用终端可视化器：

```bash
python3 -m haifa_jq.jq_cli '.items[] | .name' --input compiler/sample.json --visualize curses
```

完成安装后，也可以直接使用：

```bash
pylua --help
pyjq --help
pyscheme --help
```

## ARMv9 Lowering 示例

ARMv9 路径目前主要作为 Python API 使用：

```python
from compiler.armv9_lowering import lower_to_armv9
from compiler.armv9_vm import HaifaArmV9VM
from haifa_lua.runtime import compile_source

bytecode = list(compile_source("local t = {a = 42}; return t.a"))
lowered = lower_to_armv9(bytecode)
vm = HaifaArmV9VM(lowered.instructions, const_pool=lowered.const_pool)
vm.run()
print(vm.snapshot()["registers"])
print(lowered.allocation_report.readable_text())
```

使用 `lower_to_armv9(bytecode, optimize_registers=True)` 可以开启教学用寄存器缓存优化，并查看报告。

## 浏览器教学 Demo

直接打开：

```text
docs/lua-vm-demo/index.html
```

这个 demo 不需要本地服务器，可直接在浏览器中打开。它提供两种模式：

- 高级 Haifa BytecodeVM 指令与命名虚拟寄存器
- ARMv9 lowering 后的固定寄存器、栈槽、堆对象、全局区、常量池和 `NZCV`

重新生成 demo 数据：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python docs\lua-vm-demo\export_demo.py
```

## 建议学习路径

如果想按顺序理解项目，可以这样走：

1. 先运行 `examples/` 中的 Lua 示例。
2. 阅读 `haifa_lua/lexer.py`、`haifa_lua/parser.py`、`haifa_lua/compiler.py`。
3. 跟到 `compiler/bytecode.py` 与 `compiler/bytecode_vm.py`，理解高级字节码如何执行。
4. 对照 `haifa_jq/jq_parser.py`、`haifa_jq/jq_compiler.py`、`haifa_jq/jq_vm.py`，看 jq 如何复用 VM 基础设施。
5. 阅读 `haifa_scheme/`，比较 Scheme 的 tree-walking runtime 与 bytecode compiler 路径。
6. 阅读 `compiler/armv9_lowering.py` 与 `compiler/armv9_vm.py`，理解高级 VM 如何 lowering 到 ARMv9 风格执行。
7. 打开浏览器 demo 或 visualizer，观察每一步运行时状态变化。

## 文档索引

- [`docs/lua_guide.md`](docs/lua_guide.md)：Lua 运行时实践指南
- [`docs/scheme_guide.md`](docs/scheme_guide.md)：Scheme 运行时实践指南
- [`docs/guide.md`](docs/guide.md)：jq CLI 使用指南与示例
- [`docs/reference.md`](docs/reference.md)：命令参考
- [`docs/vm_instruction_set.md`](docs/vm_instruction_set.md)：VM 指令集参考
- [`docs/haifa_armv9_vm_plan.md`](docs/haifa_armv9_vm_plan.md)：ARMv9 VM 计划与 phase 拆分
- [`docs/lua-vm-demo/README.md`](docs/lua-vm-demo/README.md)：浏览器教学 demo 说明
- [`docs/lua_sprint.md`](docs/lua_sprint.md)：Lua 实现里程碑
- [`docs/haifa_scheme_sprit.md`](docs/haifa_scheme_sprit.md)：Scheme 实现里程碑
- [`knowledge/03-bytecode-and-vm.md`](knowledge/03-bytecode-and-vm.md)：字节码与 VM 背景
- [`knowledge/06-lua-execution-pipeline.md`](knowledge/06-lua-execution-pipeline.md)：Lua 执行全流程

## 说明

- GUI 可视化器依赖 `pygame`；终端支持 curses 时可使用 `--visualize curses`。
- Lua 实现是有意控制范围的子集/运行时实验，不以完整兼容 Lua 为目标。
- Scheme 实现是教学子集，不以完整 R5RS/R7RS 兼容为目标。
- `HaifaArmV9VM` 是 ARMv9 风格教学目标，不是完整硬件模拟器。
- 项目优先强调可读性、可观测性和可测试迭代，而不是激进性能优化。
