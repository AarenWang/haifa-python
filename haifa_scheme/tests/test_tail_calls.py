from __future__ import annotations

import math

from haifa_scheme import Symbol, run_source


def test_tail_recursive_countdown_does_not_overflow_python_stack():
    source = """
    (define (countdown n)
      (if (= n 0)
          'done
          (countdown (- n 1))))

    (countdown 1500)
    """

    assert run_source(source) == [None, Symbol("done")]


def test_tail_recursive_factorial_with_accumulator():
    source = """
    (define (fact-iter n acc)
      (if (= n 0)
          acc
          (fact-iter (- n 1) (* acc n))))

    (fact-iter 40 1)
    """

    assert run_source(source) == [None, math.factorial(40)]


def test_tail_call_through_cond_and_let_body():
    source = """
    (define (countdown n)
      (let ((next (- n 1)))
        (cond ((= n 0) 'done)
              (else (countdown next)))))

    (countdown 1500)
    """

    assert run_source(source) == [None, Symbol("done")]
