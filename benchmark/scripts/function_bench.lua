-- Function call workload shared across Lua and haifa_lua benchmarks
-- Exercises recursion, iteration, deep call stacks and tight call loops

local SIMPLE_CALLS = 20000

function fibonacci_recursive(n)
    if n <= 1 then
        return n
    end
    return fibonacci_recursive(n - 1) + fibonacci_recursive(n - 2)
end

function fibonacci_iterative(n)
    if n <= 1 then
        return n
    end
    local a, b = 0, 1
    for _ = 2, n do
        a, b = b, a + b
    end
    return b
end

function deep_call(depth)
    if depth <= 0 then
        return 1
    end
    return depth + deep_call(depth - 1)
end

function simple_add(a, b)
    return a + b
end

function test_simple_calls(n)
    local sum = 0
    for i = 1, n do
        sum = sum + simple_add(i, i + 1)
    end
    return sum
end

print("Running function benchmark suite")

local recursive_result = fibonacci_recursive(24)
local iterative_result = fibonacci_iterative(20000)
local deep_call_result = deep_call(800)
local simple_sum = test_simple_calls(SIMPLE_CALLS)

print("Recursive fib(24):")
print(recursive_result)
print("Iterative fib(20000):")
print(iterative_result)
print("Deep call depth=800:")
print(deep_call_result)
print("Simple add calls (" .. SIMPLE_CALLS .. ") sum:")
print(simple_sum)
