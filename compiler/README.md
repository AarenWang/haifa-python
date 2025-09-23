# ✅ 项目概况：类汇编语言解释执行引擎
该项目实现了一个完整的类汇编语言执行系统，包括：
1. 脚本语言设计（汇编风格）
2. 抽象语法树（AST）构建
3. 字节码编译器
4. 字节码虚拟机执行器
5. 控制结构/函数/数组支持
6. 调试与可视化工具

最终形成一个图灵完备、模块清晰、可拓展的编程语言核心运行时系统。

# ✅ 支持的语言特性（指令集）
## 运算与赋值：
MOV, ADD, SUB, MUL, DIV, MOD, NEG

## 逻辑比较：
EQ, GT, LT, AND, OR, NOT

## 位操作：
AND_BIT, OR_BIT, XOR, NOT_BIT, SHL, SHR, SAR

## 跳转与控制流：
JMP, JZ, LABEL

## 结构化语法糖：
IF, ELSE, ENDIF，WHILE, ENDWHILE, BREAK

## 数组与集合操作：
ARR_INIT, ARR_SET, ARR_GET, LEN, GET_INDEX, LEN_VALUE

## 函数调用与参数传递：
FUNC, CALL, RETURN, PARAM, ARG, RESULT, ENDFUNC

## 多结果流：
PUSH_EMIT, POP_EMIT, EMIT

## 输出与终止：
PRINT, HALT

# ✅ jq 表达式（新增 - 里程碑1）
- 语法与优先级：`+ - * / %`、`== != > >= < <=`、`and or not`、`//`（coalesce）、括号分组
- 说明：`!=`/`>=`/`<=` 通过现有比较与逻辑指令组合实现；`//` 为空值合并（左值非 null 则取左，否则取右）
- 注意：虚拟机 `DIV` 仍为整除，保持与现有 VM 测试一致

# ✅ Python 模块结构与职责

| 文件名	| 作用                   |
| ---	|----------------------| 
|parser.py	| 将类汇编脚本解析为 AST        |
|ast_nodes.py	| 定义 AST 节点类（含控制流、函数、数组、位运算等） |
|executor.py	| 解释执行 AST             |
|bytecode.py	| 定义字节码指令集与 Instruction 结构 |
|compiler.py	| 将 AST 编译为字节码列表       |
|bytecode_vm.py	| 解释执行字节码指令，支持 JSON / jq 多结果流 |
|bytecode_io.py	| .bcode 文件读写工具，支持反汇编  |
|jq_ast.py / jq_parser.py	| jq 过滤器抽象语法及递归下降解析 |
|jq_compiler.py	| jq AST → bytecode 编译器 |
|jq_runtime.py	| jq 运行时封装，管理寄存器输入/输出 |
|jq_cli.py	| `haifa jq` 命令行入口 |
|ast_visualizer.py	| 使用 Graphviz 可视化 AST 结构 |
|test_*.py	| 单元测试和 end-to-end 测试脚本|


# ✅ 核心类汇总
- ASTNode 及其子类（如 AddNode, IfNode, CallNode, …）
- Instruction(opcode, args)：字节码结构
- Opcode(Enum)：虚拟机支持的操作码集合
- ASTCompiler：AST → 字节码编译器
- BytecodeVM：虚拟机解释器
- BytecodeWriter, BytecodeReader：持久化字节码
- ASTVisualizer：AST 可视化工具
- Context, ExecutionContext：VM 状态管理容器

# ✅ 涉及的计算机科学知识点
## 语言与编译器领域：
- 词法/语法解析（Parser）
- 抽象语法树（AST）
- 中间代码表示（Bytecode）
- 栈/寄存器虚拟机设计
- 语法糖转换（结构化控制语句）

## 程序结构与控制流：
- 条件语句与跳转控制
- 函数调用、参数传递、返回值管理
- 标签定位与跳转表构建

## 操作系统与硬件抽象：
- 模拟寄存器行为
- 支持栈帧与调用栈
- 位操作、移位运算与补码处理

## 软件工程与可维护性：
- 多模块 Python 架构
- 可扩展的指令系统（OPCODE）
- 单元测试、可视化、调试接口

# ✅ 项目亮点与可扩展性
已实现亮点：
- 类汇编 → AST → Bytecode → 虚拟机执行的完整流水线
- 支持结构控制语法（如 WHILE 和 IF）
- 支持数组结构与函数递归
- AST 与字节码可视化/调试
- 支持字节码保存和反汇编
- jq 表达式解析/编译/执行，内置 `map`, `select`, `flatten`, `reduce`, `length` 等常用过滤器
- 提供 `haifa jq` CLI，可读取 stdin 或文件并输出 JSON 行

可扩展方向：
- 支持浮点类型（f32, f64）
- 栈式虚拟机 / LLVM IR 输出
- 语法高亮编辑器或 REPL
- 图形化调试器（字节码逐步执行）
- WebAssembly 或 JIT 编译后端

# ✅ 使用方式
## 运行 jq CLI（变量与输出增强）
```bash
cd compiler
python -m jq_cli ".items[] | select(.active) | {name: .name, total: reduce(.scores, 'sum')}" --input data.json
```

支持的增强功能：
- 变量与绑定：
  - `$var` 变量引用，`expr as $x | ...` 将 expr 绑定到 `$x` 后继续原管道。
  - CLI 注入：`--arg name value`（字符串），`--argjson name json`（JSON）。
- 输入模式：`--slurp`（整文作为单值）、`-n/--null-input`（null 作为输入）、`-R/--raw-input`（按行读取原始文本为字符串）。
- 输出格式：`-r/--raw-output` 对字符串直接输出（不加引号），`-c/--compact-output` 紧凑 JSON。
- 过滤器文件：`-f/--filter-file` 从文件读取过滤器表达式。

示例：
```bash
# 变量注入并使用
python -m jq_cli '$foo | .x' -n --argjson foo '{"x": 42}'

# 原始输入 & 原始输出
printf "a\nb\n" | python -m jq_cli '.' -R -r

# 使用过滤器文件与紧凑输出
python -m jq_cli -f filter.jq --input data.json -c
```

## 运行测试
```bash
cd compiler
python -m unittest
```

调试主虚拟机时，可按需启用 `BytecodeVM.run(debug=True)` 查看寄存器与输出变化。
