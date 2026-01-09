local values = {3, 1, 4}

table.insert(values, 2, 2)
table.sort(values)
print("sorted", table.concat(values, ","))

local removed = table.remove(values, 2)
print("removed", removed)
print("after", table.concat(values, ","))

local packed = table.pack("a", "b", "c")
print("pack", packed.n, packed[1], packed[2], packed[3])
