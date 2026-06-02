建议先把 Scheme 做成一个独立前端：`haifa_scheme/`，先用 tree-walking interpreter 跑通语义，不急着接 `compiler/bytecode_vm.py`。Scheme 的核心价值在词法作用域、闭包、递归、list/pair、尾调用；过早塞进现有 VM 会把 Lua/jq 的包袱带进去。

**目标范围**

先实现一个教学型 Scheme 子集，偏 R5RS 风格：

1. 语法层
   - tokenizer：括号、symbol、number、string、boolean、quote `'`
   - parser：S-expression，解析成 Python 数据结构或轻量 AST
   - 支持注释 `; ...`

2. 核心求值
   - literals：number/string/bool/symbol/nil
   - special forms：
     - `quote`
     - `if`
     - `define`
     - `lambda`
     - `begin`
     - `set!`
     - `let`
     - `let*`
     - `letrec`
     - `and`
     - `or`
     - `cond`
   - 函数调用、闭包、递归
   - 词法作用域环境链

3. 数据类型
   - Scheme boolean：`#t` / `#f`
   - 空表：`()`
   - pair/list：`cons`, `car`, `cdr`, `list`, `null?`, `pair?`, `list?`
   - number/string/symbol 基础类型
   - 打印格式：`(1 2 3)`、`#t`、`#f`、字符串带引号

4. 标准库第一批
   - arithmetic：`+ - * /`
   - compare：`= < <= > >=`
   - equality：`eq?`, `equal?`
   - predicates：`number?`, `string?`, `symbol?`, `boolean?`, `procedure?`
   - list helpers：`length`, `append`, `map`, `filter`, `foldl` 可后置

5. CLI / REPL
   - 新命令建议：`pyscheme`
   - 本地运行优先：`python3 -m haifa_scheme.cli`
   - 支持：
     - script file
     - `-e/--execute`
     - REPL
     - `--print-output`
   - 错误信息先做到清楚，后续再做 source location traceback

**建议拆 6 次提交**

**提交 1：Scheme 包骨架 + Reader**
- 新增 `haifa_scheme/`
- 新增 tokenizer/parser/reader
- 新增 `SchemeSyntaxError`
- 测试：
  - numbers/strings/booleans/symbols
  - nested lists
  - quote shorthand
  - comments
- 文档：
  - `docs/scheme_sprint.md` 初版路线图

**提交 2：最小 Eval 核心**
- 实现 environment、procedure、runtime
- 支持 literals、symbol lookup、function call
- 支持 special forms：`quote`, `if`, `define`, `lambda`, `begin`
- 标准库：`+ - * / = < >`
- 测试：
  - arithmetic
  - global define
  - lambda call
  - recursive factorial

**提交 3：List/Pair 数据模型**
- 新增 `Pair` / empty list 表示
- 实现打印器 `to_scheme_string`
- 标准库：
  - `cons`, `car`, `cdr`, `list`
  - `null?`, `pair?`, `list?`
  - `eq?`, `equal?`
- 测试：
  - proper list
  - nested list
  - dotted pair 可选，建议此提交先不做 reader dotted syntax，只支持 runtime pair

**提交 4：作用域与绑定完整化**
- special forms：
  - `set!`
  - `let`
  - `let*`
  - `letrec`
  - `and`
  - `or`
  - `cond`
- 测试：
  - lexical closure
  - shadowing
  - mutation
  - mutual recursion with `letrec`

**提交 5：CLI / REPL / docs / examples**
- 新增 `haifa_scheme/cli.py`
- `pyproject.toml` 增加 script：`pyscheme = "haifa_scheme.cli:main"`
- 新增 examples：
  - `examples/hello.scm`
  - `examples/factorial.scm`
  - `examples/lists.scm`
  - `examples/closures.scm`
- 新增 `docs/scheme_guide.md`
- README 增加 Scheme runtime 简介

**提交 6：尾调用与稳固化**
- 实现 trampoline 或显式 eval loop，避免递归爆栈
- 支持 tail position：
  - `if`
  - `begin`
  - lambda body
  - `let` family body
  - `cond`
- 测试：
  - 大递归 countdown
  - tail-recursive factorial
- 整理错误类型：
  - `SchemeRuntimeError`
  - 参数数量错误
  - 类型错误
  - 未绑定变量

**暂时不做的高级功能**

这些建议放到第二阶段：

- macro：`define-syntax`, `syntax-rules`
- quasiquote：`` ` ``, `,`, `,@`
- vectors
- ports / file IO
- exact/inexact number tower
- continuations：`call/cc`
- compiler-to-bytecode
- 与现有 VM visualizer 集成

**我建议的第一步**

先做“提交 1 + 提交 2”，也就是 reader + 最小 eval。验收标准可以很明确：

```scheme
(define square (lambda (x) (* x x)))
(square 9)
```

输出：

```text
81
```

以及：

```scheme
(define fact
  (lambda (n)
    (if (= n 0)
        1
        (* n (fact (- n 1))))))
(fact 5)
```

输出：

```text
120
```

这个起步小而硬，后面 list、let、REPL、尾调用都能稳稳往上叠。