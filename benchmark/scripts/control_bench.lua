-- Control flow workload shared across Lua and haifa_lua benchmarks
-- Covers branch heavy loops, nested iteration and complex predicates

local BRANCH_ITERATIONS = 20000
local NESTED_OUTER = 100
local WHILE_ITERATIONS = 20000

local function test_conditionals(n)
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
    return sum
end

local function test_nested_loops(n)
    local sum = 0
    for i = 1, n do
        for j = 1, 8 do
            for k = 1, 4 do
                sum = sum + i + j + k
            end
        end
    end
    return sum
end

local function test_while_loops(n)
    local sum = 0
    local i = 1
    while i <= n do
        sum = sum + i
        i = i + 1
    end
    return sum
end

local function test_complex_conditions(n)
    local count = 0
    for i = 1, n do
        if (i > 100 and i < 900) or (i % 7 == 0 and i % 11 ~= 0) then
            if i % 2 == 0 then
                count = count + 1
            end
        end
    end
    return count
end

print("Running control flow benchmark suite")

local cond_sum = test_conditionals(BRANCH_ITERATIONS)
local nested_sum = test_nested_loops(NESTED_OUTER)
local while_sum = test_while_loops(WHILE_ITERATIONS)
local complex_count = test_complex_conditions(BRANCH_ITERATIONS)

print("Branch-heavy loop sum:")
print(cond_sum)
print("Nested loop sum:")
print(nested_sum)
print("While loop sum:")
print(while_sum)
print("Complex condition hits:")
print(complex_count)
