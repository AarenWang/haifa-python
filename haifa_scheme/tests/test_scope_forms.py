from __future__ import annotations

import pytest

from haifa_scheme import SchemeRuntimeError, run_source


def test_lexical_closure_captures_outer_binding():
    source = """
    (define add-two
      (let ((x 2))
        (lambda (y) (+ x y))))
    (add-two 5)
    """

    assert run_source(source) == [None, 7]


def test_let_shadows_outer_binding_without_mutating_it():
    source = """
    (define x 10)
    (let ((x 1)
          (y 2))
      (+ x y))
    x
    """

    assert run_source(source) == [None, 3, 10]


def test_set_updates_nearest_binding():
    source = """
    (define x 1)
    ((lambda (x)
       (set! x 5)
       x)
     2)
    x
    """

    assert run_source(source) == [None, 5, 1]


def test_set_updates_captured_outer_binding():
    source = """
    (define make-counter
      (lambda ()
        (let ((x 0))
          (lambda ()
            (set! x (+ x 1))
            x))))
    (define counter (make-counter))
    (counter)
    (counter)
    """

    assert run_source(source) == [None, None, 1, 2]


def test_set_rejects_unbound_symbol():
    with pytest.raises(SchemeRuntimeError, match="unbound symbol: missing"):
        run_source("(set! missing 1)")


def test_let_initializers_use_outer_environment_but_let_star_is_sequential():
    source = """
    (define x 10)
    (let ((x 1)
          (y x))
      y)
    (let* ((x 1)
           (y x))
      y)
    """

    assert run_source(source) == [None, 10, 1]


def test_letrec_supports_recursive_function():
    source = """
    (letrec ((fact (lambda (n)
                     (if (= n 0)
                         1
                         (* n (fact (- n 1)))))))
      (fact 5))
    """

    assert run_source(source) == [120]


def test_letrec_supports_mutual_recursion():
    source = """
    (letrec ((even? (lambda (n)
                      (if (= n 0)
                          #t
                          (odd? (- n 1)))))
             (odd? (lambda (n)
                     (if (= n 0)
                         #f
                         (even? (- n 1))))))
      (even? 10))
    """

    assert run_source(source) == [True]


def test_letrec_rejects_read_before_initialization():
    with pytest.raises(SchemeRuntimeError, match="read before initialization"):
        run_source("(letrec ((x y) (y 1)) x)")


def test_and_short_circuits_and_returns_last_value():
    assert run_source('(and) (and 1 "ok") (and #f missing)') == [True, "ok", False]


def test_or_short_circuits_and_returns_first_truthy_value():
    assert run_source('(or) (or #f 0 missing) (or "value" missing)') == [False, 0, "value"]


def test_cond_clauses_else_and_bodyless_test():
    source = """
    (cond ((= 1 2) 10)
          ((= 2 2) 20)
          (else 30))
    (cond ((= 1 2) 10)
          (else 30))
    (cond ((+ 1 2)))
    """

    assert run_source(source) == [20, 30, 3]


def test_cond_rejects_else_before_last_clause():
    with pytest.raises(SchemeRuntimeError, match="else clause must be last"):
        run_source("(cond (else 1) (#t 2))")
