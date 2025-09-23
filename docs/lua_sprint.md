
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

### Milestone 1：Lua 语法与基础执行
- [ ] Lua 语法解析器：支持表达式、赋值、`if`、`while`/`repeat`、函数定义与调用。
- [ ] Lua AST 节点与 Core VM 映射初版：局部变量、全局表、简单函数调用（无闭包）。
- [ ] 扩展 VM 指令：`TABLE_NEW`, `TABLE_SET`, `TABLE_GET`, `RETURN_MULTI`, `CALL_VARARG` 等初版。
- [ ] `pylua` CLI 可执行基础脚本；提供示例和单元测试。

### Milestone 2：闭包、Upvalue、标准库
- [ ] 设计函数闭包捕获模型，引入 Upvalue 访问 opcode。
- [ ] 支持多返回值、可变参数、尾调用优化。
- [ ] 实现标准库核心：`print`, `math`, `table`, `string` 子集中常用函数。
- [ ] 增强测试覆盖（闭包、表操作、标准库调用）。

### Milestone 3：协程与调试增强
- [ ] 协程语义：`coroutine.create/resume/yield`，VM 上实现多执行上下文。
- [ ] 可视化器显示 Lua 调用栈、Upvalue、协程状态，支持断点/单步。
- [ ] 错误处理与诊断：Lua 风格的栈回溯、行列信息。
- [ ] 扩展 CLI，提供调试模式、trace 导出。

### Milestone 4：性能与文档发布
- [ ] 性能优化：缓存常用路径、减少表/字符串拷贝、评估 JIT 钩子（规划即可）。
- [ ] 编写 `docs/lua_guide.md`、标准库说明、迁移指南。
- [ ] 扩展 CI：增加 Lua 脚本测试集合，集成 GitHub Actions 构建/发布。
- [ ] 评估与 JQ/Core VM 的兼容影响，更新 README 总览。

## 开发原则
- 每个里程碑保持测试通过，尽量不破坏 Core/JQ 现有行为。
- 文档和示例与功能迭代同步更新。
- 对新增 opcode/指令保持 Core VM 可视化与调试器兼容性。