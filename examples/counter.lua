function make_counter()
    local x = 0
    return function()
        x = x + 1
        return x
    end
end

local c = make_counter()
return c(), c(), c()
