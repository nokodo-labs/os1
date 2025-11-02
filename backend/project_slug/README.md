# Project Name SDK

**RENAME THIS PACKAGE**: Change `project_slug` to your actual project name throughout the codebase.

## Purpose

This package contains the core business logic and service layer, separate from the FastAPI application. It can be:

-   Packaged independently and distributed via pip
-   Imported by the API layer (`api/` directory)
-   Used by other Python projects without FastAPI dependencies
-   Tested independently with its own test suite

## Structure

```
project_slug/
├── __init__.py          # Package initialization
├── services/            # Business logic
├── utils/               # Helper functions
└── types/               # Type definitions
```

## Usage in API

```python
from api.core.database import get_db
from project_slug.services import MyService

@router.get("/example")
async def example(db: AsyncSession = Depends(get_db)):
	service = MyService(db)
	return await service.do_something()
```

## Renaming

1. Rename the `project_slug` directory to your project name
2. Update imports in `api/` files
3. Update `pyproject.toml` if packaging separately
