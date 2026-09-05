# data directory

this directory is for application data storage.

## contents

- `htmlcov/` - test coverage reports
- `.coverage` - coverage data file

## usage

store and read files from `/app/data` in your backend code:

```python
from pathlib import Path

DATA_DIR = Path("/app/data")

# write
(DATA_DIR / "output.txt").write_text("data")

# read
content = (DATA_DIR / "input.txt").read_text()
```

## Docker volume

this directory is mounted in `docker-compose.yml`:

```yaml
volumes:
    - ../backend/data:/app/data
```

files persist across container restarts.

## .gitignore

add to `.gitignore` to exclude data files:

```
backend/data/*
!backend/data/README.md
```
