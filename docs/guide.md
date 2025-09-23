# jq CLI 快速上手指南

本指南帮助你从零开始使用 Haifa Python 的 jq 运行时工具 `pyjq`，完成安装、输入输出管线配置以及常见过滤器示例。

## 1. 安装 `pyjq`

### 使用 pip 安装
```bash
pip install .
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
pyjq '.user.name' --input user.json
pyjq '.items[] | .price' --input orders.json
```

### 5.2 变量与绑定
```bash
pyjq '$foo | .value' -n --argjson foo '{"value": 42}'
pyjq '.[] | (.|keys) as $k | {name: .name, keys: $k}' --input data.json
```

### 5.3 数组与集合操作
```bash
# map/select
pyjq '.items | map(.score)' --input scores.json
pyjq '.[] | select(.active)' --input users.json

# slice/index
pyjq '.items[0:3]' --input data.json

# 排序与唯一
pyjq '.items | sort_by(.age)' --input people.json
pyjq '.items | unique_by(.id)' --input people.json
```

### 5.4 聚合与 reduce
```bash
pyjq '.values | reduce("sum")' --input numbers.json
pyjq 'reduce(.items, "product")' --input numbers.json
```

### 5.5 字符串处理
```bash
pyjq '.message | tostring' --input payload.json
pyjq '.items | join(", ")' --input list.json
```

## 6. 可视化执行流程

使用 `--visualize` 结合内建 VM 可视化器，查看字节码执行：
```bash
pyjq '.items[] | .name' --input data.json --visualize
```
如果 GUI 环境受限，CLI 会尝试回退到 headless 可视化器，需要确保 SDL/headless 依赖已安装。

## 7. 常见问题

### 7.1 运行时报 “Failed to parse JSON input”
确认输入文件/stdin 是合法 JSON；如需处理文本，请加 `-R`。

### 7.2 运行时抛出 “jq execution failed”
说明过滤器在某个输入上出错。建议：
1. 使用 `--debug` 获取堆栈和输入编号；
2. 检查该输入数据结构，确认字段存在且类型符合预期。

### 7.3 大量数据内存占用高
`pyjq` 默认流式输出，不会整体缓存。若仍担心内存，可串联 `head`、`> file` 等命令行工具控制输出。

## 8. 后续阅读
- `docs/reference.md`：详尽的指令/过滤器手册。
- `docs/jq_design.md`：架构背景、里程碑记录与未来计划。
