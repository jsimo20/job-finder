# Google Python Style Guide — Reviewer Cheat Sheet

Condensed from <https://google.github.io/styleguide/pyguide.html>. Use as a checklist when reviewing `.py` files. Only loaded when the diff touches Python.

## Language rules (§2)

- **§2.1 Lint** — defer to `ruff`/`pylint` config in the repo; suppress per-line only with justification.
- **§2.2-2.3 Imports** — `import x` for packages; `from x import y` only for submodules. Use full package paths; avoid relative imports.
- **§2.4 Exceptions** — never `except:` or bare `except Exception:` unless re-raising. Don't use `assert` for runtime logic. Keep `try` blocks minimal.
- **§2.5 Mutable global state** — forbidden. Module-level constants only.
- **§2.7 Comprehensions** — fine for simple cases; **multiple `for` clauses are forbidden**.
- **§2.12 Default args** — never use mutable objects as defaults (`def f(x=[]):` is a bug).
- **§2.14 True/False** — implicit truthiness OK; always check `None` explicitly (`if x is None`, not `if not x` when `x` could be `0`/`""`).
- **§2.17 Decorators** — never `@staticmethod`; `@classmethod` only for named constructors.
- **§2.19 Power features** — avoid metaclasses, bytecode manipulation, `__del__`, dynamic inheritance.
- **§2.21 Type annotations** — strongly encouraged. Required for public APIs and complex/error-prone code.

## Style rules (§3)

- **§3.1 Semicolons** — never.
- **§3.2 Line length** — 80 chars. Exceptions: long imports, URLs, string constants, pylint directives. Use implicit line joining inside parens/brackets, not backslashes.
- **§3.4 Indentation** — 4 spaces, never tabs.
- **§3.5 Blank lines** — 2 between top-level defs, 1 between methods.
- **§3.6 Whitespace** — no space inside brackets, no space before `,;:`, single space around binary operators. No spaces around `=` in kwargs **unless** type annotation present.
- **§3.8 Docstrings** — triple-double-quotes. Mandatory for public API, nontrivial functions, and classes.
- **§3.10 Strings** — f-strings, `%`, or `.format()`. Never `+` accumulation in loops — use `''.join()` or `io.StringIO`.
- **§3.10.1 Logging** — pass format string + args to logger, not f-string: `log.info("user %s", user_id)` not `log.info(f"user {user_id}")`.
- **§3.11 Resources** — always `with` for files/sockets. `contextlib.closing()` for legacy non-context-managers.
- **§3.12 TODO** — `# TODO(<issue/owner>): <description>` — include reference, not bare `# TODO`.
- **§3.13 Imports order** — `__future__` → stdlib → third-party → first-party. Sorted lexicographically inside each group. One import per line.
- **§3.16 Naming** — `module_name`, `ClassName`, `function_name`, `GLOBAL_CONSTANT`, `instance_var`, `_protected`. No dashes in package names. No single-letter names except counters/exceptions/type-vars.
- **§3.17 Main** — wrap entry in `def main():` and `if __name__ == '__main__': main()`.
- **§3.18 Function length** — break up at ~40 lines unless cohesive.
- **§3.19 Type annotations**:
  - Annotate function args and return types for public APIs.
  - Use `X | None` (Python 3.10+), not `Optional[X]`.
  - One param per line when signature is long; closing `)` aligned with `def`.
  - Prefer `collections.abc.Sequence` over `list` for parameters (be generous in inputs).
  - Place type-only imports in `if TYPE_CHECKING:` block.
  - Annotated assignment: `a: Foo = ...`, not `# type:` comments.

## Reviewer's red-flag patterns (instant findings)

```python
def f(x=[]):           # §2.12 — mutable default
except Exception:       # §2.4 — too broad, no re-raise
log.info(f"u={user}")   # §3.10.1 — f-string in logger
if not user:            # §2.14 — ambiguous when user is "" or 0
from .utils import foo  # §2.3 — relative import
get_user_by_id          # §3.15 — needless getter; use attribute
class Foo(metaclass=…): # §2.19 — power feature
```

When in doubt, defer to the full guide.
