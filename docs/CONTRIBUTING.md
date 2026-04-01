# Contributing — LLM-Delivered Code Workflow

*This document defines the process for implementing code with LLM assistance, ensuring every change is reviewed, tested, and traceable.*

## Workflow

### 1. Step-by-Step Delivery

Code is delivered one implementation plan step at a time. Each step corresponds to an entry in [plan.md](/docs/plan.md).

- The LLM implements **only the current step** — no work ahead.
- The human reviewer reads the diff, runs the acceptance criteria, and gives explicit approval before the next step begins.
- If changes are needed, the reviewer provides feedback and the step is revised before moving on.

### 2. TDD Cycle

Every feature follows the Red → Green cycle:

1. **Red** — Write failing tests that define the expected behaviour. Run `pytest` to confirm they fail.
2. **Green** — Write the minimum implementation to make the tests pass. Run `pytest` to confirm they pass.

Test steps and implementation steps are separate entries in the plan. This ensures the reviewer can verify test quality independently of the implementation.

### 3. Review Checkpoints

At the end of each step, before approval, the reviewer should verify:

| Check               | Command                                              | Expected                  |
|----------------------|------------------------------------------------------|---------------------------|
| Tests pass           | `pytest`                                             | All green                 |
| Coverage             | `pytest --cov=api --cov=config --cov-report=term-missing` | No regressions     |
| Type checking        | `mypy api config`                                    | 0 errors                  |
| Django system check  | `python manage.py check`                             | 0 issues                  |

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

### File Placement

- Source code goes in `backend/api/` and `backend/config/`.
- Tests go in `backend/tests/`, mirroring the source tree.
- Documentation goes in `docs/`.
- No code outside these directories unless the spec explicitly requires it.

## LLM-Specific Guidelines

### What the LLM should do

- Follow the plan step sequence exactly.
- Write tests before implementation (when the plan says so).
- Include only files and changes required by the current step.
- Use the existing code style, naming, and conventions already established in the project.
- Run the acceptance criteria commands and report the output.

### What the LLM should not do

- Skip ahead to future steps.
- Add features, refactors, or "improvements" not in the current step.
- Create helper utilities or abstractions beyond what the step requires.
- Modify test files during implementation steps (and vice versa) unless fixing a genuine defect.
- Ship code without docstrings — all functions, classes, and modules must be documented before review.
