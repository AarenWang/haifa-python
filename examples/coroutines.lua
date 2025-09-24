function ticker(label, count)
    for i = 1, count do
        local resume_value = coroutine.yield(label .. " tick", i)
        if resume_value then
            label = label .. "+" .. tostring(resume_value)
        end
    end
    return label .. " done", count
end

local blue = coroutine.create(ticker)
local green = coroutine.create(ticker)

print(coroutine.resume(blue, "blue", 2))
print(coroutine.resume(green, "green", 3))
print(coroutine.resume(blue, "B"))
print(coroutine.resume(blue))
print(coroutine.resume(green, "G"))
print(coroutine.resume(green))
print(coroutine.resume(green))
