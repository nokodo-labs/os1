# end-to-end tests

integration tests that span the full stack: API → SDK → database.

## purpose

- test complete user workflows
- verify API and SDK integration
- test with real database connections
- validate production-like scenarios

## running

```bash
# run E2E tests
pytest tests/

# with coverage for entire backend
pytest tests/ --cov=api --cov=project_name
```

## Structure

Place tests here that require both the API layer and SDK layer working together. These tests typically:

- Make HTTP requests to endpoints
- Verify database state changes
- Test multi-step workflows
- Use the full application stack
