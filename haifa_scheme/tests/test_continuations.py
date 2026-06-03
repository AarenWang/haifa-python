from __future__ import annotations

import pytest

from haifa_scheme import SchemeRuntimeError, run_source


def test_call_cc_escapes_to_current_continuation():
    assert run_source("(+ 1 (call/cc (lambda (k) (k 41) 99)))") == [42]


def test_call_cc_returns_lambda_result_when_continuation_is_not_called():
    assert run_source("(call/cc (lambda (k) 7))") == [7]


def test_call_cc_alias_is_available():
    source = "(call-with-current-continuation (lambda (k) (k 5)))"

    assert run_source(source) == [5]


def test_continuation_is_a_procedure():
    assert run_source("(call/cc (lambda (k) (procedure? k)))") == [True]


def test_continuation_rejects_wrong_argument_count():
    with pytest.raises(SchemeRuntimeError, match="continuation expected 1 argument"):
        run_source("(call/cc (lambda (k) (k)))")

    with pytest.raises(SchemeRuntimeError, match="continuation expected 1 argument"):
        run_source("(call/cc (lambda (k) (k 1 2)))")


def test_call_cc_argument_must_be_a_procedure():
    with pytest.raises(SchemeRuntimeError, match="call/cc expected procedure argument"):
        run_source("(call/cc 1)")


def test_continuation_escapes_nested_begin_sequence():
    source = """
    (+ 1
       (call/cc
        (lambda (k)
          (begin
            (begin (k 41) 99)
            100))))
    """

    assert run_source(source) == [42]


def test_continuation_escapes_through_map_callback():
    source = """
    (+ 10
       (call/cc
        (lambda (k)
          (map (lambda (x)
                 (if (= x 2)
                     (k x)
                     x))
               '(1 2 3))
          99)))
    """

    assert run_source(source) == [12]


def test_continuation_escapes_through_for_each_callback():
    source = """
    (define seen 0)
    (call/cc
     (lambda (k)
       (for-each (lambda (x)
                   (if (= x 2)
                       (k seen)
                       (set! seen (+ seen x))))
                 '(1 2 3))
       99))
    seen
    """

    assert run_source(source) == [None, 1, 1]


def test_saved_continuation_cannot_be_reentered_after_dynamic_extent():
    source = """
    (define saved #f)
    (call/cc
     (lambda (k)
       (set! saved k)
       1))
    (saved 2)
    """

    with pytest.raises(SchemeRuntimeError, match="continuation has escaped"):
        run_source(source)
