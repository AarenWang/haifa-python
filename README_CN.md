# Haifa Python

[English](README.md) | 简体中文

Haifa Python 是一个用 Python 编写的、面向教学的编译器与虚拟机实验平台。项目基于同一个核心字节码虚拟机，提供两条学习路径：

- 一个 jq 风格的 JSON 查询/运行时工具 `pyjq`
- 一个带运行时、协程与追踪能力的 Lua 子集 `pylua`

这个项目的目标，是让学习者能够直接观察并修改完整执行链路中的每一层：词法分析、语法分析、AST、语义分析、字节码生成、虚拟机执行，以及调试/可视化。

## 项目目的

Haifa Python 希望把“编译器”和“解释器”从黑盒变成可以阅读、实验和教学的代码。仓库中的各层都尽量保持清晰可读，并配有示例、测试和可视化工具，便于课程使用、自学和扩展实验。

这个仓库尤其适合：

- 编译原理与解释器课程
- 编程语言实现的自学与演示
- 字节码设计与运行时行为实验
- 协程、闭包、表、多返回值等语义机制的实践
- 在可复用 VM 核心之上实现 jq 风格的数据处理

## 对应的计算机科学知识

代码结构直接对应多项核心 CS / PL 知识点：

- 词法分析与语法分析
- 抽象语法树与源码映射
- 作用域、闭包与 upvalue 的语义分析
- 字节码指令集设计
- 虚拟机执行模型与寄存器/栈式权衡
- 调用栈、运行时环境与错误报告
- 协程与事件化执行追踪
- CLI 工具、调试视图与执行可视化

如果你在学习或教授编译器、语言运行时、虚拟机，这个仓库既是可运行的软件，也是可研究的教材。

## 项目结构

- `compiler/`：核心字节码 VM、jq 前端/运行时、指令集与可视化器
- `haifa_lua/`：Lua 词法器、解析器、编译器、运行时、标准库、协程与 CLI
- `docs/`：用户文档、里程碑说明与参考资料
- `knowledge/`：架构说明与深入笔记
- `examples/`：可直接运行的 Lua 与协程示例
- `benchmark/`：基准脚本、运行器与结果

## Quick Start

### 环境要求

- Python 3.11+
- 可选：`pygame`，用于 GUI 可视化器

### 从源码安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install .
```

如需启用 GUI 可视化器：

```bash
python3 -m pip install ".[gui]"
```

### 运行测试

```bash
pytest
```

### 体验 Lua 运行时

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

查看追踪或可视化执行：

```bash
python3 -m haifa_lua.cli examples/coroutines.lua --trace coroutine
python3 -m haifa_lua.cli examples/coroutines.lua --visualize curses
```

### 体验 jq 风格运行时

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
```

## 建议学习路径

如果你想按顺序理解这个项目，推荐这样阅读：

1. 先运行 `examples/` 中的一个 Lua 示例。
2. 阅读 `haifa_lua/lexer.py`、`haifa_lua/parser.py` 和 `haifa_lua/compiler.py`。
3. 继续跟到 `compiler/bytecode.py` 与 `compiler/bytecode_vm.py`，看字节码与执行器如何衔接。
4. 再对照 `haifa_jq/jq_parser.py`、`haifa_jq/jq_compiler.py` 和 `haifa_jq/jq_vm.py`，比较 jq 与 Lua 如何复用同一个 VM 核心。
5. 最后结合可视化器或 trace 输出观察运行时状态变化。

## 文档索引

- [`docs/lua_guide.md`](docs/lua_guide.md)：Lua 运行时实践指南
- [`docs/guide.md`](docs/guide.md)：jq CLI 使用指南与示例
- [`docs/reference.md`](docs/reference.md)：命令参考
- [`docs/lua_sprint.md`](docs/lua_sprint.md)：实现里程碑与路线图
- [`knowledge/03-bytecode-and-vm.md`](knowledge/03-bytecode-and-vm.md)：字节码与 VM 背景
- [`knowledge/06-lua-execution-pipeline.md`](knowledge/06-lua-execution-pipeline.md)：Lua 执行全流程

## 说明

- GUI 可视化器依赖 `pygame`。在无图形环境中请使用 `--visualize curses`。
- 当前 Lua 实现是一个有意控制范围的子集/运行时实验，不以完整兼容 Lua 为目标。
- 项目优先强调可读性、可观测性和教学价值，而不是激进的性能优化。
