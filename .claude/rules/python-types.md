# Python Type Annotation Conventions

## General

- Python 3.13+. Use modern type syntax throughout.
- `X | None` instead of `Optional[X]`.
- Use builtin generics: `list[X]`, `dict[X, Y]`, `set[X]`, `tuple[X, ...]`.
- Import abstract types from `collections.abc`, not `typing`: `Sequence`, `Mapping`, `AsyncGenerator`, `Callable`, etc.
- Only import from `typing` for special forms: `Literal`, `Annotated`, `Self`, `TypeVar`, `overload`, `TYPE_CHECKING`, `cast`, `final`, `override`.

## Type Aliases

- Always use PEP 695 `type` statement syntax:
  ```python
  type SessionID = int
  type SqidOrNew[T] = int | NewValue[T]
  ```
- Do not use `TypeAlias` for new code. Migrate existing `TypeAlias` usage when touching those files.

## Forward References

- Use `from __future__ import annotations` only when needed for forward references or circular import resolution.
- Do not add it to every file by default.

## TYPE_CHECKING Blocks

- Use `if TYPE_CHECKING:` for imports only needed by type checkers (avoids circular imports at runtime).
- Pair with runtime fallbacks when the type is needed at runtime:
  ```python
  if TYPE_CHECKING:
      from typing import Protocol
      class HasID(Protocol):
          @property
          def id(self) -> int: ...
  else:
      from typing import Any
      HasID = Any
  ```

## Type Decorators

- Use `@final` on classes that should not be subclassed.
- Use `@override` on methods that override a parent class method.
- Use `@overload` for functions with multiple call signatures.

## Annotated Types

- Use `Annotated` with Pydantic validators for request parameter validation:
  ```python
  SqidInt = Annotated[int, BeforeValidator(sink)]
  ```
