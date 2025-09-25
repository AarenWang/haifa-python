local co
co = coroutine.create(function(value)
    local thread, is_main = coroutine.running()
    print("inside running == co?", thread == co, "main?", is_main)
    print("inside status:", coroutine.status(co))
    print("inside yieldable:", coroutine.isyieldable())
    local resume_arg = coroutine.yield(value + 1, value + 2)
    print("resumed with:", resume_arg)
    return "done"
end)

print("initial status:", coroutine.status(co))
print("main yieldable:", coroutine.isyieldable())
local ok, first, second = coroutine.resume(co, 5)
print("after first resume:", ok, first, second, coroutine.status(co))
local ok2, result = coroutine.resume(co, "resume")
print("after second resume:", ok2, result, coroutine.status(co))

local wrapped = coroutine.wrap(function(name)
    local greeting = coroutine.yield("hello", name)
    return "goodbye", greeting
end)

local hello, name = wrapped("wrap")
print("wrap yield:", hello, name)
local farewell, echoed = wrapped("again")
print("wrap finish:", farewell, echoed)

local ok_wrap, err_message = pcall(function()
    local failing = coroutine.wrap(function()
        error("wrap failure")
    end)
    failing()
end)
print("wrap error ok:", ok_wrap)
if not ok_wrap then
    print("wrap error message:", err_message)
end
