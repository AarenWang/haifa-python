-- 协程基础示例：简单的协程创建和恢复
-- 这个例子演示了协程的基本生命周期

print("=== 协程基础示例 ===")

-- 定义一个简单的协程函数
function simple_coroutine()
    print("协程开始执行")
    coroutine.yield("第一次暂停")

    print("协程恢复执行")
    coroutine.yield("第二次暂停")

    print("协程即将结束")
    return "协程执行完毕"
end

-- 创建协程
local co = coroutine.create(simple_coroutine)
print("协程已创建，等待调度")

local function resume_and_report(co, ...)
    print("返回值:", coroutine.resume(co, ...))
end

-- 第一次恢复协程
print("--- 第一次调用 resume ---")
resume_and_report(co)

-- 第二次恢复协程
print("--- 第二次调用 resume ---")
resume_and_report(co)

-- 第三次恢复协程
print("--- 第三次调用 resume ---")
resume_and_report(co)

