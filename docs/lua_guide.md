# Lua 运行时标准库草案

本草案概述 `haifa_lua` 运行时在 Milestone 2C 中提供的核心标准库，并演示如何借助 `LuaEnvironment` 完成全局环境的装载与热更新。

## 1. 基础内建函数

### 1.1 `print`
- 语法：`print(value1, value2, ...)`
- 行为：依次将参数转换为字符串，以制表符连接后写入虚拟机输出缓冲区（`vm.output`）。
- 返回：`nil`

示例：
```lua
print("hello", 42)
-- 输出缓冲区得到 "hello\t42"
```

## 2. `math` 库

可直接调用 `math.*` 函数（由于词法规则放宽，`.` 可作为标识符一部分）。当前提供：

| 函数 | 说明 |
| --- | --- |
| `math.abs(x)` | 绝对值 |
| `math.sqrt(x)` | 平方根 |
| `math.floor(x)` / `math.ceil(x)` | 向下/向上取整 |
| `math.min(a, b, ...)` | 取最小值（变参） |
| `math.max(a, b, ...)` | 取最大值（变参） |
| `math.pi` | 常量 π |

示例：
```lua
local a = math.max(-3, 5, 2)
local len = math.ceil(1.2)
return a + len  -- 结果 7.0
```

## 3. `table` 库

标准库暂以列表（Python `list`）模拟顺序表，索引从 1 开始：

- `table.insert(t, value)` / `table.insert(t, pos, value)`：末尾或指定位置插入。
- `table.remove(t)` / `table.remove(t, pos)`：移除末尾或指定位置，返回被移除的元素，越界时返回 `nil`。

示例：
```lua
local items = {}
table.insert(items, 10)
table.insert(items, 1, 5)
local last = table.remove(items) -- 10
```

## 4. `string` 库

- `string.len(s)`：返回字符串长度。

示例：
```lua
return string.len("haifa")  -- 5
```

## 5. 全局环境与热更新

`run_source` / `run_script` 会为新建环境自动装载标准库；若需跨脚本复用或自定义行为，可显式管理 `LuaEnvironment`：

```python
from haifa_lua import BuiltinFunction, LuaEnvironment, install_core_stdlib, run_source

# 只需在初始化时装载一次标准库
env = LuaEnvironment()
install_core_stdlib(env)

# 自定义 print，捕获输出用于调试或热更新
captured = []

def capture(args, vm):
    captured.append(tuple(args))

env.register("print", BuiltinFunction("print", capture))
run_source("print(1, 2)", env)
assert captured == [(1, 2)]
```

运行结束后，所有写入全局表的值都会同步回 `LuaEnvironment`，因而可以通过 Python 侧覆盖或更新库函数，下一次执行时立即生效。

## 6. 综合示例

```lua
function make_adder(x)
    return function(...)
        local max_val = math.max(...)
        return max_val + x, string.len("ok")
    end
end

local add = make_adder(10)
local a, b = add(1, 7, 3)
print(a, b)  -- 输出 "17.0\t2"
return a, b
```

以上示例展示了标准库函数与闭包、多返回值之间的互操作，亦验证了环境在执行结束后的可见更新。


## 7. 协程基础

标准库新增 `coroutine.create/resume/yield`，可在 Lua 脚本中以同步方式描述异步流程：

```lua
function worker(a)
    local delta = coroutine.yield(a + 1)
    return a + delta
end

local co = coroutine.create(worker)
local ok1, first = coroutine.resume(co, 10)  -- ok1 = true, first = 11
local ok2, result = coroutine.resume(co, 5)  -- ok2 = true, result = 15
```

注意：
- 初次 `resume` 的参数作为协程函数的入参；之后的 `resume` 参数会作为 `coroutine.yield` 的返回值。
- 协程运行过程中可修改全局环境；结束或挂起时，最新全局值会写回 `LuaEnvironment`。
- 若直接在主线程调用 `coroutine.yield` 会触发运行时错误。

