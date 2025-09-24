-- 函数调用性能基准测试
-- 测试递归调用、迭代调用和深度调用栈的性能

-- 递归斐波那契（测试递归调用开销）
function fibonacci_recursive(n)
    if n <= 1 then
        return n
    end
    return fibonacci_recursive(n-1) + fibonacci_recursive(n-2)
end

-- 迭代斐波那契（测试循环性能）
function fibonacci_iterative(n)
    if n <= 1 then 
        return n 
    end
    
    local a, b = 0, 1
    for i = 2, n do
        a, b = b, a + b
    end
    return b
end

-- 深层调用栈测试
function deep_call(depth)
    if depth <= 0 then
        return 1
    end
    return depth + deep_call(depth - 1)
end

-- 简单函数调用测试
function simple_add(a, b)
    return a + b
end

function test_simple_calls(n)
    local start_time = os and os.clock and os.clock() or 0
    local sum = 0
    
    for i = 1, n do
        sum = sum + simple_add(i, i+1)
    end
    
    local end_time = os and os.clock and os.clock() or 0
    return end_time - start_time, sum
end

print("Running function call benchmarks...")

-- 执行测试
local start_time = os and os.clock and os.clock() or 0
local result1 = fibonacci_recursive(25)  -- 降低到25避免过长时间
local recursive_time = (os and os.clock and os.clock() or 0) - start_time

start_time = os and os.clock and os.clock() or 0
local result2 = fibonacci_iterative(100000)
local iterative_time = (os and os.clock and os.clock() or 0) - start_time

start_time = os and os.clock and os.clock() or 0
local result3 = deep_call(1000)  -- 降低深度避免栈溢出
local deep_call_time = (os and os.clock and os.clock() or 0) - start_time

local simple_time, simple_sum = test_simple_calls(1000000)

print("Results:")
print("Recursive fib(25): " .. string.format("%.4f", recursive_time) .. " seconds, result: " .. result1)
print("Iterative fib(100K): " .. string.format("%.4f", iterative_time) .. " seconds, result: " .. result2)
print("Deep call(1000): " .. string.format("%.4f", deep_call_time) .. " seconds, result: " .. result3)
print("Simple calls(1M): " .. string.format("%.4f", simple_time) .. " seconds, sum: " .. simple_sum)