from __future__ import annotations

import pytest

from haifa_scheme import (
    EMPTY_LIST,
    Char,
    Pair,
    SchemeRuntimeError,
    Symbol,
    Vector,
    run_source,
    to_scheme_string,
)


def test_quote_empty_and_proper_list_values():
    empty_list, proper_list = run_source("'() '(1 2 x)")

    assert empty_list is EMPTY_LIST
    assert to_scheme_string(empty_list) == "()"
    assert isinstance(proper_list, Pair)
    assert to_scheme_string(proper_list) == "(1 2 x)"


def test_quote_nested_list_printing():
    [value] = run_source("'(1 (2 3) x)")

    assert to_scheme_string(value) == "(1 (2 3) x)"


def test_quote_dotted_pair_value():
    [value] = run_source("'(1 . 2)")

    assert isinstance(value, Pair)
    assert value.car == 1
    assert value.cdr == 2
    assert to_scheme_string(value) == "(1 . 2)"


def test_quote_multi_head_dotted_list_value():
    [value] = run_source("'(a b . c)")

    assert isinstance(value, Pair)
    assert to_scheme_string(value) == "(a b . c)"


def test_quote_nested_dotted_pair_value():
    first, second = run_source("'((1 . 2) . 3) '(a . (b . c))")

    assert to_scheme_string(first) == "((1 . 2) . 3)"
    assert to_scheme_string(second) == "(a b . c)"


def test_quote_character_value():
    [value] = run_source(r"'#\space")

    assert value == Char(" ")
    assert to_scheme_string(value) == r"#\space"


def test_quote_vector_value():
    [value] = run_source("'#(1 2 3)")

    assert value == Vector((1, 2, 3))
    assert to_scheme_string(value) == "#(1 2 3)"


def test_quote_vector_recursively_converts_items():
    [value] = run_source(r"'#(1 (2 . 3) #\space)")

    assert isinstance(value, Vector)
    assert value.items[0] == 1
    assert isinstance(value.items[1], Pair)
    assert value.items[2] == Char(" ")
    assert to_scheme_string(value) == r"#(1 (2 . 3) #\space)"


def test_list_builtin_returns_proper_scheme_list():
    [value] = run_source('(list 1 (+ 1 1) "three")')

    assert isinstance(value, Pair)
    assert to_scheme_string(value) == '(1 2 "three")'


def test_length_counts_proper_list_items():
    assert run_source("(length '(1 2 3)) (length '())") == [3, 0]


def test_reverse_returns_reversed_proper_list():
    [value] = run_source("(reverse '(1 2 3))")

    assert to_scheme_string(value) == "(3 2 1)"


def test_append_combines_lists_and_accepts_zero_arguments():
    combined, empty = run_source("(append '(1 2) '(3 4)) (append)")

    assert to_scheme_string(combined) == "(1 2 3 4)"
    assert empty is EMPTY_LIST


def test_append_uses_final_argument_as_tail():
    dotted, unchanged_tail = run_source("(append '(1 2) 3) (append 3)")

    assert to_scheme_string(dotted) == "(1 2 . 3)"
    assert unchanged_tail == 3


def test_length_and_reverse_reject_improper_lists():
    with pytest.raises(SchemeRuntimeError, match="length expected proper list"):
        run_source("(length '(1 . 2))")

    with pytest.raises(SchemeRuntimeError, match="reverse expected proper list"):
        run_source("(reverse '(1 . 2))")


def test_append_rejects_improper_non_final_lists():
    with pytest.raises(SchemeRuntimeError, match="append expected proper list"):
        run_source("(append '(1 . 2) '(3 4))")


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


def test_value_predicates_distinguish_scheme_value_types():
    assert run_source(
        r'''
        (number? 1)
        (number? 1.5)
        (number? #t)
        (integer? 1)
        (integer? 1.5)
        (integer? #f)
        (string? "name")
        (string? 'name)
        (symbol? 'name)
        (symbol? "name")
        (boolean? #t)
        (boolean? #f)
        (boolean? 0)
        (char? #\a)
        (char? "a")
        (vector? #(1 2))
        (vector? '(1 2))
        (procedure? +)
        (procedure? '(1 2))
        (list? #(1 2))
        '''
    ) == [
        True,
        True,
        False,
        True,
        False,
        False,
        True,
        False,
        True,
        False,
        True,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        False,
    ]


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


def test_to_scheme_string_formats_characters():
    assert to_scheme_string(Char("a")) == r"#\a"
    assert to_scheme_string(Char(" ")) == r"#\space"
    assert to_scheme_string(Char("\n")) == r"#\newline"
    assert to_scheme_string(Char("\t")) == r"#\tab"


def test_to_scheme_string_formats_vectors():
    assert to_scheme_string(Vector((1, Pair(2, 3), Char(" ")))) == r"#(1 (2 . 3) #\space)"
