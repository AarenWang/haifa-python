-- 中文测试文件
print("你好世界！")
print("Hello World!")

-- 定义一个函数，包含中文注释
function 问候(名字)
    return "你好，" .. 名字 .. "！"
end

local 结果 = 问候("张三")
print(结果)

-- 测试数字和中文混合
local 数字 = 42
print("答案是：" .. 数字)