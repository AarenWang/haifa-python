from __future__ import annotations

import pytest

from haifa_scheme import SchemeRuntimeError, Symbol, run_source


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


def test_named_let_supports_recursive_loop():
    source = """
    (let fact ((n 5)
               (acc 1))
      (if (= n 0)
          acc
          (fact (- n 1) (* acc n))))
    """

    assert run_source(source) == [120]


def test_named_let_initializers_use_outer_environment():
    source = """
    (define x 10)
    (let loop ((x 1)
               (y x))
      y)
    """

    assert run_source(source) == [None, 10]


def test_named_let_tail_recursive_loop_uses_trampoline():
    source = """
    (let loop ((n 2000)
               (total 0))
      (if (= n 0)
          total
          (loop (- n 1) (+ total n))))
    """

    assert run_source(source) == [2001000]


def test_named_let_rejects_malformed_bindings():
    with pytest.raises(SchemeRuntimeError, match="named let expected name, bindings, and body"):
        run_source("(let loop ((x 1)))")
    with pytest.raises(SchemeRuntimeError, match="named let duplicate binding: x"):
        run_source("(let loop ((x 1) (x 2)) x)")


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


def test_case_matches_number_symbol_string_and_list_datums():
    source = """
    (case 2
      ((1) 'one)
      ((2 3) 'small)
      (else 'other))
    (case 'beta
      ((alpha) 1)
      ((beta gamma) 2))
    (case "ok"
      (("no") 'bad)
      (("ok" "yes") 'good))
    (case '(a b)
      (((x y) (a b)) 'list-match)
      (else 'other))
    """

    assert run_source(source) == [
        Symbol("small"),
        2,
        Symbol("good"),
        Symbol("list-match"),
    ]


def test_case_else_clause_and_no_match_return_void():
    matched, missing = run_source(
        """
        (case 'z
          ((a b) 1)
          (else 2))
        (case 'z
          ((a b) 1)
          ((c d) 2))
        """
    )

    assert matched == 2
    assert missing is None


def test_case_key_expression_is_evaluated_once():
    source = """
    (define x 0)
    (case (begin (set! x (+ x 1)) x)
      ((1) 'once)
      ((2) 'twice))
    x
    """

    assert run_source(source) == [None, Symbol("once"), 1]


def test_case_rejects_else_before_last_clause():
    with pytest.raises(SchemeRuntimeError, match="case else clause must be last"):
        run_source("(case 1 (else 1) ((1) 2))")


def test_case_rejects_empty_clause_bodies():
    with pytest.raises(SchemeRuntimeError, match="case clause expected a body"):
        run_source("(case 1 ((1)))")
    with pytest.raises(SchemeRuntimeError, match="case else clause expected a body"):
        run_source("(case 1 (else))")


def test_case_rejects_malformed_datum_list():
    with pytest.raises(SchemeRuntimeError, match="case clause expected a datum list"):
        run_source("(case 1 (1 'bad))")
    with pytest.raises(SchemeRuntimeError, match="case clause expected a datum list"):
        run_source("(case 1 ((1 . 2) 'bad))")


def test_do_sums_loop_values():
    source = """
    (do ((i 0 (+ i 1))
         (total 0 (+ total i)))
        ((= i 5) total))
    """

    assert run_source(source) == [10]


def test_do_result_expressions_return_last_value():
    source = """
    (do ((i 0 (+ i 1)))
        ((= i 3)
         (define done 'ignored)
         (+ i 10)))
    """

    assert run_source(source) == [13]


def test_do_without_result_expression_returns_void():
    result = run_source("(do ((i 0 (+ i 1))) ((= i 2)))")

    assert result == [None]


def test_do_omitted_step_keeps_variable_value():
    source = """
    (do ((x 7)
         (i 0 (+ i 1)))
        ((= i 3) x))
    """

    assert run_source(source) == [7]


def test_do_updates_loop_variables_simultaneously():
    source = """
    (do ((x 0 y)
         (y 1 (+ x y))
         (i 0 (+ i 1)))
        ((= i 6) x))
    """

    assert run_source(source) == [8]


def test_do_body_side_effects_run_before_steps():
    source = """
    (define seen 0)
    (do ((i 0 (+ i 1)))
        ((= i 4) seen)
      (set! seen (+ seen i)))
    """

    assert run_source(source) == [None, 6]


def test_do_initializers_use_outer_environment():
    source = """
    (define x 10)
    (do ((x 1 (+ x 1))
         (y x))
        ((= x 2) y))
    """

    assert run_source(source) == [None, 10]


def test_do_rejects_malformed_forms():
    with pytest.raises(SchemeRuntimeError, match="do expected variable specs"):
        run_source("(do)")
    with pytest.raises(SchemeRuntimeError, match="do variable specs must be a list"):
        run_source("(do x (#t))")
    with pytest.raises(SchemeRuntimeError, match="do variable specs must be .*lists"):
        run_source("(do ((x)) (#t))")
    with pytest.raises(SchemeRuntimeError, match="do variable names must be symbols"):
        run_source("(do ((1 2)) (#t))")
    with pytest.raises(SchemeRuntimeError, match="do duplicate variable: x"):
        run_source("(do ((x 1) (x 2)) (#t))")
    with pytest.raises(SchemeRuntimeError, match="do termination clause must be a non-empty list"):
        run_source("(do ((x 1)) #t)")
    with pytest.raises(SchemeRuntimeError, match="do termination clause must be a non-empty list"):
        run_source("(do ((x 1)) ())")
