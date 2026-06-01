from __future__ import annotations

import pytest

from haifa_scheme import SchemeRuntimeError, Symbol, run_source


def test_arithmetic():
    assert run_source("(+ 1 2 3)") == [6]
    assert run_source("(- 10 3 2)") == [5]
    assert run_source("(* 2 3 4)") == [24]
    assert run_source("(/ 20 2 2)") == [5]
    assert run_source("(= 4 (+ 2 2)) (< 1 2 3) (> 3 2 1)") == [True, True, True]


def test_global_define_and_symbol_lookup():
    source = """
    (define x 10)
    (define y (+ x 5))
    y
    """

    assert run_source(source) == [None, None, 15]


def test_lambda_call():
    source = """
    (define square (lambda (x) (* x x)))
    (square 9)
    """

    assert run_source(source) == [None, 81]


def test_lambda_with_multiple_body_expressions_returns_last_value():
    source = """
    ((lambda (x)
       (define doubled (* x 2))
       (+ doubled 1))
     5)
    """

    assert run_source(source) == [11]


def test_begin_returns_last_expression():
    source = """
    (begin
      (define x 2)
      (define y 3)
      (+ x y))
    """

    assert run_source(source) == [5]


def test_function_define_shorthand_and_recursive_factorial():
    source = """
    (define (fact n)
      (if (= n 0)
          1
          (* n (fact (- n 1)))))
    (fact 5)
    """

    assert run_source(source) == [None, 120]


def test_quote_special_form_returns_expression_without_evaluating_it():
    assert run_source("'answer '(1 2 x)") == [Symbol("answer"), [1, 2, Symbol("x")]]


def test_only_false_is_falsey():
    source = """
    (if #f 1 2)
    (if 0 1 2)
    (if "text" 1 2)
    """

    assert run_source(source) == [2, 1, 1]


def test_argument_count_error_is_clear():
    with pytest.raises(SchemeRuntimeError, match="procedure expected 2 argument"):
        run_source("((lambda (x y) (+ x y)) 1)")


def test_unbound_symbol_error_is_clear():
    with pytest.raises(SchemeRuntimeError, match="unbound symbol: missing"):
        run_source("missing")


def test_division_by_zero_error_is_clear():
    with pytest.raises(SchemeRuntimeError, match="/ division by zero"):
        run_source("(/ 4 0)")
