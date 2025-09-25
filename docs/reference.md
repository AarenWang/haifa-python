# jq 过滤器与运行时参考手册

本文档对 Haifa Python jq 运行时支持的主要特性进行汇总，供开发与测试查阅。

## 1. 命令行接口

### 1.1 位置参数
- `filter`：jq 表达式字符串。可省略并使用 `--filter-file` 指定文件。

### 1.2 调用方式
- Python 模块：`python -m compiler.jq_cli <filter> [options]`
- 安装脚本：`pyjq <filter> [options]`
- Lua 子集：`pylua <file.lua>` 或 `pylua --execute '<expr>'`

### 1.3 常用选项

| 选项 | 说明 |
| --- | --- |
| `--filter-file/-f` | 从文件读取过滤器表达式 |
| `--input/-i` | 指定输入 JSON 文件路径 |
| `--slurp` | 将整个 JSON 文档视为一个值 |
| `-R/--raw-input` | 按行读取原始文本字符串 |
| `-n/--null-input` | 使用 `null` 作为唯一输入 |
| `-r/--raw-output` | 输出字符串不加引号 |
| `-c/--compact-output` | 输出紧凑 JSON |
| `--arg name value` | 设置 `$name` 字符串变量 |
| `--argjson name json` | 设置 `$name` JSON 变量 |
| `--visualize [mode]` | 启动 VM 可视化器；`mode` 为 `gui` (默认) 或 `curses` |
| `--debug` | 输出完整堆栈调试信息 |

### 1.4 Lua REPL

- `pylua` 在 TTY 中默认进入交互式 REPL，使用 `pylua --repl` 可在任何环境强制启用。
- 主提示符为 `>`，多行语句时使用 `...` 续行，`=` 前缀会自动补全为 `return`。
- 内置命令：`:help`、`:quit`/`:q`、`:trace none|instructions|coroutine|all`、`:env`。
- `--trace`、`--stack`、`--break-on-error` 选项在 REPL 中同样生效，可结合 `:trace` 动态调整。

## 2. 支持的 jq 语法元素

### 2.1 基础表达式
- `.`：输入值
- `.foo`：对象字段访问
- `.foo.bar`：链式访问
- `.[]`：数组迭代
- `.foo[]`：字段后迭代
- `.foo[0]`、`.foo[-1]`：索引，支持负数
- `.foo[1:3]`、`.foo[:2]`、`.foo[2:]`：切片
- `"str"`、`123`、`true/false/null`：字面量
- `{key: expr, ...}`：对象字面量
- `[expr1, expr2]`：数组字面量

### 2.2 运算符
- 算术：`+`, `-`, `*`, `/`, `%`
- 比较：`==`, `!=`, `<`, `<=`, `>`, `>=`
- 逻辑：`and`, `or`, `not`
- 空值合并：`//`
- 括号分组：`(expr)`

### 2.3 管道
- `expr1 | expr2`：将 expr1 的输出依次作为 expr2 的输入。

### 2.4 变量
- `$var`：访问变量。
- `expr as $var | ...`：绑定变量后续使用。
- CLI 注入变量：`--arg/--argjson`。

## 3. 内建函数与过滤器

| 名称 | 形态 | 说明 |
| --- | --- | --- |
| `length()` | 函数 | 返回输入长度（数组/字符串/对象） |
| `keys()` | 函数 | 对象字段名排序返回，数组返回索引 |
| `has(key)` | 函数 | 检查对象字段/数组索引是否存在 |
| `contains(sub)` | 函数 | 字符串包含、数组包含、对象包含 |
| `add` | 过滤器 | 对数组进行数值求和/字符串拼接 |
| `reverse` | 过滤器 | 数组或字符串反转 |
| `first/last` | 过滤器 | 取数组或字符串首/尾元素 |
| `any/all` | 过滤器 | 判断数组中元素的布尔值 |
| `map(expr)` | 函数 | 对数组元素应用表达式并收集 |
| `select(expr)` | 函数 | 保留满足条件的元素 |
| `flatten()` | 函数 | 展平一层嵌套数组 |
| `reduce(array?, op, init?)` | 函数 | 见下文 |
| `sort()` | 过滤器 | 升序排序 |
| `sort_by(expr)` | 函数 | 按键排序 |
| `unique()` | 过滤器 | 去重保持顺序 |
| `unique_by(expr)` | 函数 | 按键去重 |
| `min/max` | 过滤器 | 取最小/最大值 |
| `min_by(expr)/max_by(expr)` | 函数 | 按键取最小/最大 element |
| `group_by(expr)` | 函数 | 按键分组，输出数组数组 |
| `tostring/tonumber` | 函数 | 类型转换 |
| `split(sep)` | 函数 | 字符串拆分 |
| `gsub(regex; repl)` | 函数 | 正则替换 |
| `join(sep)` | 函数 | 数组字符串 join |

### 3.1 Core 扩展指令

| 指令 | 说明 |
| --- | --- |
| `CLR reg` | 将寄存器 `reg` 置为 0 |
| `CMP_IMM dst src imm` | 对 `src` 与立即数 `imm` 进行比较，结果为 -1/0/1 |
| `JNZ reg label` | 若 `reg` 非零则跳转到 `label` |
| `JMP_REL offset` | 相对跳转，偏移量可为负值 |
| `PUSH src` / `POP dst` | 对 VM 内建数据栈进行压入/弹出 |
| `ARR_COPY dst src start len` | 拷贝 `src[start:start+len]` 至数组 `dst` |
| `IS_OBJ dst src` | 判断 `src` 是否为对象 (`dict`) |
| `IS_ARR dst src` | 判断 `src` 是否为数组 (`list`) |
| `IS_NULL dst src` | 判断 `src` 是否为 `None` |
| `COALESCE dst lhs rhs` | 若 `lhs` 为 `None` 则取 `rhs`，否则保留 `lhs` |
| `MAKE_CELL dst src` | 创建闭包 Cell（用于 upvalue 捕获） |
| `CELL_GET dst cell` | 从 Cell 读取值 |
| `CELL_SET cell src` | 向 Cell 写入值 |
| `CLOSURE dst label cell1 cell2 ...` | 构建闭包对象并捕获 upvalue 列表 |
| `BIND_UPVALUE dst index` | 在函数体内绑定上层传入的 upvalue |
| `CALL_VALUE reg` | 调用存储在寄存器中的闭包/函数值 |
| `VARARG dst` | 将当前函数剩余参数打包成列表写入 `dst` |
| `VARARG_FIRST dst src` | 读取列表 `src` 的首元素（空列表得到 `nil`） |
| `RETURN_MULTI r1 r2 ...` | 返回多个值，列表会被展开 |
| `RESULT_MULTI dst1 dst2 ...` | 将最近一次调用的返回值依次写入目标寄存器（不足补 `nil`） |
| `RESULT_LIST dst` | 将最近一次调用的返回值整体拷贝为列表 |
| `PARAM reg` | 入栈调用参数 |
| `PARAM_EXPAND reg` | 将列表参数展开后逐个入栈 |

### 3.2 `reduce` 语义

```jq
reduce(array_expr; op_string; init?)
```

- `array_expr`：可选，若省略则使用当前输入。
- `op_string`：`sum`, `product`, `min`, `max`, `concat` 等。
- `init`：可选初始值。

示例：
```bash
pyjq 'reduce(.items; "sum")' --input numbers.json
pyjq 'reduce(.items; "concat"; [])' --input arrays.json
```

## 4. 运行时行为

### 4.1 流式执行
- 运行时缓存 bytecode（LRU 128 项），避免重复编译；
- 逐个输入执行，边生成结果边输出；
- 对于失败的输入，会抛出 `JQRuntimeError` 并包含输入编号。

### 4.2 变量寄存器
- CLI 注入的变量映射为寄存器 `__jq_var_<name>`；
- `as` 绑定在字节码层生成 MOV 指令更新寄存器。

## 5. 错误诊断

| 场景 | 表现 | 建议 |
| --- | --- | --- |
| JSON 解析失败 | `Failed to parse JSON input` | 检查输入，或使用 `-R` |
| jq 编译失败 | `Failed to compile jq expression: ...` | 查看语法，必要时 `--debug` |
| jq 运行失败 | `jq execution failed on input #N: ...` | 使用 `--debug` 查看堆栈，定位第 N 个输入 |

## 6. 可视化支持

- `--visualize gui`：调用 `vm_visualizer` 展示字节码执行（需 `pygame`）。
- `--visualize curses`：调用 `vm_visualizer_headless`（基于 `curses`）。
- 默认行为：`--visualize` 等价于 `--visualize gui`，若 GUI 失败会自动回退到 headless。
- GUI 控制：`P` 运行/暂停，`SPACE` 单步，`/` 搜索指令（回车确认、ESC 取消），`L` 导出执行轨迹（JSONL），`R` 重置，`Q` 退出。寄存器面板会高亮最新变更。
- Headless 控制：`SPACE/p` 切换自动执行，`n`/右箭头单步，`r` 重置，`q` 退出。
- GUI 导出的轨迹文件位于当前目录 (`vm_trace_YYYYMMDD_HHMMSS.jsonl`)。

## 7. 测试覆盖概览

| 测试文件 | 关注点 |
| --- | --- |
| `compiler/test_jq_runtime.py` | 运行时流式、缓存、错误包装 |
| `compiler/test_jq_cli.py` | CLI 输入输出、错误处理、`--debug` |
| `compiler/test_jq_core_filters.py` | 核心集合过滤器 |
| `compiler/test_jq_sort_agg.py` | 排序/聚合指令 |
| `compiler/test_jq_string_tools.py` | 字符串相关指令 |

## 8. 兼容性说明

- Python 3.11 测试通过；
- CLI 与 PyInstaller 打包脚本兼容；
- jq 表达式语法覆盖常见子集，但非全面兼容官方 jq。

## 9. 常见陷阱

- `reduce` 的 aggregator 参数必须是字符串字面量；
- `map` 和 `select` 内部表达式仍可使用管道；
- 当输入为空数组，部分聚合返回 `None`（保持 jq 行为一致）。

## 10. 未来扩展

- 更细粒度的错误定位（行列信息）。
- 更多过滤器（`group_by` 聚合扩展、`walk` 等）。
- 流式输入源（生成器、异步 IO）优化。

---

版本：Milestone 6（2025-09-24）
