# nokodo AI SDK

## purpose

this package contains the core business logic and service layer, separate from the FastAPI application. it can be:

- packaged independently and distributed via pip
- imported by the API layer (`api/` directory)
- used by other Python projects without FastAPI dependencies
- tested independently with its own test suite

## structure

```
nokodo_ai/
├── __init__.py          # package initialization
├── services/            # business logic
├── utils/               # helper functions
└── types/               # type definitions
```

## usage in API

```python
from api.core.database import get_db
from nokodo_ai.services import MyService

@router.get("/example")
async def example(db: AsyncSession = Depends(get_db)):
	service = MyService(db)
	return await service.do_something()
```
