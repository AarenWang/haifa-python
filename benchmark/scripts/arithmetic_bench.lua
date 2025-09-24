-- 算术运算性能基准测试
-- 测试整数和浮点运算的执行速度

function test_integer_ops(n)
    local sum = 0
    local start_time = os and os.clock and os.clock() or 0
    
    for i = 1, n do
        sum = sum + i * 2 - 1
        sum = sum % 1000000
    end
    
    local end_time = os and os.clock and os.clock() or 0
    return end_time - start_time, sum
end

function test_float_ops(n) 
    local sum = 0.0
    local start_time = os and os.clock and os.clock() or 0
    
    for i = 1, n do
        local x = i / 1000.0
        sum = sum + x * x - x / 2.0
    end
    
    local end_time = os and os.clock and os.clock() or 0
    return end_time - start_time, sum
end

-- 执行测试
local n = 1000000
print("Running arithmetic benchmark with " .. n .. " operations...")

local int_time, int_result = test_integer_ops(n)
local float_time, float_result = test_float_ops(n)

print("Results:")
print("Integer ops: " .. string.format("%.4f", int_time) .. " seconds, result: " .. int_result)
print("Float ops: " .. string.format("%.4f", float_time) .. " seconds, result: " .. string.format("%.6f", float_result))