-- 协程生产者-消费者示例：模拟生产者消费者模式
-- 这个例子展示了协程在协作式多任务中的应用

print("=== 协程生产者-消费者示例 ===")

function get_item(index)
    if index == 1 then
        return "苹果"
    end
    if index == 2 then
        return "香蕉"
    end
    if index == 3 then
        return "橙子"
    end
    if index == 4 then
        return "葡萄"
    end
    if index == 5 then
        return "草莓"
    end
    return nil
end

-- 生产者协程
function producer()
    local index = 0

    while index < 5 do
        index = index + 1
        local item = get_item(index)
        coroutine.yield("物品", item)
    end

    return "完成"
end

-- 消费者函数（主程序扮演消费者）
function consumer()
    local co = coroutine.create(producer)
    local item_count = 0

    while item_count < 5 do
        item_count = item_count + 1
        print("消费者: 请求第", item_count, "个物品")
        print("返回值:", coroutine.resume(co))
        local item = get_item(item_count)
        print("消费者: 正在消费", item)
        print("消费者: 请求下一个物品...")
        print("---")
    end

    print("协程最终返回:", coroutine.resume(co))
    print("消费者: 总共消费了", item_count, "个物品")
end

-- 开始消费流程
consumer()

