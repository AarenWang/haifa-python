from __future__ import annotations

import re

import pytest

from haifa_scheme import Char, SchemeSyntaxError, Symbol, Vector, parse_source
from haifa_scheme.reader import DottedList


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


def test_quasiquote_shorthand_expands_to_quasiquote_form():
    expressions = parse_source("`x")

    assert expressions == [[Symbol("quasiquote"), Symbol("x")]]


def test_quasiquote_supports_unquote_and_unquote_splicing():
    expressions = parse_source("`(a ,b ,@c)")

    assert expressions == [
        [
            Symbol("quasiquote"),
            [
                Symbol("a"),
                [Symbol("unquote"), Symbol("b")],
                [Symbol("unquote-splicing"), Symbol("c")],
            ],
        ]
    ]


def test_parse_character_literals():
    expressions = parse_source(r"#\a #\space #\newline #\tab")

    assert expressions == [Char("a"), Char(" "), Char("\n"), Char("\t")]


def test_parse_vector_literal():
    expressions = parse_source("#(1 2 3)")

    assert expressions == [Vector((1, 2, 3))]


def test_parse_nested_vector_literal():
    expressions = parse_source(r"#(1 (2 . 3) #\space)")

    assert expressions == [Vector((1, DottedList([2], 3), Char(" ")))]


def test_parse_two_element_dotted_list():
    expressions = parse_source("(1 . 2)")

    assert expressions == [DottedList([1], 2)]


def test_parse_multi_head_dotted_list():
    expressions = parse_source("(a b . c)")

    assert expressions == [DottedList([Symbol("a"), Symbol("b")], Symbol("c"))]


def test_quote_shorthand_supports_dotted_list():
    expressions = parse_source("'(1 . 2)")

    assert expressions == [[Symbol("quote"), DottedList([1], 2)]]


def test_dot_inside_symbol_is_not_dotted_syntax():
    expressions = parse_source("a.b")

    assert expressions == [Symbol("a.b")]


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
        ("`", "quasiquote"),
        (",", "unquote"),
        (",@", "unquote-splicing"),
    ],
)
def test_syntax_errors(source: str, message: str):
    with pytest.raises(SchemeSyntaxError, match=re.escape(message)):
        parse_source(source)


@pytest.mark.parametrize(
    "source",
    [
        "(. 1)",
        "(1 .)",
        "(1 . 2 3)",
        "(1 . 2 . 3)",
    ],
)
def test_malformed_dotted_list_errors(source: str):
    with pytest.raises(SchemeSyntaxError, match="dotted list"):
        parse_source(source)


def test_unclosed_dotted_list_keeps_unclosed_paren_error():
    with pytest.raises(SchemeSyntaxError, match="unclosed '\\('"):
        parse_source("(1 . 2")


def test_unclosed_vector_literal_errors():
    with pytest.raises(SchemeSyntaxError, match="unclosed vector literal"):
        parse_source("#(1 2")


@pytest.mark.parametrize("source", ["#\\", r"#\ab", r"#\unknown"])
def test_malformed_character_literal_errors(source: str):
    with pytest.raises(SchemeSyntaxError, match="malformed character literal"):
        parse_source(source)
