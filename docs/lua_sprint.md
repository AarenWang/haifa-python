
# Lua 解释器规划与迭代拆分

## 总体目标
- 在现有 Core VM 基础上实现 Lua 语言子集：支持数据类型（数值、字符串、布尔、表）、表达式、控制流、函数与闭包、标准库核心能力。
- 提供 `pylua` CLI，可加载执行 `.lua` 脚本，并复用现有可视化/调试设施。
- 逐步引入协程、错误处理、调试器等高级特性，保持 Core VM 与 JQ 模块兼容。

## 架构规划
1. Lua 前端解析：实现词法/语法分析，生成 Lua 专用 AST。
2. AST → Core VM 映射：设计寄存器/栈帧模型，必要时扩展 opcode（表操作、闭包、返回多值等）。
3. 运行时环境：局部变量、Upvalue、全局表、标准库注册。
4. 调试/可视化增强：展示多返回值、调用栈、源代码位置信息。
5. CLI 入口与工具：`pylua` 命令、脚本执行、REPL（选做）。

## 里程碑拆分

### Milestone 1：Lua 语法与基础执行 ✅（已完成）
- [x] Lua 语法解析器：支持表达式、赋值、`if`、`while`、函数定义与调用。
- [x] Lua AST 节点与 Core VM 映射初版：局部变量、全局表、直接函数调用。
- [x] 基础 CLI：`pylua --execute/脚本`，配套单元测试 `test_lua_basic`。
- [x] 文档更新：README/guide/reference 说明 Lua 子集与示例脚本。

### Milestone 2：闭包、Upvalue、标准库

为降低风险，拆分为三个迭代：

**Milestone 2A：闭包与 Upvalue 基础**
- [x] VM 扩展：闭包模型与 upvalue 指令（`MAKE_CELL`, `CELL_GET`, `CELL_SET`, `CLOSURE`, `CALL_VALUE`, `BIND_UPVALUE`）。
- [x] 语义分析：识别自由变量、构建闭包捕获列表。
- [x] 编译器：局部变量 cell 化，支持函数返回闭包、闭包调用与 upvalue 绑定。
- [x] 单元/集成测试：累加器、共享 upvalue、多层嵌套调用；核心 VM 指令覆盖。

**Milestone 2A-1：VM 层改造**
- [x] 新增 opcode：MAKE_CELL/CELL_GET/CELL_SET（捕获变量用）、CLOSURE、CALL_VALUE、BIND_UPVALUE。
- [x] BytecodeVM 维护 upvalue 列表，CALL_VALUE 需保存/恢复 current_upvalues，闭包对象结构确定。
- [x] 更新可视化器显示（寄存器高亮继续适配）。

**Milestone 2A-2：编译期自由变量分析**
- [x] 在 haifa_lua 内新增分析模块，对 AST 做作用域递归，标记被内层函数引用的局部变量。
- [x] 编译器根据分析结果生成 cell 初始化、CELL_SET/GET、闭包 upvalue 列表。

**Milestone 2A-3：闭包编译与调用** 
- [x] 函数定义：生成 MAKE_CELL、CLOSURE，内层函数 prolog 插入 BIND_UPVALUE。
- [x] 函数调用：对变量储存在 register 的闭包使用 CALL_VALUE。

**Milestone 2B：多返回值与可变参数**
- [x] 支持 Lua 函数多返回值、尾调用、`...` 可变参数。
- [x] VM 指令：`RETURN_MULTI`, `CALL_VARARG`、栈帧扩展。
- [x] 增加测试：多返回值解构、链式调用、vararg 处理。

**Milestone 2C：标准库核心**
- [x] 内建库：`print`, `math` 基础函数、`table.insert/remove`, `string.len` 等常用函数。
- [x] 全局环境与库注册机制，允许热更新。
- [x] 文档/示例：`docs/lua_guide.md` 草案、标准库使用示例。
- [x] 集成测试：综合脚本验证库与闭包、多返回值的互操作。

### Milestone 3：协程与调试增强
- [x] 协程语义：`coroutine.create/resume/yield`，VM 上实现多执行上下文。
- [x] 可视化器显示 Lua 调用栈、Upvalue、协程状态，支持断点/单步。
- [x] 错误处理与诊断：Lua 风格的栈回溯、行列信息。
- [x] 扩展 CLI，提供调试模式、trace 导出。

### Milestone 4：性能与文档发布
- [ ] 性能优化：缓存常用路径、减少表/字符串拷贝、评估 JIT 钩子（规划即可）。
- [ ] 编写 `docs/lua_guide.md`、标准库说明、迁移指南。
- [ ] 扩展 CI：增加 Lua 脚本测试集合，集成 GitHub Actions 构建/发布。
- [ ] 评估与 JQ/Core VM 的兼容影响，更新 README 总览。

### Milestone 5：表与表达式扩展
- [x] AST/Parser：支持表构造器（数组部分、键值对）、字段访问/索引表达式、方法调用语法。
- [X] 赋值语义：允许多目标赋值、`local` 批量声明，并与多返回值/vararg 对齐。
- [x] 运算符补全：实现字符串拼接 `..`、长度运算 `#`、必要的比较/算术扩展。
- [ ] 编译器/VM：为表读写、`#` 运算等生成字节码，实现运行时的 Lua 表模型（dict/list 混合）。
- [ ] 标准库/测试：更新 `table` 库 API，补充表构造、字段更新、赋值语义的单元与集成测试。

### Milestone 6：控制流覆盖与块语义
- [x] 语法支持：补齐 `elseif`、`repeat ... until`、`break`、`do ... end` 块。
- [x] 循环结构：实现数值 `for`（含步长）、泛型 `for`（配合迭代器）以及循环局部变量作用域。
- [ ] 编译器：生成相应跳转/作用域处理，确保与闭包、协程兼容。
- [ ] 测试：添加典型循环与条件组合场景，验证 `break`、`until`、`for` 的边界行为。

### Milestone 7：标准库与错误处理增强
- [x] 内置函数：增加 `type`、`next`、`pairs`/`ipairs`、`tonumber`、`tostring`、`error`、`assert` 等核心能力。
- [x] 字符串/表扩展：实现 `string.sub/upper/lower`、`table.concat/sort` 等高频 API。
- [x] 错误与保护调用：支持 `pcall`/`xpcall`、改进异常对象，补充错误传播测试。
- [ ] 文档：更新 `docs/lua_guide.md` 与 CLI 帮助，列出标准库覆盖范围与示例。

### Milestone 8：元表与对象语义
- [ ] 语言特性：实现冒号方法调用语法、字面量方法定义生成，并在 VM 中支持 `self` 约定。
- [ ] 元表机制：为表对象补齐 `setmetatable`、`getmetatable`、`rawget`/`rawset`/`rawequal` 等 API，驱动 `__index`、`__newindex` 等基础元方法。
- [ ] 运算符扩展：接入比较/算术元方法（如 `__add`、`__eq`），并与现有二元运算发射路径整合。
- [ ] 测试：覆盖面向对象模式、原型继承示例以及元方法回退路径。

### Milestone 9：模块加载与动态代码执行
- [ ] 全局函数：补齐 `require`、`dofile`、`load`/`loadfile` 等入口，定义 chunk 环境与返回值语义。
- [ ] 包系统：实现 `package.searchers`（或 Lua 5.1 `package.loaders`）最小可用集合，支持基于文件系统的模块查找与缓存。
- [ ] 环境隔离：允许为模块自定义 `_ENV`/`_G`，并提供沙箱执行选项。
- [ ] CLI/调试：更新 `pylua` 支持脚本路径解析、错误定位到模块来源，并补充相关文档与示例。

### Milestone 10：标准库补全与运行时服务
- [ ] 字符串库：实现模式匹配与格式化（`string.find`、`gsub`、`match`、`format` 等）。
- [ ] 表/数学库：补齐 `table.pack/unpack/move` 以及 `math` 的三角、随机、常数接口，评估 `utf8` 库需求。
- [ ] 系统库：按需提供 `os`、`io`、`debug` 等库的可控实现，确保与沙箱策略一致。
- [ ] 错误与调试：输出 Lua 兼容的栈回溯信息，开放 `debug.traceback` 等调试入口并扩展测试覆盖。

### Milestone 11：语法与运算符对齐
- [ ] 语句集：支持 `goto`/标签语法、`::label::` 跳转，并处理作用域合法性验证。
- [ ] 运算符：实现乘方 `^`、整除 `//`、位运算符（`&`、`|`、`~`、`<<`、`>>`）等 Lua 5.3+ 语义，完善短路行为。
- [ ] 词法/解析：更新词法分析器关键字、操作符优先级表，并保证与现有语义保持向后兼容。
- [ ] 测试/文档：补充相应单元与集成测试，在指南中说明完整的语言特性支持矩阵。

### Milestone 12：协程 API 完备与兼容性
- 目标
  - 完成 Lua 协程库 API，定义与实现可 yield 边界与错误信息，使之与 Lua 语义兼容或明确差异。
  - 强化可视化与事件，补齐调试工具对协程的可观测性。
- 范围
  - API 完备
    - `coroutine.status(thread)`：返回 `"running" | "suspended" | "dead"`。
    - `coroutine.wrap(f)`：返回一个函数，调用即 `resume`；报错时抛出 Lua 风格异常；多返回值直传。
    - `coroutine.running()`：返回当前线程与是否为主线程标记（`thread, isMain`）。
    - `coroutine.isyieldable()`：在可 yield 的上下文返回 `true`，否则 `false`。
  - 语义与边界
    - 明确定义“可 yield 边界”：是否允许跨 `pcall`/`xpcall`、元方法、内建（C）函数边界 `yield`；不允许时给出一致错误信息（例如 `attempt to yield across a C-call boundary`）。
    - 保持/巩固现有约束：不能恢复运行中的协程、不能恢复已结束的协程；`resume` 返回 `(ok, ...)` 约定。
  - 错误与回溯
    - `debug.traceback(thread?)`：允许传入目标协程，返回该协程的栈回溯；错误消息前缀与源位置信息对齐。
    - `resume` 失败信息与 `traceback` 风格一致（含文件名、行号）。
  - 事件与可视化
    - 在事件/快照中补充字段：`is_main`、`yieldable`、`status`；可视化器显示 `coroutine.status`、最近错误。
    - 时间线为 `resume`/`yield`/`complete` 区分颜色与状态标签；选中协程时展示 `last_resume_args`/`last_yield`。
  - 文档与示例
    - 更新 `docs/lua_guide.md` 协程章节，新增 `wrap`/`status`/`running`/`isyieldable` 用法与差异说明。
    - 新增 `examples/coroutine_wrap_status.lua` 展示 `wrap` 多返回值与错误传播。
- 测试与验收
  - 单元测试：`status`/`running`/`isyieldable` 基本行为；`wrap` 的成功/错误传播；`wrap` 的多返回值直传。
  - 语义测试：在 `pcall`/`xpcall`/内建边界内 `yield` 的行为与错误信息一致性。
  - 可视化器快照包含并显示新字段；CLI trace 过滤 `coroutine` 保持可读。
  - 全量测试通过；新增示例运行输出与预期一致。
- 完成标准
  - 新增 API 可用并在 stdlib 注册，具备完整测试覆盖。
  - `debug.traceback(thread)` 返回目标协程堆栈与消息。
  - 可视化器与 CLI 能显示/过滤新字段。
  - 文档与示例同步更新，列明与 Lua 官方差异（若有）。

## 开发原则
- 每个里程碑保持测试通过，尽量不破坏 Core/JQ 现有行为。
- 文档和示例与功能迭代同步更新。
- 对新增 opcode/指令保持 Core VM 可视化与调试器兼容性。
