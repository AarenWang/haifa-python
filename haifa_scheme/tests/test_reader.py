from __future__ import annotations

import re

import pytest

from haifa_scheme import SchemeSyntaxError, Symbol, parse_source


def test_parse_atoms():
    expressions = parse_source('42 -7 3.5 #t #f hello "world"')

    assert expressions == [42, -7, 3.5, True, False, Symbol("hello"), "world"]
    assert isinstance(expressions[5], Symbol)
    assert type(expressions[6]) is str


def test_parse_nested_lists():
    expressions = parse_source("(define square (lambda (x) (* x x)))")

    assert expressions == [
        [
            Symbol("define"),
            Symbol("square"),
            [Symbol("lambda"), [Symbol("x")], [Symbol("*"), Symbol("x"), Symbol("x")]],
        ]
    ]


def test_parse_multiple_top_level_expressions():
    expressions = parse_source("(define x 10) (+ x 5)")

    assert expressions == [[Symbol("define"), Symbol("x"), 10], [Symbol("+"), Symbol("x"), 5]]


def test_quote_shorthand_expands_to_quote_form():
    expressions = parse_source("'answer '(1 2 nested)")

    assert expressions == [
        [Symbol("quote"), Symbol("answer")],
        [Symbol("quote"), [1, 2, Symbol("nested")]],
    ]


def test_comments_are_ignored():
    expressions = parse_source(
        """
        ; whole line comment
        (define x 1) ; trailing comment
        (+ x 2)
        """
    )

    assert expressions == [[Symbol("define"), Symbol("x"), 1], [Symbol("+"), Symbol("x"), 2]]


def test_string_escapes():
    expressions = parse_source(r'"hello\n\"scheme\""')

    assert expressions == ['hello\n"scheme"']


@pytest.mark.parametrize(
    "source, message",
    [
        ("(define x 1", "unclosed '('"),
        ("define x 1)", "unexpected ')'"),
        ('"unterminated', "unterminated string"),
        ("'", "quote"),
    ],
)
def test_syntax_errors(source: str, message: str):
    with pytest.raises(SchemeSyntaxError, match=re.escape(message)):
        parse_source(source)
