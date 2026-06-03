# Scheme Runtime Guide

`haifa_scheme` is a small teaching-oriented Scheme interpreter. It is currently a tree-walking runtime, separate from the shared bytecode VM used by the Lua and jq tracks.

## Running Code

Run a script:

```bash
python3 -m haifa_scheme.cli examples/factorial.scm --print-output
```

Evaluate inline source:

```bash
python3 -m haifa_scheme.cli -e "(+ 1 2 3)" --print-output
```

Start the REPL:

```bash
python3 -m haifa_scheme.cli --repl
```

After installing the package, the same CLI is available as:

```bash
pyscheme --help
```

## Supported Core Forms

- `quote` and quote shorthand, such as `'x` and `'(1 2 3)`
- `if`, including the optional alternate form
- `define`, including function shorthand
- `lambda`
- `begin`
- `set!`
- `let`, named `let`, `let*`, and `letrec`
- `and`, `or`, `cond`, `case`, and `do`
- `define-syntax` with `syntax-rules`

Only `#f` is false. Numbers, strings, symbols, pairs, and the empty list are truthy.
When an `if`, `case`, or `do` form has no selected result expression, the runtime returns `#<void>`.

## Values

The runtime supports:

- numbers
- strings
- characters, such as `#\a`, `#\space`, and `#\newline`
- booleans: `#t` and `#f`
- symbols
- the empty list: `()`
- pairs and proper lists
- vectors
- EOF object: `#<eof>`
- textual input and output ports
- user procedures and builtin procedures

List and pair values print in Scheme form:

```scheme
'(1 2 3)       ; (1 2 3)
(cons 1 2)    ; (1 . 2)
'(1 . 2)      ; (1 . 2)
#(1 2 3)      ; #(1 2 3)
```

The reader also understands quasiquote syntax, expanding backquote, comma, and comma-at into `quasiquote`, `unquote`, and `unquote-splicing` forms. Runtime quasiquote expansion is not implemented yet.

## Builtins

Numeric operations:

- `+`
- `-`
- `*`
- `/`
- `=`
- `<`
- `>`

List and equality operations:

- `cons`
- `car`
- `cdr`
- `list`
- `length`
- `append`
- `reverse`
- `map`
- `for-each`
- `null?`
- `pair?`
- `list?`
- `eq?`
- `equal?`
- `apply`
- `call/cc`
- `call-with-current-continuation`

Ports and IO:

- `display`
- `write`
- `newline`
- `read`
- `open-input-file`
- `open-output-file`
- `close-input-port`
- `close-output-port`
- `current-input-port`
- `current-output-port`

Predicates:

- `number?`
- `integer?`
- `string?`
- `symbol?`
- `boolean?`
- `char?`
- `vector?`
- `procedure?`
- `input-port?`
- `output-port?`

## Macros

The runtime supports a small `syntax-rules` macro system:

- pattern variables
- literal identifiers
- wildcard `_`
- common one-level ellipsis forms such as `body ...` and `(x y) ...`
- hygiene for local bindings introduced by macro templates in `lambda`, `let`, `let*`, `letrec`, and named `let`

Example:

```scheme
(define-syntax when
  (syntax-rules ()
    ((when test body ...)
     (if test (begin body ...)))))

(define x 0)
(when #t
  (set! x (+ x 1))
  (set! x (+ x 2)))
```

Nested ellipsis such as `((x ...) ...)` and full R5RS referential hygiene are not implemented yet.

## Continuations

The runtime supports escape-only continuations through `call/cc` and its alias
`call-with-current-continuation`.

```scheme
(+ 1
   (call/cc
    (lambda (k)
      (k 41)
      99))) ; 42
```

The captured continuation may be called while the dynamic extent of the `call/cc`
is still active. Saved continuations cannot be invoked after that extent has
returned; doing so raises a runtime error. Full re-entrant continuations are out
of scope for the current tree-walking evaluator.

## Ports And IO

The runtime supports textual ports for basic Scheme IO. `display` writes strings
and characters directly, while `write` uses Scheme literal formatting.

```scheme
(display "hello") ; hello
(write "hello")   ; "hello"
(newline)
```

`read` parses Scheme datums from the current input port or an explicit input
port. A single port can be read repeatedly; when no datums remain, `read`
returns `#<eof>`.

```scheme
(define in (open-input-file "data.scm"))
(read in)
(close-input-port in)
```

File ports are UTF-8 text ports. `open-output-file` overwrites the destination.
Closed ports reject further reads or writes with a runtime error.

## Examples

Recursive factorial:

```scheme
(define (fact n)
  (if (= n 0)
      1
      (* n (fact (- n 1)))))

(fact 5)
```

Closure with mutation:

```scheme
(define make-counter
  (lambda ()
    (let ((value 0))
      (lambda ()
        (set! value (+ value 1))
        value))))

(define counter (make-counter))
(list (counter) (counter) (counter))
```

## Current Non-Goals

The runtime does not yet implement runtime quasiquote expansion, exact/inexact numeric towers, full re-entrant continuations, binary ports, append-mode file ports, or bytecode compilation.
