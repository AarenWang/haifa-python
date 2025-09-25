-- 基础算术运算测试 (简化版)
-- 适配 haifa_lua 的当前功能

-- 简单计算测试
function simple_calculation()
    local sum = 0
    for i = 1, 100 do
        sum = sum + i
    end
    return sum
end

-- 执行测试
print("Starting simple arithmetic test...")
local result = simple_calculation()
print("Sum of 1 to 100:")
print(result)
print("Test completed")