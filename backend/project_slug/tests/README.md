# SDK/Service Layer Tests

Tests for the `project_slug` package business logic and services.

## Purpose

Test the SDK independently of the API layer:

-   Unit tests for services
-   Tests for utility functions
-   Type checking and validation
-   No database or HTTP dependencies (use mocks)

## Running

```bash
# Run SDK tests only
pytest project_slug/tests/

# With coverage
pytest project_slug/tests/ --cov=project_slug
```

## Structure

Keep tests focused on business logic without FastAPI/database dependencies. Use mocks for external dependencies.
