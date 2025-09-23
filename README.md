# Haifa Python 编译器与虚拟机

Haifa Python 提供了一个教学友好的编译器与虚拟机实验平台：
从类汇编脚本解析成抽象语法树（AST），再编译为字节码并在虚拟机上运行。
在此基础上，我们扩展出 jq 风格的 JSON 处理运行时，形成“Core VM + jq 工具层”的分层架构。

## 项目亮点
- **完整流水线**：类汇编 → AST → 字节码 → 字节码虚拟机，配套解释器与可视化工具。
- **分层设计**：核心指令集保持精简通用；jq 功能通过独立的 `JQOpcode` 与 `JQVM` 扩展。
- **JSON 友好**：支持对象/数组/字符串/布尔/Null 等值类型，兼容 jq 常用过滤器、排序、聚合与字符串处理。
- **CLI 体验**：`python -m compiler.jq_cli` 提供 jq 风格命令行，覆盖变量、输入模式、输出格式等选项。
- **测试齐备**：`pytest` 覆盖核心指令、jq 解析与运行时、端到端 CLI 等 100+ 用例。

## 目录结构速览
| 路径 | 说明 |
| --- | --- |
| `compiler/parser.py` | 类汇编脚本解析器，生成 AST 节点序列 |
| `compiler/ast_nodes.py` | AST 节点定义，覆盖算术、控制流、函数、数组、位运算等 |
| `compiler/compiler.py` | 将 AST 翻译为仅包含 Core `Opcode` 的字节码 |
| `compiler/bytecode.py` | Core 指令枚举与 `Instruction` 数据结构 |
| `compiler/bytecode_vm.py` | Core 字节码虚拟机，执行通用指令并提供调试状态 |
| `compiler/jq_parser.py` / `compiler/jq_ast.py` | jq 语法解析与 AST 定义 |
| `compiler/jq_compiler.py` | jq AST → `Opcode` + `JQOpcode` 字节码编译器 |
| `compiler/jq_vm.py` | 基于 Core VM 的 jq 虚拟机，注册 jq 专属指令处理器 |
| `compiler/jq_cli.py` | jq 命令行入口，负责参数解析、输入输出管线 |
| `docs/jq_design.md` | jq 功能路线图、指令分层对照表、设计笔记 |
| `vm/` | 早期寄存器/栈 VM 实验实现与测试 |

## 指令分层概览
- **Core Opcode**：由 `Opcode` 枚举定义，负责算术逻辑、跳转、数组、函数调用等通用操作。
- **JQ Opcode**：由 `JQOpcode` 描述 jq 专属语义（对象访问、迭代、聚合、字符串工具等）。
- **执行单元**：`BytecodeVM` 仅实现 Core 指令；`JQVM` 在其基础上扩展 jq 指令处理。
- 详见 `docs/jq_design.md` 的“指令分层对照表”。

## 快速上手
1. 准备 Python 3.11+ 环境（推荐使用虚拟环境）。
2. 安装依赖（本项目仅使用标准库与 `pytest`）。
3. 运行测试验证环境：
   ```bash
   pytest
   ```

### 运行类汇编脚本
- 编写汇编风格脚本，例如：
  ```
  MOV a, 5
  ADD b, a, 3
  PRINT b
  HALT
  ```
- 使用解析器与编译器执行：
  ```python
  from compiler import parser, compiler, bytecode_vm

  program = """\nMOV a, 5\nADD b, a, 3\nPRINT b\nHALT\n"""
  nodes = parser.parse(program)
  bytecode = compiler.ASTCompiler().compile(nodes)
  vm = bytecode_vm.BytecodeVM(bytecode)
  vm.run()
  print(vm.output)  # [8]
  ```

### jq 命令行示例
```bash
# 从 stdin 读取 JSON，输出对象的键
cat data.json | python -m compiler.jq_cli 'keys'

# 使用变量并启用紧凑输出
python -m compiler.jq_cli '.items[] | {name, price}' \
  --argjson items '[{"name": "apple", "price": 12}]' \
  -n -c

# 处理原始文本输入
printf "a\nb\n" | python -m compiler.jq_cli '.' -R -r
```

常用选项：
- `--arg/--argjson` 注入变量，`$var` 与 `expr as $x` 绑定。
- `-n/--null-input`、`-R/--raw-input`、`--slurp` 控制输入模式。
- `-r/--raw-output`、`-c/--compact-output` 控制输出格式。
- `-f/--filter-file` 从文件加载过滤器。

## 安装与分发

### 通过 pip 安装 `pyjq`
项目提供了标准的 `pyproject.toml`，安装后会自动注册 `pyjq` 命令：

```bash
pip install .
pyjq '.foo' --input sample.json
```

安装时会拉取 `compiler` 包，`pyjq` 实际调用 `compiler.jq_cli:main`。

### 构建独立可执行文件
若希望在无 Python 环境的机器上运行，可使用 PyInstaller 打包：

```bash
python -m pip install pyinstaller
pyinstaller --onefile --name pyjq compiler/jq_cli.py
# 生成的二进制位于 dist/pyjq（Windows 下为 dist/pyjq.exe）
```

## CI/CD：PyInstaller 构建流水线
- `.github/workflows/pyjq-build.yml` 定义了跨平台流水线，在推送 `v*` 标签或手动触发时运行。
- 流水线会在 Ubuntu / macOS / Windows 上运行 PyInstaller，产出 `pyjq-linux`、`pyjq-macos`、`pyjq-windows.exe` 三个制品并自动上传为构建产物。
- 可结合 GitHub Releases，将这些制品发布给终端用户。

## 测试与开发
- 单元与集成测试：`pytest`（覆盖 Core 指令、jq 编译/运行、CLI 等场景）。
- 新增指令时请同步更新：
  - `compiler/bytecode.py`（枚举与文档字符串）
  - 对应编译器 / VM 处理逻辑
  - `docs/jq_design.md` 中的指令分层表
- 若需调试执行流程，可使用 `compiler/vm_visualizer.py` 或配套测试中的可视化帮助。

## 相关文档
- `docs/jq_design.md`：阶段性里程碑、设计原则、指令分层对照表。
- `compiler/README.md`（如有）和测试文件中的示例，提供更多 API 使用方式。

欢迎在实验、教学或探索虚拟机与编译器实现时使用与扩展本项目。
