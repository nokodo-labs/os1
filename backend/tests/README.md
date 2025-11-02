# End-to-End Tests

Integration tests that span the full stack: API → SDK → Database.

## Purpose

-   Test complete user workflows
-   Verify API and SDK integration
-   Test with real database connections
-   Validate production-like scenarios

## Running

```bash
# Run E2E tests
pytest tests/

# With coverage for entire backend
pytest tests/ --cov=api --cov=project_name
```

## Structure

Place tests here that require both the API layer and SDK layer working together. These tests typically:

-   Make HTTP requests to endpoints
-   Verify database state changes
-   Test multi-step workflows
-   Use the full application stack
