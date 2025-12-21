# SDK/service layer tests

tests for the `nokodo_ai` package business logic and services.

## purpose

test the SDK independently of the API layer:

-   unit tests for services
-   tests for utility functions
-   type checking and validation
-   no database or HTTP dependencies (use mocks)

## running

```bash
# run SDK tests only
pytest nokodo_ai/tests/

# with coverage
pytest nokodo_ai/tests/ --cov=nokodo_ai
```

## structure

keep tests focused on business logic without FastAPI/database dependencies. use mocks for external dependencies.
