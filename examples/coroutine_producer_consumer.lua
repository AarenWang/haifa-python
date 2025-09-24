-- 协程生产者-消费者示例：模拟生产者消费者模式
-- 这个例子展示了协程在协作式多任务中的应用

print("=== 协程生产者-消费者示例 ===")

-- 生产者协程
function producer()
    local items = {"苹果", "香蕉", "橙子", "葡萄", "草莓"}
    
    for i = 1, #items do
        print("生产者: 正在生产", items[i])
        coroutine.yield(items[i])  -- 产出物品
        print("生产者: 继续生产下一个物品")
    end
    
    print("生产者: 所有物品生产完毕")
    return nil  -- 生产结束
end

-- 消费者函数（主程序扮演消费者）
function consumer()
    local co = coroutine.create(producer)
    local item_count = 0
    
    while true do
        local success, item = coroutine.resume(co)
        
        if not success then
            print("消费者: 协程执行出错")
            break
        end
        
        if item == nil then
            print("消费者: 没有更多物品了")
            break
        end
        
        item_count = item_count + 1
        print("消费者: 接收到第" .. item_count .. "个物品:", item)
        print("消费者: 正在消费", item)
        print("消费者: 请求下一个物品...")
        print("---")
    end
    
    print("消费者: 总共消费了", item_count, "个物品")
    print("协程最终状态:", coroutine.status(co))
end

-- 开始消费流程
consumer()