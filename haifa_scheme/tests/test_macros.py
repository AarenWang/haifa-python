from __future__ import annotations

import pytest

from haifa_scheme import SchemeRuntimeError, run_source, to_scheme_string


def test_define_syntax_when_expands_before_evaluation():
    source = """
    (define-syntax when
      (syntax-rules ()
        ((when test expr) (if test expr))))
    (define x 0)
    (when #t (set! x 7))
    (when #f (set! x 9))
    x
    """

    assert run_source(source) == [None, None, None, None, 7]


def test_define_syntax_unless_expands_before_evaluation():
    source = """
    (define-syntax unless
      (syntax-rules ()
        ((unless test expr) (if test #f expr))))
    (define x 0)
    (unless #f (set! x 3))
    (unless #t (set! x 9))
    x
    """

    assert run_source(source) == [None, None, None, False, 3]


def test_syntax_rules_substitutes_pattern_variables():
    source = """
    (define-syntax pair-up
      (syntax-rules ()
        ((pair-up left right) (list right left))))
    (pair-up (+ 1 1) (+ 2 3))
    """

    _, value = run_source(source)

    assert to_scheme_string(value) == "(5 2)"


def test_syntax_rules_matches_literal_identifiers():
    source = """
    (define-syntax choose
      (syntax-rules (else)
        ((choose else expr) expr)
        ((choose test expr) (if test expr #f))))
    (choose else 42)
    (choose #t 7)
    (choose #f 9)
    """

    assert run_source(source) == [None, 42, 7, False]


def test_literal_identifier_does_not_match_string_literal():
    source = """
    (define-syntax only-else
      (syntax-rules (else)
        ((only-else else expr) expr)))
    (only-else "else" 42)
    """

    with pytest.raises(SchemeRuntimeError, match="found no matching rule"):
        run_source(source)


def test_syntax_rules_wildcard_does_not_bind_or_evaluate():
    source = """
    (define-syntax constant
      (syntax-rules ()
        ((constant _ value) value)))
    (constant missing 11)
    """

    assert run_source(source) == [None, 11]


def test_local_define_syntax_is_available_in_current_environment():
    source = """
    ((lambda ()
       (define-syntax one
         (syntax-rules ()
           ((one) 1)))
       (one)))
    """

    assert run_source(source) == [1]


def test_syntax_rules_reports_unmatched_invocation():
    source = """
    (define-syntax only-two
      (syntax-rules ()
        ((only-two left right) left)))
    (only-two 1)
    """

    with pytest.raises(SchemeRuntimeError, match="found no matching rule"):
        run_source(source)


def test_syntax_rules_rejects_malformed_rule():
    source = """
    (define-syntax bad
      (syntax-rules ()
        ((bad x))))
    """

    with pytest.raises(SchemeRuntimeError, match="rules must be .* pairs"):
        run_source(source)


def test_syntax_rules_repeats_when_body_expressions():
    source = """
    (define-syntax when
      (syntax-rules ()
        ((when test body ...)
         (if test (begin body ...)))))
    (define x 0)
    (when #f)
    (when #t (set! x 1))
    (when #t (set! x (+ x 2)) (set! x (+ x 3)))
    x
    """

    assert run_source(source) == [None, None, None, None, None, 6]


def test_syntax_rules_repeats_multiple_pattern_variables_in_lockstep():
    source = """
    (define-syntax pair-list
      (syntax-rules ()
        ((pair-list (a b) ...)
         (list (list a b) ...))))
    (pair-list (1 2) (3 4) ((+ 2 3) 6))
    """

    _, value = run_source(source)

    assert to_scheme_string(value) == "((1 2) (3 4) (5 6))"


def test_syntax_rules_can_repeat_template_variable_more_than_once():
    source = """
    (define-syntax duplicate
      (syntax-rules ()
        ((duplicate item ...)
         (list item ... item ...))))
    (duplicate 1 2 3)
    """

    _, value = run_source(source)

    assert to_scheme_string(value) == "(1 2 3 1 2 3)"


def test_syntax_rules_reports_template_ellipsis_without_repeated_variable():
    source = """
    (define-syntax bad
      (syntax-rules ()
        ((bad x) (list x ...))))
    (bad 1)
    """

    with pytest.raises(SchemeRuntimeError, match="repeated pattern variable"):
        run_source(source)


def test_syntax_rules_rejects_illegal_ellipsis_with_clear_error():
    source = """
    (define-syntax bad
      (syntax-rules ()
        ((bad x ... ...) x)))
    """

    with pytest.raises(SchemeRuntimeError, match="ellipsis"):
        run_source(source)


def test_hygiene_lambda_binding_does_not_capture_user_identifier():
    source = """
    (define-syntax with-temp
      (syntax-rules ()
        ((with-temp expr)
         ((lambda (tmp) expr) 0))))
    (let ((tmp 42))
      (with-temp tmp))
    """

    assert run_source(source) == [None, 42]


def test_hygiene_lambda_internal_reference_uses_introduced_binding():
    source = """
    (define-syntax local-temp
      (syntax-rules ()
        ((local-temp)
         ((lambda (tmp) tmp) 0))))
    (let ((tmp 42))
      (local-temp))
    """

    assert run_source(source) == [None, 0]


def test_hygiene_let_binding_does_not_capture_user_identifier():
    source = """
    (define-syntax with-let-temp
      (syntax-rules ()
        ((with-let-temp expr)
         (let ((tmp 0)) expr))))
    (let ((tmp 42))
      (with-let-temp tmp))
    """

    assert run_source(source) == [None, 42]


def test_hygiene_let_internal_reference_uses_introduced_binding():
    source = """
    (define-syntax local-let-temp
      (syntax-rules ()
        ((local-let-temp)
         (let ((tmp 0)) tmp))))
    (let ((tmp 42))
      (local-let-temp))
    """

    assert run_source(source) == [None, 0]


def test_hygiene_let_star_internal_reference_uses_introduced_binding():
    source = """
    (define-syntax local-let-star-temp
      (syntax-rules ()
        ((local-let-star-temp)
         (let* ((tmp 0)
                (value tmp))
           value))))
    (let ((tmp 42))
      (local-let-star-temp))
    """

    assert run_source(source) == [None, 0]


def test_hygiene_letrec_internal_reference_uses_introduced_binding():
    source = """
    (define-syntax local-letrec-temp
      (syntax-rules ()
        ((local-letrec-temp)
         (letrec ((tmp (lambda () 0))
                  (value (lambda () (tmp))))
           (value)))))
    (let ((tmp 42))
      (local-letrec-temp))
    """

    assert run_source(source) == [None, 0]


def test_hygiene_named_let_does_not_capture_user_identifier():
    source = """
    (define-syntax with-loop
      (syntax-rules ()
        ((with-loop expr)
         (let loop ((tmp 0))
           expr))))
    (let ((tmp 42)
          (loop 99))
      (with-loop (list tmp loop)))
    """

    _, value = run_source(source)

    assert to_scheme_string(value) == "(42 99)"


def test_hygiene_named_let_internal_reference_uses_introduced_binding():
    source = """
    (define-syntax count-down
      (syntax-rules ()
        ((count-down n)
         (let loop ((tmp n))
           (if (= tmp 0)
               tmp
               (loop (- tmp 1)))))))
    (let ((tmp 42)
          (loop 99))
      (count-down 3))
    """

    assert run_source(source) == [None, 0]
