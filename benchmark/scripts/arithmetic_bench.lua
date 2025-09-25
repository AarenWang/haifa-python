-- Arithmetic workload shared by Lua and haifa_lua benchmarks
-- Focuses on integer and floating point heavy loops without relying on os.clock

local ITERATIONS = 20000

local function test_integer_ops(n)
    local sum = 0
    for i = 1, n do
        sum = sum + i * 2 - 1
        sum = sum % 1000000
    end
    return sum
end

local function test_float_ops(n)
    local sum = 0.0
    for i = 1, n do
        local x = i / 1000.0
        sum = sum + x * x - x / 2.0
    end
    return sum
end

print("Running arithmetic benchmark with " .. ITERATIONS .. " iterations")

local int_result = test_integer_ops(ITERATIONS)
local float_result = test_float_ops(ITERATIONS)

print("Integer ops result:")
print(int_result)
print("Float ops result:")
print(string.format("%.6f", float_result))
