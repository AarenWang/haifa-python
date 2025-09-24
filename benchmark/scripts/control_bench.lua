-- 控制流性能基准测试
-- 测试条件分支、循环嵌套等控制结构的性能

-- 条件分支测试
function test_conditionals(n)
    local start_time = os and os.clock and os.clock() or 0
    local sum = 0
    
    for i = 1, n do
        if i % 5 == 0 then
            sum = sum + 5
        elseif i % 3 == 0 then
            sum = sum + 3
        elseif i % 2 == 0 then
            sum = sum + 2
        else
            sum = sum + 1
        end
    end
    
    local end_time = os and os.clock and os.clock() or 0
    return end_time - start_time, sum
end

-- 嵌套循环测试
function test_nested_loops(n)
    local start_time = os and os.clock and os.clock() or 0
    local sum = 0
    
    for i = 1, n do
        for j = 1, 10 do
            for k = 1, 5 do
                sum = sum + i + j + k
            end
        end
    end
    
    local end_time = os and os.clock and os.clock() or 0
    return end_time - start_time, sum
end

-- while 循环测试
function test_while_loops(n)
    local start_time = os and os.clock and os.clock() or 0
    local sum = 0
    local i = 1
    
    while i <= n do
        sum = sum + i
        i = i + 1
    end
    
    local end_time = os and os.clock and os.clock() or 0
    return end_time - start_time, sum
end

-- 复杂条件测试
function test_complex_conditions(n)
    local start_time = os and os.clock and os.clock() or 0
    local count = 0
    
    for i = 1, n do
        if (i > 100 and i < 900) or (i % 7 == 0 and i % 11 ~= 0) then
            if i % 2 == 0 then
                count = count + 1
            end
        end
    end
    
    local end_time = os and os.clock and os.clock() or 0
    return end_time - start_time, count
end

print("Running control flow benchmarks...")

-- 执行测试
local n = 100000
local cond_time, cond_sum = test_conditionals(n)
local loop_time, loop_sum = test_nested_loops(1000)
local while_time, while_sum = test_while_loops(n)
local complex_time, complex_count = test_complex_conditions(n)

print("Results:")
print("Conditionals: " .. string.format("%.4f", cond_time) .. " seconds, sum: " .. cond_sum)
print("Nested loops: " .. string.format("%.4f", loop_time) .. " seconds, sum: " .. loop_sum)
print("While loops: " .. string.format("%.4f", while_time) .. " seconds, sum: " .. while_sum)
print("Complex conditions: " .. string.format("%.4f", complex_time) .. " seconds, count: " .. complex_count)