-- haifa_lua 兼容的算术性能基准测试
-- 移除时间测量，专注于算法性能

function test_integer_ops(n)
    local sum = 0
    
    for i = 1, n do
        sum = sum + i * 2 - 1
        sum = sum % 1000000
    end
    
    return sum
end

function test_float_ops(n) 
    local sum = 0.0
    
    for i = 1, n do
        local x = i / 1000.0
        sum = sum + x * x - x / 2.0
    end
    
    return sum
end

-- 执行测试
local n = 100000  -- 减小测试规模
print("Running arithmetic benchmark...")

local int_result = test_integer_ops(n)
local float_result = test_float_ops(n)

print("Results:")
print("Integer ops result:")
print(int_result)
print("Float ops result:")
print(float_result)