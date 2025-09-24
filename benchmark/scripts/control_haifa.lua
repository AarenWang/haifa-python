-- haifa_lua 兼容的控制流基准测试

function test_conditionals(n)
    local sum = 0
    
    for i = 1, n do
        if i % 2 == 0 then
            sum = sum + i
        else
            sum = sum + 1
        end
    end
    
    return sum
end

function test_nested_loops(n)
    local sum = 0
    
    for i = 1, n do
        for j = 1, n do
            sum = sum + i * j
        end
    end
    
    return sum
end

function test_while_loops(n)
    local i = 1
    local sum = 0
    
    while i <= n do
        sum = sum + i * i
        i = i + 1
    end
    
    return sum
end

function test_complex_conditions(n)
    local count = 0
    
    for i = 1, n do
        if i % 3 == 0 and i % 5 == 0 then
            count = count + 2
        elseif i % 3 == 0 or i % 5 == 0 then
            count = count + 1
        end
    end
    
    return count
end

-- 执行测试 (减小规模)
print("Running control flow benchmarks...")

local cond_sum = test_conditionals(10000)
local loop_sum = test_nested_loops(100)  -- 100x100 loops
local while_sum = test_while_loops(1000)
local complex_count = test_complex_conditions(1000)

print("Results:")
print("Conditionals sum:")
print(cond_sum)
print("Nested loops sum:")
print(loop_sum)
print("While loops sum:")
print(while_sum)
print("Complex conditions count:")
print(complex_count)