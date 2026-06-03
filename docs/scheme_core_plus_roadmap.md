# Scheme Core+ Roadmap

This roadmap extends the current teaching Scheme runtime toward a more standard Scheme subset while keeping each step small enough to review and test independently.

## Current Baseline

Implemented:

- Reader for numbers, strings, booleans, symbols, lists, dotted lists, character literals, vectors, quote/quasiquote shorthand, and line comments.
- Tree-walking evaluator with lexical environments and closures.
- Core forms: `quote`, `if`, `define`, `lambda`, `begin`, `set!`, `let`, named `let`, `let*`, `letrec`, `and`, `or`, `cond`, `case`, `do`.
- Pair/list values, Scheme formatting, and basic equality.
- Builtins: `+`, `-`, `*`, `/`, `=`, `<`, `>`, `cons`, `car`, `cdr`, `list`, `length`, `append`, `reverse`, `map`, `for-each`, `apply`, predicates, `eq?`, `equal?`.
- Macro expansion with `define-syntax` and a practical `syntax-rules` subset.
- Escape-only continuations with `call/cc` and `call-with-current-continuation`.
- CLI, examples, REPL, and trampoline support for key tail-call positions.

## Phase 1: Reader Data Coverage

Goal: make Scheme data syntax much closer to everyday Scheme source.

Features:

- Dotted pair reader syntax:
  - `(1 . 2)`
  - `(a b . c)`
  - quoted dotted forms, such as `'(1 . 2)`
- Quasiquote reader syntax:
  - backquote
  - unquote
  - unquote-splicing
- Character literals:
  - `#\a`
  - `#\space`
  - `#\newline`
- Vector literals:
  - `#(1 2 3)`

Suggested commits:

1. Add dotted pair reader support.
2. Add quasiquote/unquote reader forms.
3. Add character and vector value syntax.

Tests:

- Reader tests for valid and invalid dotted pair syntax.
- Runtime quote tests for dotted lists.
- Formatting tests for characters and vectors.
- Syntax error tests for malformed dotted pairs and incomplete quasiquote forms.

## Phase 2: Core Stdlib Expansion

Goal: add the first set of practical standard procedures.

Features:

- Procedure application:
  - `apply`
- Higher-order list procedures:
  - `map`
  - `for-each`
- List utilities:
  - `append`
  - `reverse`
  - `length`
- Predicates:
  - `number?`
  - `integer?`
  - `string?`
  - `symbol?`
  - `boolean?`
  - `procedure?`
  - `char?`
  - `vector?`

Suggested commits:

1. Add `apply` and procedure predicates.
2. Add `length`, `append`, and `reverse`.
3. Add `map`, `for-each`, and value predicates.

Tests:

- Proper and improper list argument validation.
- `apply` with builtin and user procedures.
- `map` and `for-each` with closures.
- Predicate tests for every runtime value type.

## Phase 3: Core Form Compatibility

Goal: fill common Scheme control and binding forms.

Features:

- Optional `if` else branch:
  - `(if test consequent)`
- Named `let`:
  - `(let loop ((n 10) (acc 0)) ...)`
- `case`
- `do`

Suggested commits:

1. Add optional `if` else and named `let`.
2. Add `case`.
3. Add `do`.

Tests:

- `if` without alternate returns a void/unspecified value.
- Named `let` supports tail-recursive loops.
- `case` uses datum matching and supports `else`.
- `do` handles initialization, stepping, termination, and result expressions.

## Phase 4: Hygienic Macros

Goal: implement a small but useful `syntax-rules` macro system.

Features:

- `define-syntax`
- `syntax-rules`
- Pattern variables
- Literal identifiers
- Ellipsis matching for repeated forms
- Hygienic expansion for introduced bindings

Suggested commits:

1. Add macro objects, macro environment, and expansion entry point.
2. Add basic `syntax-rules` pattern/template expansion.
3. Add ellipsis and hygiene behavior.
4. Add macro examples and docs.

Tests:

- Basic macros such as `when`, `unless`, and `swap!`.
- Literal identifier matching.
- Repeated pattern matching with ellipsis.
- Hygiene tests where introduced identifiers do not capture user bindings.

Implemented boundary:

- Common one-level ellipsis forms are supported.
- Template-introduced local bindings are scoped for `lambda`, `let`, `let*`, `letrec`, and named `let`.
- Nested ellipsis and full referential hygiene remain out of scope.

## Phase 5: Advanced Scheme Semantics

Goal: tackle standard features that need deeper runtime changes.

Features:

- Continuations:
  - escape-only `call/cc`
- Ports and IO:
  - `read`
  - `write`
  - `display`
  - `newline`
  - file input/output ports
- Number tower:
  - exact and inexact numbers
  - rational numbers
  - complex numbers
  - `eqv?` numeric semantics

Suggested commits:

1. Add continuation representation and `call/cc`.
2. Add textual output procedures.
3. Add input procedures and file ports.
4. Add exact/inexact numeric model.
5. Add rational and complex numeric support.

Tests:

- Escape continuations and re-entry behavior.
- Port lifecycle and error cases.
- `write` versus `display` formatting.
- Exact/inexact arithmetic and equality.
- Rational and complex arithmetic edge cases.

Implemented boundary:

- `call/cc` and `call-with-current-continuation` capture an escape continuation for
  the current dynamic extent.
- Continuations are procedures and can escape through nested Scheme evaluation and
  higher-order builtin callbacks.
- Calling a saved continuation after its dynamic extent has returned raises a
  runtime error. Full re-entrant continuations remain out of scope.

## Recommended Order

Start with Phase 1 and Phase 2 before macros. Reader and stdlib gaps are high-value and low-risk, while `syntax-rules`, `call/cc`, ports, and number tower require more runtime structure.

The next concrete implementation step should be Phase 5, beginning with a small continuation representation and `call/cc`, then ports, then number tower work.
