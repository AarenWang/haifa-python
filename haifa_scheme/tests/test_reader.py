from __future__ import annotations

import re

import pytest

from haifa_scheme import Char, SchemeSyntaxError, Symbol, Vector, parse_source
from haifa_scheme.reader import DottedList, LocatedDatum, SourceSpan, parse_source_with_locations


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


def test_parse_source_with_locations_tracks_atoms():
    expressions = parse_source_with_locations('42 hello "world"', source_name="atoms.scm")

    assert expressions == [
        LocatedDatum(42, SourceSpan("atoms.scm", 1, 1, 1, 3)),
        LocatedDatum(Symbol("hello"), SourceSpan("atoms.scm", 1, 4, 1, 9)),
        LocatedDatum("world", SourceSpan("atoms.scm", 1, 10, 1, 17)),
    ]


def test_parse_source_with_locations_tracks_nested_lists():
    expressions = parse_source_with_locations("(define square (lambda (x) (* x x)))")

    assert len(expressions) == 1
    expression = expressions[0]
    assert expression.span == SourceSpan("<input>", 1, 1, 1, 37)
    assert isinstance(expression.value, list)

    define_form = expression.value
    assert define_form[0] == LocatedDatum(Symbol("define"), SourceSpan("<input>", 1, 2, 1, 8))
    assert define_form[1] == LocatedDatum(Symbol("square"), SourceSpan("<input>", 1, 9, 1, 15))

    lambda_expression = define_form[2]
    assert lambda_expression.span == SourceSpan("<input>", 1, 16, 1, 36)
    assert isinstance(lambda_expression.value, list)
    assert lambda_expression.value[0] == LocatedDatum(
        Symbol("lambda"), SourceSpan("<input>", 1, 17, 1, 23)
    )

    parameters = lambda_expression.value[1]
    assert parameters.span == SourceSpan("<input>", 1, 24, 1, 27)
    assert parameters.value == [LocatedDatum(Symbol("x"), SourceSpan("<input>", 1, 25, 1, 26))]


def test_parse_source_with_locations_tracks_quote_shorthand():
    expressions = parse_source_with_locations("'(1 . answer)")

    assert len(expressions) == 1
    quoted_expression = expressions[0]
    assert quoted_expression.span == SourceSpan("<input>", 1, 1, 1, 14)
    assert isinstance(quoted_expression.value, list)
    assert quoted_expression.value[0] == LocatedDatum(Symbol("quote"), SourceSpan("<input>", 1, 1, 1, 2))

    dotted = quoted_expression.value[1]
    assert isinstance(dotted.value, DottedList)
    assert dotted.span == SourceSpan("<input>", 1, 2, 1, 14)
    assert dotted.value.items == [LocatedDatum(1, SourceSpan("<input>", 1, 3, 1, 4))]
    assert dotted.value.tail == LocatedDatum(Symbol("answer"), SourceSpan("<input>", 1, 7, 1, 13))


def test_parse_source_with_locations_tracks_vectors_and_multiline_spans():
    expressions = parse_source_with_locations("\n  #(1\n     (2 3))", source_name="vectors.scm")

    assert len(expressions) == 1
    vector_expression = expressions[0]
    assert vector_expression.span == SourceSpan("vectors.scm", 2, 3, 3, 12)
    assert isinstance(vector_expression.value, Vector)
    assert vector_expression.value.items[0] == LocatedDatum(1, SourceSpan("vectors.scm", 2, 5, 2, 6))

    nested_list = vector_expression.value.items[1]
    assert nested_list.span == SourceSpan("vectors.scm", 3, 6, 3, 11)
    assert nested_list.value == [
        LocatedDatum(2, SourceSpan("vectors.scm", 3, 7, 3, 8)),
        LocatedDatum(3, SourceSpan("vectors.scm", 3, 9, 3, 10)),
    ]


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


def test_parse_source_with_locations_keeps_syntax_errors_clear():
    with pytest.raises(SchemeSyntaxError, match="unclosed '\\('"):
        parse_source_with_locations("(define x 1")


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
