# nokodo AI SDK

## Purpose

This package contains the core business logic and service layer, separate from the FastAPI application. It can be:

-   Packaged independently and distributed via pip
-   Imported by the API layer (`api/` directory)
-   Used by other Python projects without FastAPI dependencies
-   Tested independently with its own test suite

## Structure

```
nokodo_ai/
├── __init__.py          # Package initialization
├── services/            # Business logic
├── utils/               # Helper functions
└── types/               # Type definitions
```

## Usage in API

```python
from api.core.database import get_db
from nokodo_ai.services import MyService

@router.get("/example")
async def example(db: AsyncSession = Depends(get_db)):
	service = MyService(db)
	return await service.do_something()
```
