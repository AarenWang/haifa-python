-- 协程数据传递示例：演示协程间的数据交换
-- 这个例子展示了如何在协程和主程序之间传递数据

print("=== 协程数据传递示例 ===")

function data_processor(initial_data)
    local received = coroutine.yield("处理结果", initial_data * 2)
    received = coroutine.yield("累加结果", initial_data * 2 + received)
    return "最终处理完成", initial_data * 2 + received * 3
end

-- 创建协程
local co = coroutine.create(data_processor)

local function resume_and_show(co, ...)
    print("主程序接收到:", coroutine.resume(co, ...))
end

-- 启动协程并传入初始数据
print("--- 启动协程，传入数据: 10 ---")
resume_and_show(co, 10)

-- 传入新数据继续协程
print("--- 传入新数据: 5 ---")
resume_and_show(co, 5)

-- 传入最后的数据
print("--- 传入最终数据: 3 ---")
resume_and_show(co, 3)

