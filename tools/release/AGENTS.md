# nokodo AI release tooling guidelines

custom release and versioning tooling for the nokodo AI monorepo. replaces release-please.

## tech stack

- Node.js 24+ ESM modules
- `semver` for version parsing, comparison, and incrementing
- `conventional-commits-parser` for parsing conventional commit messages
- `gh` CLI for GitHub API operations (pre-installed on GitHub Actions runners)
- npm as package manager (only two production deps)

## code style

- tabs indents, unix line endings
- adhere to `nokodo` brand rule of **no auto-capitalization** in comments, docstrings, logging, or any user-facing text. only proper nouns, acronyms and other intentional capitalizations are allowed.
- no TypeScript, no build step - plain ESM `.mjs` files

## modules

- `src/config.mjs` - single source of truth for changelog categories, monorepo package definitions, labels, and constants
- `src/git.mjs` - git CLI wrappers for tag listing, commit extraction, repo slug detection
- `src/changelog.mjs` - conventional commit parsing, bump recommendation, markdown changelog rendering. also has a CLI entry point used by `promotion.yml`
- `src/version.mjs` - read/write version in `package.json` and `pyproject.toml` files
- `src/github.mjs` - GitHub operations via `gh` CLI (releases, PRs, labels)
- `src/release.mjs` - main orchestrator entry point. creates/updates release PRs on push, detects merged release PRs via GitHub API, creates tags and GitHub releases on merge

## how it works

1. on push to `dev` or `stable`, `release.yml` runs `node src/release.mjs`
2. commits since last tag are parsed for conventional commit types
3. a version bump is computed (RC for dev, stable for stable)
4. a release PR is created/updated with version file changes
5. when the release PR is merged, tags are created and a GitHub release is published
6. component tags (e.g. `frontend-v1.2.3`) are created alongside the root tag

## validation

```sh
cd tools/release
npm ci
node src/release.mjs        # main entry (requires BRANCH, GITHUB_TOKEN env vars)
node src/changelog.mjs --from <ref> --to <ref>   # standalone changelog generation
npm test                     # run unit tests (node:test runner)
```

## environment variables

- `GITHUB_TOKEN` - required for `gh` CLI auth
- `BRANCH` - current branch name (`dev` or `stable`)
- `GITHUB_OUTPUT` - path to write outputs (GitHub Actions)
- `RELEASE_AS` - optional manual version override
- `GITHUB_REPOSITORY` - fallback repo slug (`owner/repo`)
