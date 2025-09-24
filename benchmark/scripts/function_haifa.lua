-- haifa_lua 兼容的函数调用基准测试

function fibonacci(n)
    if n <= 1 then
        return n
    else
        return fibonacci(n-1) + fibonacci(n-2)
    end
end

function fibonacci_iterative(n)
    if n <= 1 then
        return n
    end
    
    local a = 0
    local b = 1
    
    for i = 2, n do
        local temp = a + b
        a = b
        b = temp
    end
    
    return b
end

function deep_call(n)
    if n <= 0 then
        return 0
    else
        return 1 + deep_call(n - 1)
    end
end

function simple_calls(n)
    local sum = 0
    for i = 1, n do
        sum = sum + i
    end
    return sum
end

-- 执行测试 (减小规模)
print("Running function call benchmarks...")

local result1 = fibonacci(20)  -- 减小到20
local result2 = fibonacci_iterative(1000)  -- 减小到1000
local result3 = deep_call(100)  -- 减小到100
local result4 = simple_calls(10000)  -- 减小到10000

print("Results:")
print("Recursive fib(20) result:")
print(result1)
print("Iterative fib(1000) result:")
print(result2)
print("Deep call(100) result:")
print(result3)
print("Simple calls(10K) sum:")
print(result4)