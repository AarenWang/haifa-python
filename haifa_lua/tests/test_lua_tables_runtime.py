from haifa_lua import run_source


def test_table_field_assignment_and_length():
    src = """
    local t = {10, 20, foo = "bar"}
    t.bar = t.foo .. "!"
    t[3] = 30
    t[3] = nil
    t[3] = 99
    return t[1], t.foo, t.bar, t[3], #t
    """
    result = run_source(src)
    assert result == [10, "bar", "bar!", 99, 3]


def test_table_constructor_spread_and_scalar_calls():
    src = """
    local function produce()
        return 7, 8, 9
    end

    local t = {1, produce()}
    local v = {produce(), 100}
    return #t, t[1], t[2], t[3], t[4], #v, v[1], v[2]
    """
    result = run_source(src)
    assert result == [4, 1, 7, 8, 9, 2, 7, 100]


def test_table_vararg_collect_and_length_updates():
    src = """
    local function collect(...)
        local result = {}
        local args = {...}
        for i = 1, #args do
            result[#result + 1] = args[i]
        end
        return result[1], result[2], result[3], #result, #args
    end

    return collect("a", "b", "c")
    """
    result = run_source(src)
    assert result == ["a", "b", "c", 3, 3]
