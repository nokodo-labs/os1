# Extended Instructions Directory

This directory contains domain-specific `.instructions.md` files that apply to specific file types or patterns in the workspace.

## How It Works

Each `.instructions.md` file uses YAML frontmatter to specify when it should be applied:

```markdown
---
description: "Brief description shown on hover"
applyTo: "**/*.py" # Glob pattern relative to workspace root
---

# Your instructions here in Markdown
```

## File Structure

-   **Workspace instructions**: Stored here (`.github/instructions/`)
-   **User instructions**: Stored in VS Code profile (available across workspaces)
-   **Global instructions**: Use `.github/copilot-instructions.md` in workspace root

## Examples

Create files like:

-   `python-patterns.instructions.md` - Python-specific conventions (applyTo: `**/*.py`)
-   `typescript-patterns.instructions.md` - TypeScript conventions (applyTo: `**/*.ts,**/*.tsx`)
-   `api-patterns.instructions.md` - Backend API patterns (applyTo: `backend/api/**`)
-   `database.instructions.md` - Database/ORM patterns (applyTo: `**/models/**/*.py`)
-   `frontend.instructions.md` - Frontend component patterns (applyTo: `frontend/src/**/*.svelte`)

## Tips

-   Keep instructions short and focused per file
-   Use specific `applyTo` patterns to avoid conflicts
-   Instructions apply during file creation/modification, not reads
-   Multiple files can apply to the same file pattern
-   Reference workspace files using Markdown links: `[example](../../backend/api/main.py)`

## Manual Usage

You can manually attach any instruction file to a chat prompt via:
**Chat view → Add Context → Instructions**
