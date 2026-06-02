from __future__ import annotations

import pytest

from haifa_scheme import EMPTY_LIST, Pair, SchemeRuntimeError, Symbol, run_source, to_scheme_string


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
    symbol, quoted_list = run_source("'answer '(1 2 x)")

    assert symbol == Symbol("answer")
    assert to_scheme_string(quoted_list) == "(1 2 x)"
    assert isinstance(quoted_list, Pair)


def test_apply_calls_builtin_with_list_arguments():
    assert run_source("(apply + '(1 2 3))") == [6]


def test_apply_appends_leading_arguments_to_final_list():
    assert run_source("(apply + 1 2 '(3 4))") == [10]


def test_apply_calls_user_procedure():
    source = """
    (define (combine a b c)
      (+ (* a 100) (* b 10) c))
    (apply combine '(4 5 6))
    """

    assert run_source(source) == [None, 456]


def test_apply_rejects_missing_argument_list():
    with pytest.raises(SchemeRuntimeError, match="apply expected at least 2 argument"):
        run_source("(apply +)")


def test_apply_rejects_improper_final_list():
    with pytest.raises(SchemeRuntimeError, match="apply expected final argument"):
        run_source("(apply + '(1 . 2))")


def test_procedure_predicate_identifies_builtins_and_user_procedures():
    source = """
    (procedure? +)
    (procedure? (lambda (x) x))
    (procedure? 1)
    (procedure? '(1 2))
    """

    assert run_source(source) == [True, True, False, False]


def test_map_calls_lambda_for_each_list_item():
    [value] = run_source("(map (lambda (x) (* x 2)) '(1 2 3))")

    assert to_scheme_string(value) == "(2 4 6)"


def test_map_calls_builtin_procedure():
    [value] = run_source("(map + '(1 2) '(10 20))")

    assert to_scheme_string(value) == "(11 22)"


def test_map_supports_multiple_lists():
    source = """
    (map (lambda (x y z) (+ x (* y 10) (* z 100)))
         '(1 2)
         '(3 4)
         '(5 6))
    """

    [value] = run_source(source)

    assert to_scheme_string(value) == "(531 642)"


def test_map_rejects_improper_list_argument():
    with pytest.raises(SchemeRuntimeError, match="map expected proper list"):
        run_source("(map + '(1 . 2))")


def test_map_rejects_non_procedure_even_for_empty_list():
    with pytest.raises(SchemeRuntimeError, match="map expected procedure"):
        run_source("(map 1 '())")


def test_map_rejects_length_mismatch():
    with pytest.raises(SchemeRuntimeError, match="map expected list arguments with equal length"):
        run_source("(map + '(1 2) '(10))")


def test_for_each_calls_procedure_for_side_effects_and_returns_void():
    source = """
    (define total 0)
    (for-each (lambda (x y)
                (set! total (+ total x y)))
              '(1 2)
              '(10 20))
    total
    """

    define_result, for_each_result, total = run_source(source)

    assert define_result is None
    assert for_each_result is None
    assert to_scheme_string(for_each_result) == "#<void>"
    assert total == 33


def test_for_each_rejects_improper_list_argument():
    with pytest.raises(SchemeRuntimeError, match="for-each expected proper list"):
        run_source("(for-each + '(1 . 2))")


def test_for_each_rejects_non_procedure_even_for_empty_list():
    with pytest.raises(SchemeRuntimeError, match="for-each expected procedure"):
        run_source("(for-each 1 '())")


def test_for_each_rejects_length_mismatch():
    with pytest.raises(
        SchemeRuntimeError, match="for-each expected list arguments with equal length"
    ):
        run_source("(for-each + '(1 2) '(10))")


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
