我已梳理现有实现与 docs 规划，并对标 jq 的常用能力，下面给出差距与迭代拆分建议。


## 现状小结

jq 前端：已支持标识符/字段、.、.foo、.[]、对象字面量、| 管道、函数调用子集（length, map, select, flatten, reduce）。见 compiler/jq_parser.py:1、compiler/jq_ast.py:1、compiler/jq_compiler.py:1。
VM/字节码：已支持 JSON 值、OBJ_GET/GET_INDEX/LEN_VALUE、多结果流 PUSH_EMIT/EMIT/POP_EMIT、FLATTEN/REDUCE 等；基础算术/比较/逻辑/位运算就绪。见 compiler/bytecode.py:1、compiler/bytecode_vm.py:1。
CLI：haifa jq 支持从 stdin/文件读取与 --slurp，逐条输出 JSON 行。见 compiler/jq_cli.py:1。
测试：解析/编译/运行/CLI 端到端用例齐全，覆盖上述功能。
对标 jq 的主要差距

语法/运算符：缺少二元算术与比较在 jq 表达式中的语法（现仅汇编层有 OPCODE），缺少 //（coalesce）、== != >= <=、and/or/not 的表达式语法优先级。
索引与切片：仅有 .[]，缺少 .foo[0]、.[i]、.[i:j] 等。
更多核心过滤器：keys/has/contains/add/join/sort/sort_by/min/max/min_by/max_by/unique/unique_by/group_by/any/all/first/last/reverse/to_entries/from_entries/with_entries 等常用集合操作。
字符串/数值工具：tostring/tonumber/split/gsub 等。
变量与绑定：as $x、$var、--arg/--argjson、用户定义函数 def 尚未支持。
CLI 兼容：-r/--raw-output、-c/--compact-output、-n/--null-input、-f filter.jq、--arg/--argjson、-R/--raw-input 等。
语义细节：真假值/空序列处理、除法返回类型（当前 DIV 为整除）、JZ 真值语义与 jq 对齐、错误信息与定位。
建议的里程碑与任务拆分

## 里程碑 1：表达式与真值语义打底（解析/编译/VM 收敛）

在解析器加入运算符优先级：+ - * / %, == != > >= < <=, and or not, //（coalesce）。覆盖括号分组与字面量混用。更新 compiler/jq_parser.py:1 与 compiler/jq_ast.py:1。
JZ 真值语义统一：在 VM 引入“falsy”判断（False, null, 0, "", [], {} 视为假），JZ/跳转基于通用真值，不再仅等于 0。更新 compiler/bytecode_vm.py:1，确保现有用例不回归。
除法/取模数值学：DIV 支持浮点（与 jq 一致），新增 TONUMBER/TOSTRING OPCODE 或内联转换策略。
测试：新增表达式与真值用例（比较、逻辑、coalesce、浮点除法）。完善错误定位信息（位置信息沿 AST 传播）。

## 里程碑 2：索引与切片
语法与 AST：新增 Index(expr)、Slice(start?, end?, step?)，支持 .foo[0]、.[i]、.[1:3]、.[::2] 等。
编译：将 Index/Slice 降解为 GET_INDEX/循环与边界检查；负索引与越界返回 null 对齐 jq。
测试：基础与组合管道用例（如 .items[0] | .name、.nums[1:3] | length）。

## 里程碑 3：核心集合过滤器一组（高价值、易落地）

keys, has, contains, add, join, reverse, first/last, any/all.
对应 VM 支持：必要时新增 KEYS, CONTAINS, JOIN 等 OPCODE，或在编译期展开为通用指令模板。
测试：对象/数组/边界类型用例与与空序列语义。

## 里程碑 4：排序与聚合家族

sort, sort_by(expr), min/max, min_by/max_by, unique/unique_by, group_by(expr).
编译策略：表达式求值缓冲 + Python 排序/分组执行（稳定性、键缺失/Null 处理对齐 jq 语义）。
测试：数字/字符串/对象字段组合，空值与重复值处理。

## 里程碑 5：变量与 CLI 互操作

语法：as $x、$var，AST 节点与作用域规则；编译：将 $var 映射为固定寄存器或环境表。
CLI：--arg name value、--argjson name json 注入；-r/--raw-output、-c/--compact-output、-n/--null-input、-f 读取过滤器文件、-R/--raw-input 行模式。
测试：变量绑定链式管道、raw/compact 输出、null-input 入口、filter 文件。

## 里程碑 6：字符串/正则工具

tostring, tonumber, split/ join, 基础 gsub（可先不支持复杂正则命名捕获）。
VM 支持与/或编译期展开；测试覆盖类型转换与错误容忍度。

## 里程碑 7：鲁棒性与文档

统一错误模型：语法/类型/运行时错误携带位置与上下文片段。
性能：大数组场景的迭代与拷贝削减（尽量使用迭代器与按需 FLATTEN）。
文档：补充用户指南、对标表（已支持/计划支持）、示例库，更新 docs/jq_design.md:1 进度快照。
优先落地的“快赢”项（建议先做）

运算符与真值统一（里程碑 1）：最大化解锁表达式组合能力，影响面可控。
索引/切片（里程碑 2）：极常用语法，收益立竿见影。
CLI 选项 -r/-c/-n 与 --arg/--argjson（里程碑 5，子集）：提升日常可用性。
验收与回归保障

为每个里程碑补充解析/编译/VM/CLI 四层测试用例，并保留现有测试全部通过。
端到端样例集（小型 JSON 集合 + 典型 jq 片段）用于持续回归。
在 compiler/README.md:1 与 docs/jq_design.md:1 标注已支持清单与剩余差距，保持透明可追踪。
需要我先从“运算符与真值语义统一（里程碑 1）”开始起草 parser/AST/VM 的改动方案和测试清单吗？
