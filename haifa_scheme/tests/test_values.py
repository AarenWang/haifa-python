from __future__ import annotations

import pytest

from haifa_scheme import EMPTY_LIST, Pair, SchemeRuntimeError, Symbol, run_source, to_scheme_string


def test_quote_empty_and_proper_list_values():
    empty_list, proper_list = run_source("'() '(1 2 x)")

    assert empty_list is EMPTY_LIST
    assert to_scheme_string(empty_list) == "()"
    assert isinstance(proper_list, Pair)
    assert to_scheme_string(proper_list) == "(1 2 x)"


def test_quote_nested_list_printing():
    [value] = run_source("'(1 (2 3) x)")

    assert to_scheme_string(value) == "(1 (2 3) x)"


def test_list_builtin_returns_proper_scheme_list():
    [value] = run_source('(list 1 (+ 1 1) "three")')

    assert isinstance(value, Pair)
    assert to_scheme_string(value) == '(1 2 "three")'


def test_cons_car_cdr_and_runtime_dotted_pair():
    dotted, car_value, cdr_value = run_source(
        """
        (cons 1 2)
        (car (cons 1 2))
        (cdr (cons 1 2))
        """
    )

    assert isinstance(dotted, Pair)
    assert to_scheme_string(dotted) == "(1 . 2)"
    assert car_value == 1
    assert cdr_value == 2


def test_car_and_cdr_reject_non_pairs():
    with pytest.raises(SchemeRuntimeError, match="car expected pair argument"):
        run_source("(car '())")

    with pytest.raises(SchemeRuntimeError, match="cdr expected pair argument"):
        run_source("(cdr 1)")


def test_list_predicates():
    assert run_source(
        """
        (null? '())
        (pair? '(1 2))
        (pair? '())
        (list? '(1 2))
        (list? '())
        (list? (cons 1 2))
        """
    ) == [True, True, False, True, True, False]


def test_empty_list_is_truthy():
    assert run_source("(if '() 1 2)") == [1]


def test_eq_and_equal_predicates():
    assert run_source(
        """
        (eq? 'x 'x)
        (eq? '(1 2) '(1 2))
        (equal? #t 1)
        (equal? '(1 (2 3)) '(1 (2 3)))
        (equal? (cons 1 2) (cons 1 2))
        (equal? '(1 2) (cons 1 2))
        """
    ) == [True, False, False, True, True, False]


def test_to_scheme_string_formats_atoms_and_strings():
    assert to_scheme_string(True) == "#t"
    assert to_scheme_string(False) == "#f"
    assert to_scheme_string(Symbol("name")) == "name"
    assert to_scheme_string('hello\n"scheme"') == r'"hello\n\"scheme\""'
