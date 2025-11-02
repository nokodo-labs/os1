# Data Directory

This directory is for application data storage.

## Usage

Store and read files from `/app/data` in your backend code:

```python
from pathlib import Path

DATA_DIR = Path("/app/data")

# Write
(DATA_DIR / "output.txt").write_text("data")

# Read
content = (DATA_DIR / "input.txt").read_text()
```

## Docker Volume

This directory is mounted in `docker-compose.yml`:

```yaml
volumes:
    - ../backend/data:/app/data
```

Files persist across container restarts.

## .gitignore

Add to `.gitignore` to exclude data files:

```
backend/data/*
!backend/data/README.md
```
