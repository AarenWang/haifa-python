from __future__ import annotations

import pytest

from haifa_jq.jq_runtime import JQRuntimeError, run_filter, run_filter_many, run_filter_stream


def test_path_function_returns_matching_paths():
    data = {"foo": [1, {"bar": 2}], "baz": 0}
    result = run_filter("path(.foo[])", data)
    assert result == [["foo", 0], ["foo", 1]]


def test_paths_without_argument_lists_all_paths():
    data = {"a": {"b": 1}, "c": [10]}
    result = run_filter("paths()", data)
    assert result == [[], ["a"], ["a", "b"], ["c"], ["c", 0]]


def test_setpath_updates_structure():
    data = {"foo": [0, 1]}
    result = run_filter('setpath(["foo", 1]; 42)', data)
    assert result == [{"foo": [0, 42]}]


def test_del_removes_target_path():
    data = {"foo": [1, 2], "bar": 3}
    result = run_filter('del(.foo[0])', data)
    assert result == [{"foo": [2], "bar": 3}]


def test_walk_applies_filter_to_matching_values():
    data = {"foo": [1, 2], "bar": {"baz": 1}}
    expression = "walk(if . == 1 then 42 else . end)"
    result = run_filter(expression, data)
    assert result == [{"foo": [42, 2], "bar": {"baz": 42}}]


def test_input_reads_from_stream():
    result = run_filter_many("input()", [1, 2, 3])
    assert result == [2, None]


def test_inputs_emits_remaining_values():
    result = run_filter_many("inputs()", [1, 2, 3])
    assert result == [2, 3]


def test_halt_stops_processing():
    result = list(run_filter_stream("halt()", [1, 2, 3]))
    assert result == []


def test_halt_error_raises_runtime_error():
    with pytest.raises(JQRuntimeError):
        run_filter("halt_error(\"boom\")", 1)


def test_label_break_terminates_label_block():
    result = run_filter("label $stop | (.[] | if . == 2 then break $stop else . end)", [1, 2, 3])
    assert result == [1]
