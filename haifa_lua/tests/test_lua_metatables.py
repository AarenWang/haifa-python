import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from haifa_lua import run_source


def test_method_definition_and_index_function():
    src = """
    local Account = { balance = 10 }

    function Account:deposit(amount)
        self.balance = self.balance + amount
        return self
    end

    function Account:get_balance()
        return self.balance
    end

    local dynamic = {}
    function dynamic.__index(tbl, key)
        if key == "bump" then
            return function(self, value)
                self.balance = self.balance + value * 2
                return self.balance
            end
        end
        return Account[key]
    end

    local user = { balance = 0 }
    setmetatable(user, dynamic)

    user:deposit(5)
    local after_dynamic = user:bump(3)

    return user.balance, after_dynamic, Account:get_balance(), getmetatable(user) == dynamic
    """
    result = run_source(src)
    assert result == [11, 11, 10, True]


def test_prototype_chain_and_arithmetic_metamethods():
    src = """
    local Vec = {}
    Vec.__index = Vec

    function Vec:new(x)
        local instance = { x = x }
        setmetatable(instance, self)
        return instance
    end

    function Vec:__add(other)
        return Vec:new(self.x + other.x)
    end

    function Vec:__eq(other)
        return self.x == other.x
    end

    function Vec:__lt(other)
        return self.x < other.x
    end

    function Vec:magnitude()
        return self.x
    end

    local Child = {}
    setmetatable(Child, { __index = Vec })

    local a = Child:new(3)
    local b = Child:new(7)
    local c = a + b
    local same = c == Child:new(10)
    local diff = c == Child:new(8)
    local lt = a < b
    local gt = b > a

    return c:magnitude(), same, diff, lt, gt, getmetatable(a) == Child
    """
    result = run_source(src)
    assert result == [10, True, False, True, True, True]


def test_newindex_and_raw_access_helpers():
    src = """
    local record = {}

    local base = {}
    setmetatable(base, {
        __newindex = function(tbl, key, value)
            record[key] = value .. "!"
        end
    })

    local proxy = {}
    setmetatable(proxy, { __newindex = base })

    proxy.foo = "bar"
    rawset(proxy, "foo", "raw")
    rawset(proxy, "direct", 42)

    local eq_meta = {
        __eq = function(left, right)
            return true
        end
    }
    local left = {}
    local right = {}
    setmetatable(left, eq_meta)
    setmetatable(right, eq_meta)
    local eq_value = (left == right)
    local raw_eq = rawequal(left, right)

    return record.foo, rawget(proxy, "foo"), rawget(proxy, "direct"), eq_value, raw_eq
    """
    result = run_source(src)
    assert result == ["bar!", "raw", 42, True, False]
