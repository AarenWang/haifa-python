-- 协程数据传递示例：演示协程间的数据交换
-- 这个例子展示了如何在协程和主程序之间传递数据

print("=== 协程数据传递示例 ===")

function data_processor(initial_data)
    print("协程接收到初始数据:", initial_data)
    
    -- 处理数据并返回结果，同时接收新数据
    local received = coroutine.yield("处理结果: " .. initial_data * 2)
    print("协程接收到新数据:", received)
    
    -- 再次处理并返回
    received = coroutine.yield("累加结果: " .. (initial_data * 2 + received))
    print("协程接收到最终数据:", received)
    
    return "最终处理完成: " .. (initial_data * 2 + received * 3)
end

-- 创建协程
local co = coroutine.create(data_processor)

-- 启动协程并传入初始数据
print("--- 启动协程，传入数据: 10 ---")
local success, result = coroutine.resume(co, 10)
print("主程序接收到:", result)

-- 传入新数据继续协程
print("--- 传入新数据: 5 ---")
success, result = coroutine.resume(co, 5)
print("主程序接收到:", result)

-- 传入最后的数据
print("--- 传入最终数据: 3 ---")
success, result = coroutine.resume(co, 3)
print("主程序接收到:", result)