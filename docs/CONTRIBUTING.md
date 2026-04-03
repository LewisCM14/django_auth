# Contributing — LLM-Delivered Code Workflow

*This document defines the process for implementing code with LLM assistance, ensuring every change is reviewed, tested, and traceable.*

## Workflow

### 1. Step-by-Step Delivery

Code is delivered one implementation plan step at a time. Each step corresponds to an entry in [plan.md](/docs/plan.md).

- The LLM implements **only the current step** — no work ahead.
- The human reviewer reads the diff, runs the acceptance criteria, and gives explicit approval before the next step begins.
- If changes are needed, the reviewer provides feedback and the step is revised before moving on.

### 2. Implementation & Verification Cycle

Every feature is delivered in two consecutive steps:

1. **Implementation** — Write the minimum production code for the feature. Run `pytest` to confirm existing tests still pass. `mypy` and `ruff` must be clean. New code may have uncovered lines at this stage.
2. **Verification** — Write tests that verify the expected behaviour and achieve 100% coverage. Run `pytest` to confirm all tests pass with full coverage.

Implementation steps and test steps are separate entries in the plan. This ensures the reviewer can verify production code quality independently before assessing test coverage.

### 3. Review Checkpoints

At the end of each step, before approval, the reviewer should verify:

| Check               | Command                                              | Expected                  |
|----------------------|------------------------------------------------------|---------------------------|
| Tests pass           | `uv run pytest`                                      | All green                 |
| Coverage             | `uv run pytest` (coverage in `pytest.ini` addopts)   | 100%, no regressions      |
| Type checking        | `uv run mypy api config`                             | 0 errors                  |
| Linting              | `uv run ruff check .`                                | All checks passed         |
| Django system check  | `uv run python manage.py check`                      | 0 issues                  |

If any check fails, the step is not approved until it is resolved.

### 4. Commit Convention

Each approved step should be committed with a message referencing the plan step:

```
step-XX: <short description>
```

Examples:
```
step-01: add pyproject.toml and environment.yml dependencies
step-05: add health endpoint tests (red)
step-06: implement health endpoint (green)
```

This creates a linear, auditable history that maps 1:1 with the implementation plan.

## Code Standards

### Static Typing

- All function signatures must have full type annotations.
- `mypy` runs in strict mode via `mypy.ini`.
- Use `django-stubs` and `djangorestframework-stubs` for framework type support.

### Documentation

All Python modules, classes, and functions must be documented with docstrings. Follow these conventions:

**Module Docstrings** — Every `.py` file (except empty `__init__.py` files) must have a docstring at the very top:
```python
"""Brief one-line description of module purpose."""
```

**Class Docstrings** — Every class must have a docstring:
```python
class UserSerializer:
    """Serializes user data for API responses."""
```

**Function & Method Docstrings** — Every function and method must have a docstring:
```python
def get_user_role(user_id: int) -> str:
    """Fetch user role from LDAP or cache.
    
    Args:
        user_id: The numeric ID of the user.
    
    Returns:
        The user's role string (e.g., 'admin', 'user').
    
    Raises:
        UserNotFoundError: If the user does not exist in LDAP.
    """
```

Use **Google-style docstrings** for consistency (one-liner for simple functions, Args/Returns/Raises sections for complex ones). Docstrings must be present *before* any code review or approval.

### Testing

- Every module has a corresponding test file in `tests/` mirroring the source structure.
- Tests are grouped in classes named after the subject under test (e.g., `TestHealthView`).
- Shared fixtures live in `tests/conftest.py`.
- Target: 100% line coverage across `api/` and `config/`.
- Use `@pytest.mark.django_db` only on methods that touch the database, not at class level.
- Tests that can run without the database should force IIS mode via `monkeypatch.setenv("AUTH_MODE", "iis")` to avoid the dev-mode startup guard.

### Logging

- Use Python's standard `logging` module: `logger = logging.getLogger(__name__)`.
- Do **not** configure handlers or formatters in application code — `config/settings.py` owns all logging configuration via the `LOGGING` dict.
- Request-ID correlation is automatic via the `RequestIdFilter`. No manual passing of request IDs to log calls is required.
- Log levels:
    - `DEBUG` — Detailed diagnostic information (never in production).
    - `INFO` — Normal operational events (request served, cache hit, adapter call completed).
    - `WARNING` — Unexpected but recoverable situations (access denied, cache miss on expected key, retry attempt).
    - `ERROR` — Failures that need investigation (unhandled exceptions, adapter failures, database errors).
- Never log sensitive data: request bodies, passwords, tokens, or PII beyond the corporate username.

### Error Handling

- Do **not** add `try/except` blocks in views to catch and format errors. The custom DRF exception handler (`api/exceptions.py`) catches all exceptions raised within views and returns a consistent error envelope.
- For business rule violations in the service layer, raise DRF's `ValidationError` or `PermissionDenied`. The exception handler will format them.
- For adapter-specific errors that should surface a non-500 status code, define a custom `APIException` subclass with the appropriate `status_code` and `default_detail`.
- Unhandled exceptions automatically become 500 responses with no internal details leaked. The traceback is logged server-side.

### File Placement

- Source code goes in `backend/api/` and `backend/config/`.
- Tests go in `backend/tests/`, mirroring the source tree.
- Documentation goes in `docs/`.
- No code outside these directories unless the spec explicitly requires it.

## LLM-Specific Guidelines

### What the LLM should do

- Follow the plan step sequence exactly.
- Write tests after implementation (when the plan pairs an implementation step with a verification step).
- Include only files and changes required by the current step.
- Use the existing code style, naming, and conventions already established in the project.
- Run the acceptance criteria commands and report the output.

### What the LLM should not do

- Skip ahead to future steps.
- Add features, refactors, or "improvements" not in the current step.
- Create helper utilities or abstractions beyond what the step requires.
- Modify test files during implementation steps (and vice versa) unless fixing a genuine defect.
- Ship code without docstrings — all functions, classes, and modules must be documented before review.
