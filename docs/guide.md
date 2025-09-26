# jq CLI 快速上手指南

本指南帮助你从零开始使用 Haifa Python 的 jq 运行时工具 `pyjq`，完成安装、输入输出管线配置以及常见过滤器示例。

## 1. 安装 `pyjq`

### 使用 pip 安装
```bash
pip install .
# 方式一：直接调用 Python 模块
python -m compiler.jq_cli --help
# 方式二：使用安装后的 pyjq 命令
pyjq --help
```

### 构建平台可执行文件
在项目根目录运行：
```bash
python -m pip install pyinstaller
pyinstaller --onefile --name pyjq compiler/jq_cli.py
```
生成的二进制位于 `dist/pyjq`（Windows 为 `dist/pyjq.exe`）。

## 2. 基本命令结构
```bash
# 直接运行 Python 模块
python -m compiler.jq_cli '<filter>' [--input FILE] [options]

# 使用 pyjq 命令
pyjq '<filter>' [--input FILE] [options]
```

- `<filter>`：jq 表达式字符串；或使用 `--filter-file` 指向脚本文件。
- 默认读取 `stdin`，也可通过 `--input` 指定 JSON 文件。
- 输出结果为按行分隔的 JSON 值，可使用 `--raw-output` 等选项调整格式。

## 3. 输入模式

| 选项 | 说明 |
| --- | --- |
| `--input PATH` | 从文件读取 JSON，而不是 stdin |
| `-n/--null-input` | 忽略输入，使用 `null` 作为唯一数据 |
| `-R/--raw-input` | 将每一行原始文本视为字符串输入 |
| `--slurp` | 将整个 JSON 文档作为单个值传入（数组不会拆分） |

## 4. 输出控制

| 选项 | 说明 |
| --- | --- |
| `-r/--raw-output` | 字符串结果不再输出引号 |
| `-c/--compact-output` | 紧凑 JSON（无空格） |
| `--debug` | 发生错误时输出完整堆栈，便于排查 |

## 5. 常用过滤器示例

### 5.1 访问字段与管道
```bash
python -m compiler.jq_cli '.user.name' --input user.json
pyjq '.items[] | .price' --input orders.json
```

示例 `user.json`：
```json
{
  "user": {
    "name": "Alice",
    "email": "alice@example.com"
  }
}
```

### 5.2 变量与绑定
```bash
python -m compiler.jq_cli '$foo | .value' -n --argjson foo '{"value": 42}'
pyjq '.[] | (.|keys) as $k | {name: .name, keys: $k}' --input data.json
```

### 5.3 数组与集合操作
```bash
# map/select
python -m compiler.jq_cli '.items | map(.score)' --input scores.json
pyjq '.[] | select(.active)' --input users.json

# slice/index
python -m compiler.jq_cli '.items[0:3]' --input data.json

# 排序与唯一
pyjq '.items | sort_by(.age)' --input people.json
python -m compiler.jq_cli '.items | unique_by(.id)' --input people.json
```

### 5.4 聚合与 reduce
```bash
python -m compiler.jq_cli 'reduce .values[] as $n (0; . + $n)' --input numbers.json
pyjq 'reduce(.items, "product")' --input numbers.json
pyjq 'foreach .values[] as $n (0; . + $n; .)' --input numbers.json
```

### 5.5 字符串处理
```bash
python -m compiler.jq_cli '.message | tostring' --input payload.json
pyjq '.items | join(", ")' --input list.json
```

### 5.6 更新与循环组合子
```bash
python -m compiler.jq_cli '.counter += 1' --input counter.json
pyjq 'while(. < 100; . * 2)' --input numbers.json
pyjq 'until(. > 10; . + 3)' --input numbers.json
```

## 6. 类汇编脚本与可视化

### 6.1 基础类汇编执行
```python
from compiler import parser, compiler, bytecode_vm

program = """\nMOV a, 5\nADD b, a, 3\nPRINT b\nHALT\n"""
nodes = parser.parse(program)
bytecode = compiler.ASTCompiler().compile(nodes)
vm = bytecode_vm.BytecodeVM(bytecode)
vm.run()
print(vm.output)  # [8]
```

### 6.2 查看调用栈的汇编示例
```python
from compiler.parser import parse
from compiler.compiler import ASTCompiler
from compiler.bytecode_vm import BytecodeVM
from compiler.vm_visualizer import VMVisualizer

script = [
    "FUNC max2",
    "ARG a",
    "ARG b",
    "GT cond a b",
    "IF cond",
    "RETURN a",
    "ELSE",
    "RETURN b",
    "ENDIF",
    "ENDFUNC",
    "ARR_INIT arr 5",
    "ARR_SET arr 0 5",
    "ARR_SET arr 1 12",
    "ARR_SET arr 2 7",
    "ARR_SET arr 3 3",
    "ARR_SET arr 4 9",
    "MOV i 0",
    "MOV len 5",
    "ARR_GET max arr 0",
    "LABEL loop",
    "LT cond i len",
    "JZ cond end",
    "ARR_GET val arr i",
    "PARAM max",
    "PARAM val",
    "CALL max2",
    "RESULT max",
    "ADD i i 1",
    "JMP loop",
    "LABEL end",
    "PRINT max"
]

bytecode = ASTCompiler().compile(parse(script))
vm = BytecodeVM(bytecode)
VMVisualizer(vm).run()
```

### 6.3 可视化器面板与快捷键
GUI 版可视化器拆分为三个区域：

- **左侧指令区**：展示指令列表，可通过 `/` 搜索并定位到当前 PC。
- **中部状态区**：包含全局寄存器、选中协程的寄存器/Upvalue/调用栈，以及 Emit Stack、Output 等调试信息。
- **右侧协程与时间线区**：上方列出当前协程列表，下方时间线会记录 `create/resume/yield/complete` 事件，并在最底部展示事件详情。

常用快捷键：

- `P` 运行/暂停自动执行。
- `SPACE` 单步执行。
- `↑` / `↓` 切换选中的协程，面板随之刷新寄存器与栈信息。
- `←` / `→` 在时间线中切换事件，右侧详情会显示参数与 PC。
- `F` 开关“自动跟随当前协程”，开启后 `resume` 会自动选中对应协程。
- `/` 进入指令搜索（回车确认、ESC 取消）。
- `L` 导出执行轨迹（JSONL），`R` 重置虚拟机，`Q` 退出。

GUI 会高亮最近变更的寄存器，时间线还会对当前选中的协程事件进行浅色标记。导出的轨迹文件位于当前目录，命名为 `vm_trace_YYYYMMDD_HHMMSS.jsonl`。

## 7. 可视化执行流程
使用 `--visualize` 结合内建 VM 可视化器，查看字节码执行：
```bash
python -m compiler.jq_cli '.items[] | .name' --input data.json --visualize
pyjq '.items[] | .name' --input data.json --visualize
# 强制使用 headless 模式
python -m compiler.jq_cli '.items[] | .name' --input data.json --visualize curses
```
GUI 版可视化依赖 `pygame`，需要提前安装：
```bash
python -m pip install pygame
```
若无法使用图形界面，CLI 会自动尝试导入 `vm_visualizer_headless`，以控制台形式输出执行轨迹。

Headless 模式基于 `curses` 渲染，常用按键：
- `SPACE` / `p`：开始/暂停自动执行
- `n` / 右方向键：单步执行
- `r`：重置并回到初始状态
- `e`：切换协程事件列表的显示/隐藏（右栏仍会保留最近一条事件详情）
- `q`：退出
- Headless 会同步展示当前协程寄存器、Upvalue 与最近事件详情；如需导出轨迹，可在 GUI 模式运行后使用 `L` 键生成文件。

### 6.4 协程事件示例

仓库新增示例脚本 `examples/coroutines.lua`，模拟两个协程交替 `yield` 的过程，可直接加载到可视化器中：

```python
from pathlib import Path

from compiler.bytecode_vm import BytecodeVM
from compiler.vm_visualizer import VMVisualizer
from haifa_lua.runtime import compile_source

source = Path("examples/coroutines.lua").read_text(encoding="utf-8")
instructions = list(compile_source(source, source_name="coroutines.lua"))
vm = BytecodeVM(instructions)
VMVisualizer(vm).run()
```

若处于终端环境，可用 `pylua` 的 `--trace coroutine` 选项打印同样的事件序列：

```bash
python -m haifa_lua.cli examples/coroutines.lua --trace coroutine
```

## 8. 常见问题

### 8.1 运行时报 “Failed to parse JSON input”
确认输入文件/stdin 是合法 JSON；如需处理文本，请加 `-R`。

### 8.2 运行时抛出 “jq execution failed”
说明过滤器在某个输入上出错。建议：
1. 使用 `--debug` 获取堆栈和输入编号；
2. 检查该输入数据结构，确认字段存在且类型符合预期。

### 8.3 大量数据内存占用高
`pyjq` 默认流式输出，不会整体缓存。若仍担心内存，可串联 `head`、`> file` 等命令行工具控制输出。

## 9. 后续阅读
- `docs/reference.md`：详尽的指令/过滤器手册。
- `docs/jq_design.md`：架构背景、里程碑记录与未来计划。
- `docs/lua_sprint.md`：Lua 解释器规划与迭代任务。

## 10. Lua 子集快速体验（Milestone 1）
- CLI：`pylua your_script.lua` 或 `pylua --execute 'return 1+2'`。
- 当前支持：赋值、算术表达式、`if/else`、`while`、函数定义与调用、闭包（Milestone 2A）、`return`。
- 示例脚本：`examples/hello.lua`。
- 后续里程碑将逐步加入闭包、标准库、协程等特性。

### 闭包示例
```lua
function make_counter()
    local x = 0
    return function()
        x = x + 1
        return x
    end
end

local c1 = make_counter()
local c2 = make_counter()
local a = c1()
local b = c1()
local c = c2()
return a, b, c -- 输出 1, 2, 1
```
运行：`pylua --execute '<上述代码>' --print-output`

### 多返回值 / 可变参数
```lua
function pair()
    return 1, 2
end

function pass_through(...)
    return ...
end

return pair(), pass_through("a", "b")
-- 输出 [1, 2, "a", "b"]
```
