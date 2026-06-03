from __future__ import annotations

from fractions import Fraction

import pytest

from haifa_scheme import SchemeRuntimeError, SchemeSyntaxError, parse_source, run_source
from haifa_scheme.values import Vector, to_scheme_string


def test_reader_parses_rational_literals():
    expressions = parse_source("1/2 -2/3")

    assert expressions == [Fraction(1, 2), Fraction(-2, 3)]


def test_reader_rejects_zero_denominator_rational_literals():
    with pytest.raises(SchemeSyntaxError, match="denominator cannot be zero"):
        parse_source("1/0")


def test_reader_parses_complex_literals():
    expressions = parse_source("1+2i 1-2i 2i +i -i")

    assert expressions == [
        complex(1, 2),
        complex(1, -2),
        complex(0, 2),
        complex(0, 1),
        complex(0, -1),
    ]


def test_to_scheme_string_formats_rational_and_complex_numbers():
    assert to_scheme_string(Fraction(1, 2)) == "1/2"
    assert to_scheme_string(Fraction(2, 1)) == "2"
    assert to_scheme_string(complex(1, 2)) == "1+2i"
    assert to_scheme_string(complex(1, -2)) == "1-2i"
    assert to_scheme_string(complex(0, 1)) == "+i"
    assert to_scheme_string(complex(0, -1)) == "-i"
    assert to_scheme_string(complex(0, 2)) == "+2i"


def test_to_scheme_string_formats_numbers_inside_vectors():
    assert to_scheme_string(Vector((Fraction(1, 2), complex(1, -2)))) == "#(1/2 1-2i)"


def test_exact_rational_arithmetic():
    half, sum_value, product, quotient = run_source(
        """
        (/ 1 2)
        (+ 1/2 1/3)
        (* 2/3 3/5)
        (/ 3/4 2)
        """
    )

    assert half == Fraction(1, 2)
    assert sum_value == Fraction(5, 6)
    assert product == Fraction(2, 5)
    assert quotient == Fraction(3, 8)
    assert to_scheme_string(sum_value) == "5/6"


def test_mixed_exact_and_inexact_arithmetic():
    float_sum, complex_sum, complex_product = run_source(
        """
        (+ 1/2 0.5)
        (+ 1/2 1+2i)
        (* 1+2i 3)
        """
    )

    assert float_sum == 1.0
    assert type(float_sum) is float
    assert complex_sum == complex(1.5, 2)
    assert type(complex_sum) is complex
    assert complex_product == complex(3, 6)


def test_numeric_comparison_supports_rationals_and_rejects_complex():
    assert run_source("(< 1/3 1/2 1) (> 3/2 1 1/2)") == [True, True]

    with pytest.raises(SchemeRuntimeError, match="< expected real number arguments"):
        run_source("(< 1+2i 3)")

    with pytest.raises(SchemeRuntimeError, match="> expected real number arguments"):
        run_source("(> 3 1+2i)")


def test_number_tower_predicates():
    assert run_source(
        """
        (number? 1/2)
        (number? 1+2i)
        (number? #t)
        (integer? 2/1)
        (integer? 3/2)
        (integer? 1.0)
        (exact? 1/2)
        (exact? 1.0)
        (inexact? 1+2i)
        (rational? 1/2)
        (rational? 1.5)
        (rational? 1+2i)
        (real? 1/2)
        (real? 1+0i)
        (real? 1+2i)
        (complex? 1/2)
        (complex? 1+2i)
        (complex? #f)
        """
    ) == [
        True,
        True,
        False,
        True,
        False,
        True,
        True,
        False,
        True,
        True,
        True,
        False,
        True,
        True,
        False,
        True,
        True,
        False,
    ]


def test_numeric_equality_and_eqv_distinguish_exactness():
    assert run_source(
        """
        (= 1 1.0)
        (eqv? 1 1)
        (eqv? 1 1.0)
        (eqv? 1/2 (/ 1 2))
        (eqv? 1+2i 1+2i)
        (eqv? 1.0 1+0i)
        (equal? '(1/2) (list (/ 1 2)))
        (equal? 1 1.0)
        """
    ) == [True, True, False, True, True, False, True, False]


def test_division_by_zero_covers_exact_rational_zero():
    with pytest.raises(SchemeRuntimeError, match="/ division by zero"):
        run_source("(/ 1 0)")

    with pytest.raises(SchemeRuntimeError, match="/ division by zero"):
        run_source("(/ 1 0/2)")
