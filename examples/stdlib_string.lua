local text = "hello world"

print("len", string.len(text))
print("sub", string.sub(text, 1, 5))

local start_pos, end_pos = string.find(text, "world")
print("find", start_pos, end_pos)

local replaced, count = string.gsub(text, "l", "L")
print("gsub", replaced, count)
