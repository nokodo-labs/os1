# Backend Environment Variables Guide

All backend configuration is driven by two settings classes:

- **`BootSettings`** - loaded at startup from env/`.env` only. changes require a server restart.
- **`Settings`** - loaded from env/`.env` and overridable via DB (except write-locked fields). prefix: `NOKODO__`, nested delimiter: `__`.

---

## Frontend and Console env vars (Vite)

Both the Svelte frontend (`frontend/`) and admin console (`console/`) read the API origin using the same three-level priority chain.

### Shared resolution order

1. `VITE_API_ORIGIN` - build-time override (baked into the bundle at `docker build` time)
2. `/config.json` → `api_origin` - runtime override (written by the container entrypoint at startup)
3. Browser fallback: `${window.location.protocol}//${window.location.hostname}:${VITE_API_PORT|1383}`

### Build-time variables

| Variable          | App  | Default | Description                                                                                           |
| ----------------- | ---- | ------- | ----------------------------------------------------------------------------------------------------- |
| `VITE_API_ORIGIN` | both | `null`  | API origin baked in at build time (e.g. `https://api.example.com`). Takes highest priority.           |
| `VITE_API_PORT`   | both | `1383`  | Fallback port used by the browser when neither `VITE_API_ORIGIN` nor `config.json` provide an origin. |

### Runtime variable (Docker containers)

| Variable     | Default                        | Description                                                                                                                                                                                           |
| ------------ | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `API_ORIGIN` | `""` (unset = use nginx proxy) | Passed to the container at start. The entrypoint writes it to `/usr/share/nginx/html/config.json`, which the app fetches at browser load time. Leave unset when nginx proxies `/v1` on the same host. |

Both frontend and console containers include a `docker-entrypoint.sh` that generates `config.json` from this variable before starting nginx.

---

## Boot settings (no prefix)

These are read once at startup. No prefix required.

| Variable               | Type                  | Default                                                                       | Description                                                                                      |
| ---------------------- | --------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `DATABASE_URL`         | string                | `postgresql+psycopg://nokodo-ai-admin:nokodo-ai@127.0.0.1:5432/nokodo-ai-dev` | PostgreSQL connection URL. Supported schemes: `postgresql` or `postgresql+psycopg`.              |
| `ENV`                  | `dev` \| `production` | `production`                                                                  | Runtime environment profile.                                                                     |
| `DEBUG`                | bool                  | `false`                                                                       | Enable debug mode.                                                                               |
| `JSON_LOGS`            | bool                  | `false`                                                                       | Emit logs as JSON (recommended for production/log aggregators).                                  |
| `TESTING`              | bool                  | `false`                                                                       | Enable testing mode (used by pytest).                                                            |
| `BRANCHING_MIGRATIONS` | bool                  | `false`                                                                       | Use `heads` instead of `head` for Alembic on startup (required when using branching migrations). |

---

## Runtime settings (`NOKODO__` prefix)

Runtime settings use the `NOKODO__` prefix and `__` as the nested section separator.

Pattern: `NOKODO__<SECTION>__<FIELD>`

Fields marked **write-locked** can only be set via environment - they are frozen after startup and cannot be updated through the API.
Fields marked **private** are never returned by non-admin API responses.

---

### Cache (`NOKODO__CACHE__*`)

These settings are write-locked because API, worker, and scheduler processes must agree on them at startup.

| Variable                            | Type   | Default                    | Flags                 | Description                                                     |
| ----------------------------------- | ------ | -------------------------- | --------------------- | --------------------------------------------------------------- |
| `NOKODO__CACHE__REDIS__URL`         | string | `redis://127.0.0.1:6380/0` | private, write-locked | Redis / Valkey URL for pub/sub, task streams, and shared state. |
| `NOKODO__CACHE__REDIS__CLIENT_NAME` | string | `nokodo_ai`                | write-locked          | Name sent to Redis `CLIENT SETNAME`.                            |

### Tasks (`NOKODO__TASKS__*`)

These settings are write-locked because API, worker, and scheduler processes must agree on them at startup.

| Variable                                    | Type   | Default                      | Flags        | Description                                         |
| ------------------------------------------- | ------ | ---------------------------- | ------------ | --------------------------------------------------- |
| `NOKODO__TASKS__TASKIQ__QUEUE_NAME`         | string | `nokodo-ai:taskiq:queue`     | write-locked | TaskIQ queue shared by API, worker, and scheduler.  |
| `NOKODO__TASKS__TASKIQ__RESULT_TTL_SECONDS` | int    | `86400`                      | write-locked | Seconds to retain TaskIQ result backend entries.    |
| `NOKODO__TASKS__TASKIQ__MAX_CONNECTIONS`    | int    | `32`                         | write-locked | Maximum Redis connections used by TaskIQ.           |
| `NOKODO__TASKS__TASKIQ__AUTO_WORKERS_MAX`   | int    | unset                        | write-locked | Optional max worker processes for `--workers auto`. |
| `NOKODO__TASKS__TASKIQ__SCHEDULE_PREFIX`    | string | `nokodo-ai:taskiq:schedules` | write-locked | Redis key prefix for dynamic TaskIQ schedules.      |

---

### Security (`NOKODO__SECURITY__*`)

| Variable                                        | Type      | Default                                                      | Flags                 | Description                                                                                                                                         |
| ----------------------------------------------- | --------- | ------------------------------------------------------------ | --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NOKODO__SECURITY__SECRET_KEY`                  | string    | `changeme`                                                   | private, write-locked | Application secret key used for JWT signing. **Must be changed in production.**                                                                     |
| `NOKODO__SECURITY__JWT_ALGORITHM`               | string    | `HS256`                                                      | write-locked          | JWT signing algorithm.                                                                                                                              |
| `NOKODO__SECURITY__ENABLE_OAUTH`                | bool      | `true`                                                       | write-locked          | Enable OAuth support.                                                                                                                               |
| `NOKODO__SECURITY__CORS_ORIGINS`                | list[str] | `["http://localhost:888","http://localhost:8383"]`           | write-locked          | Allowed CORS origins. Accepts comma-separated string or JSON array.                                                                                 |
| `NOKODO__SECURITY__CORS_ORIGINS_REGEX`          | list[str] | `["^https?://.*\\.local:888$","^https?://.*\\.local:8383$"]` | write-locked          | Regex patterns for CORS origin matching. Must be set as a JSON array string.                                                                        |
| `NOKODO__SECURITY__ALLOWED_HOSTS`               | list[str] | `["localhost","0.0.0.0","127.0.0.1",".local"]`               | write-locked          | Allowed host patterns for origin/CSRF validation. Supports `*`, leading-dot domains (`.local`), and exact hostnames. Comma-separated or JSON array. |
| `NOKODO__SECURITY__ALLOW_SIGNUPS`               | bool      | `true`                                                       |                       | Allow new user self-registration.                                                                                                                   |
| `NOKODO__SECURITY__AUTO_SIGNUP_ROLE_IDS`        | list[str] | `null`                                                       |                       | Role IDs auto-applied to new signups. JSON array.                                                                                                   |
| `NOKODO__SECURITY__ACCESS_TOKEN_EXPIRE_MINUTES` | int       | `30`                                                         |                       | Access token lifetime in minutes.                                                                                                                   |
| `NOKODO__SECURITY__REFRESH_TOKEN_EXPIRE_DAYS`   | int       | `90`                                                         |                       | Refresh token lifetime in days.                                                                                                                     |
| `NOKODO__SECURITY__AUTH_COOKIE_SECURE`          | bool      | `true`                                                       |                       | Set `Secure` flag on auth cookies. Set `false` for HTTP-only dev environments.                                                                      |
| `NOKODO__SECURITY__SESSION_TIMEOUT_MINUTES`     | int       | `30`                                                         |                       | Inactivity session timeout in minutes (min: 5).                                                                                                     |
| `NOKODO__SECURITY__REQUIRE_EMAIL_VERIFICATION`  | bool      | `true`                                                       |                       | Require users to verify their email address.                                                                                                        |
| `NOKODO__SECURITY__ALLOWED_EMAIL_DOMAINS`       | list[str] | `[]`                                                         |                       | Restrict signups to specific email domains. Empty = all domains allowed.                                                                            |

#### OIDC (`NOKODO__SECURITY__OIDC__*`)

| Variable                                | Type      | Default                        | Flags   | Description                                                                                          |
| --------------------------------------- | --------- | ------------------------------ | ------- | ---------------------------------------------------------------------------------------------------- |
| `NOKODO__SECURITY__OIDC__ENABLED`       | bool      | `false`                        |         | Enable OIDC authentication. Requires all fields below to be set.                                     |
| `NOKODO__SECURITY__OIDC__ISSUER_URL`    | URL       | `null`                         |         | OIDC issuer URL (e.g. `https://accounts.google.com`).                                                |
| `NOKODO__SECURITY__OIDC__CLIENT_ID`     | string    | `null`                         |         | OIDC client ID.                                                                                      |
| `NOKODO__SECURITY__OIDC__CLIENT_SECRET` | string    | `null`                         | private | OIDC client secret.                                                                                  |
| `NOKODO__SECURITY__OIDC__REDIRECT_URI`  | URL       | `null`                         |         | OIDC redirect URI (must match your provider configuration).                                          |
| `NOKODO__SECURITY__OIDC__SCOPES`        | list[str] | `["openid","profile","email"]` |         | OIDC scopes to request. JSON array.                                                                  |
| `NOKODO__SECURITY__OIDC__ONLY`          | bool      | `false`                        |         | Disable password login and require OIDC only. Requires `OIDC__ENABLED=true` and all OIDC fields set. |

---

### Branding (`NOKODO__BRANDING__*`)

| Variable                                   | Type   | Default   | Flags                 | Description                                                                                                                                                                                                                                                      |
| ------------------------------------------ | ------ | --------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NOKODO__BRANDING__SITE_NAME`              | string | `nokodo`  |                       | Display name for the application.                                                                                                                                                                                                                                |
| `NOKODO__BRANDING__APP_VERSION`            | string | `0.1.0`   | write-locked          | Backend version string. Set by CI/CD.                                                                                                                                                                                                                            |
| `NOKODO__BRANDING__PRIMARY_COLOR`          | string | `#6366f1` |                       | Primary brand color (hex).                                                                                                                                                                                                                                       |
| `NOKODO__BRANDING__LOGO_URL`               | URL    | `null`    |                       | Logo URL.                                                                                                                                                                                                                                                        |
| `NOKODO__BRANDING__FAVICON_URL`            | URL    | `null`    |                       | Favicon URL.                                                                                                                                                                                                                                                     |
| `NOKODO__BRANDING__SUPPORT_EMAIL`          | string | `null`    |                       | Support email shown to users awaiting account approval.                                                                                                                                                                                                          |
| `NOKODO__BRANDING__ADMIN_EMAIL`            | string | `null`    |                       | Internal/escalation admin email.                                                                                                                                                                                                                                 |
| `NOKODO__BRANDING__PUBLIC_FRONTEND_ORIGIN` | URL    | `null`    |                       | Public frontend origin (e.g. `https://app.example.com`). Used for link generation. Blank falls back to the request origin host with the default frontend port `888`; if no request origin is available, the API origin is assumed to be `http://localhost:1383`. |
| `NOKODO__BRANDING__PUBLIC_CDN_ORIGIN`      | URL    | `null`    |                       | Public CDN origin used by assets whose source is `cdn`.                                                                                                                                                                                                          |
| `NOKODO__BRANDING__PUBLIC_CONSOLE_ORIGIN`  | URL    | `null`    |                       | Public admin console origin.                                                                                                                                                                                                                                     |
| `NOKODO__BRANDING__PWA_MANIFEST_URL`       | URL    | `null`    |                       | External PWA manifest.json URL.                                                                                                                                                                                                                                  |
| `NOKODO__BRANDING__ANALYTICS_KEY`          | string | `null`    | private, write-locked | Analytics provider key (env-only, never returned to clients).                                                                                                                                                                                                    |

Generated manifest asset controls live under `NOKODO__BRANDING__PWA_ASSETS__*`.
Each asset has `SOURCE` (`default`, `cdn`, `custom`, or `disabled`) and `URL`
(full custom URL override). See [pwa-cdn-setup.md](pwa-cdn-setup.md) for
the full asset list and path map.

---

### Media (`NOKODO__MEDIA__*`)

Used to serve frontend media tags. Each asset has `SOURCE` (`default`, `cdn`,
or `custom`) and `URL` (full custom URL override). `cdn` uses
`NOKODO__BRANDING__PUBLIC_CDN_ORIGIN` plus the well-known path documented in
[pwa-cdn-setup.md](pwa-cdn-setup.md).

| Variable                                  | Type | Default   | Description                      |
| ----------------------------------------- | ---- | --------- | -------------------------------- |
| `NOKODO__MEDIA__FAVICON__SOURCE`          | enum | `default` | Browser tab favicon source.      |
| `NOKODO__MEDIA__FAVICON__URL`             | URL  | `null`    | Custom browser tab favicon URL.  |
| `NOKODO__MEDIA__APPLE_TOUCH_ICON__SOURCE` | enum | `default` | iOS home-screen icon source.     |
| `NOKODO__MEDIA__APPLE_TOUCH_ICON__URL`    | URL  | `null`    | Custom iOS home-screen icon URL. |
| `NOKODO__MEDIA__SIDEBAR_LOGO__SOURCE`     | enum | `default` | Sidebar logo source.             |
| `NOKODO__MEDIA__SIDEBAR_LOGO__URL`        | URL  | `null`    | Custom sidebar logo URL.         |
| `NOKODO__MEDIA__SPLASH_LOGO__SOURCE`      | enum | `default` | Splash logo source.              |
| `NOKODO__MEDIA__SPLASH_LOGO__URL`         | URL  | `null`    | Custom splash logo URL.          |

---

### Limits (`NOKODO__LIMITS__*`)

| Variable                                         | Type | Default | Description                         |
| ------------------------------------------------ | ---- | ------- | ----------------------------------- |
| `NOKODO__LIMITS__MAX_THREADS_PER_USER`           | int  | `100`   | Maximum chat threads per user.      |
| `NOKODO__LIMITS__MAX_MESSAGES_PER_THREAD`        | int  | `1000`  | Maximum messages per thread.        |
| `NOKODO__LIMITS__MAX_FILE_SIZE_MB`               | int  | `50`    | Maximum upload file size in MB.     |
| `NOKODO__LIMITS__RATE_LIMIT_REQUESTS_PER_MINUTE` | int  | `60`    | API rate limit per minute per user. |

---

### UI defaults (`NOKODO__UI__*`)

| Variable                            | Type   | Default     | Description                                           |
| ----------------------------------- | ------ | ----------- | ----------------------------------------------------- |
| `NOKODO__UI__DEFAULT_THEME`         | string | `system`    | Default UI color theme: `light`, `dark`, or `system`. |
| `NOKODO__UI__DEFAULT_BACKGROUND`    | string | `darkveil`  | Default app background style.                         |
| `NOKODO__UI__AUTH_PAGES_BACKGROUND` | string | `lightrays` | Background for login/signup pages.                    |
| `NOKODO__UI__SIDEBAR_COLLAPSED`     | bool   | `false`     | Default sidebar collapsed state.                      |

---

### AI (`NOKODO__AI__*`)

#### General

| Variable                        | Type      | Default | Description                                                     |
| ------------------------------- | --------- | ------- | --------------------------------------------------------------- |
| `NOKODO__AI__DEFAULT_AGENT_IDS` | list[str] | `[]`    | Ordered list of default agent IDs (tried in order). JSON array. |

#### Memory (`NOKODO__AI__MEMORY__*`)

| Variable                                   | Type  | Default | Description                                                               |
| ------------------------------------------ | ----- | ------- | ------------------------------------------------------------------------- |
| `NOKODO__AI__MEMORY__ENABLE_MEMORY`        | bool  | `true`  | Enable persistent AI memory.                                              |
| `NOKODO__AI__MEMORY__SIMILARITY_THRESHOLD` | float | `0.65`  | Minimum similarity (0.0-1.0) for memory retrieval. Lower = more memories. |
| `NOKODO__AI__MEMORY__TOP_K`                | int   | `15`    | Number of relevant memories to retrieve per query.                        |
| `NOKODO__AI__MEMORY__MESSAGES_TO_CONSIDER` | int   | `4`     | Recent messages considered when retrieving/consolidating memories.        |

#### Chat context (`NOKODO__AI__CHAT_CONTEXT__*`)

| Variable                          | Type                               | Default  | Description                                                |
| --------------------------------- | ---------------------------------- | -------- | ---------------------------------------------------------- |
| `NOKODO__AI__CHAT_CONTEXT__MODE`  | `recent` \| `relevant` \| `pinned` | `recent` | Strategy for selecting chats for agent context enrichment. |
| `NOKODO__AI__CHAT_CONTEXT__TOP_K` | int                                | `3`      | Number of chats to inject as context.                      |

#### Background task models (`NOKODO__AI__TASKS__*`)

| Variable                                         | Type   | Default | Description                                                                   |
| ------------------------------------------------ | ------ | ------- | ----------------------------------------------------------------------------- |
| `NOKODO__AI__TASKS__DEFAULT_MODEL_ID`            | string | `null`  | Fallback model ID for all background AI tasks.                                |
| `NOKODO__AI__TASKS__THREAD_METADATA_MODEL_ID`    | string | `null`  | Model for thread title/tag generation. Falls back to `DEFAULT_MODEL_ID`.      |
| `NOKODO__AI__TASKS__THREAD_MAINTENANCE_MODEL_ID` | string | `null`  | Model for inactive thread metadata/summary. Falls back to `DEFAULT_MODEL_ID`. |
| `NOKODO__AI__TASKS__INPUT_AUTOCOMPLETE_MODEL_ID` | string | `null`  | Model for input autocomplete suggestions. Falls back to `DEFAULT_MODEL_ID`.   |

#### Attachment decay (`NOKODO__AI__ATTACHMENTS__*`)

Decay is measured in iterations (one agent-loop step, i.e. one assistant
message, within the same agent turn), not turns.

| Variable                                          | Type | Default | Description                                                         |
| ------------------------------------------------- | ---- | ------- | ------------------------------------------------------------------- |
| `NOKODO__AI__ATTACHMENTS__IMAGE_DECAY_ITERATIONS` | int  | `3`     | Iterations before image attachments decay from native to reference. |
| `NOKODO__AI__ATTACHMENTS__AUDIO_DECAY_ITERATIONS` | int  | `3`     | Iterations before audio attachments decay.                          |
| `NOKODO__AI__ATTACHMENTS__VIDEO_DECAY_ITERATIONS` | int  | `1`     | Iterations before video attachments decay.                          |

#### Context compaction (`NOKODO__AI__CONTEXT_COMPACTION__*`)

| Variable                                                          | Type  | Default  | Description                                                     |
| ----------------------------------------------------------------- | ----- | -------- | --------------------------------------------------------------- |
| `NOKODO__AI__CONTEXT_COMPACTION__ENABLED`                         | bool  | `true`   | Enable token-aware context compaction and summarization.        |
| `NOKODO__AI__CONTEXT_COMPACTION__TRIGGER_RATIO`                   | float | `0.70`   | Token budget fraction at which background summarization starts. |
| `NOKODO__AI__CONTEXT_COMPACTION__MAX_SUMMARIES_BEFORE_CONDENSE`   | int   | `4`      | Condense existing summaries into one when this many accumulate. |
| `NOKODO__AI__CONTEXT_COMPACTION__PROMPT_OVERHEAD_TOKENS`          | int   | `300`    | Prompt framing and provider overhead budget.                    |
| `NOKODO__AI__CONTEXT_COMPACTION__TOOL_RESULT_MAX_SHARE`           | float | `0.25`   | Max fraction of budget a single tool result may consume.        |
| `NOKODO__AI__CONTEXT_COMPACTION__TOOL_RESULT_HARD_CAP`            | int   | `100000` | Absolute character ceiling per tool result.                     |
| `NOKODO__AI__CONTEXT_COMPACTION__TOOL_RESULTS_COMBINED_MAX_SHARE` | float | `0.50`   | Max fraction of budget for all tool results combined.           |
| `NOKODO__AI__CONTEXT_COMPACTION__RESPONSE_HEADROOM`               | int   | `4096`   | Tokens reserved for the model's response.                       |

---

### Assets (`NOKODO__ASSETS__*`)

#### General

| Variable                                     | Type   | Default | Description                              |
| -------------------------------------------- | ------ | ------- | ---------------------------------------- |
| `NOKODO__ASSETS__DEFAULT_EMBEDDING_MODEL_ID` | string | `null`  | Default embedding model ID (`Model.id`). |

#### Vector database (`NOKODO__ASSETS__VECTOR_DATABASE__*`)

| Variable                                               | Type   | Default       | Flags   | Description                                                                                                      |
| ------------------------------------------------------ | ------ | ------------- | ------- | ---------------------------------------------------------------------------------------------------------------- |
| `NOKODO__ASSETS__VECTOR_DATABASE__PROVIDER`            | string | `qdrant`      |         | Vector DB provider: `qdrant`, `chroma`, `pinecone`, `weaviate`, `milvus`, `pgvector`, `redis`, `opensearch`.     |
| `NOKODO__ASSETS__VECTOR_DATABASE__QDRANT__URL`         | string | `qdrant:6334` |         | Qdrant endpoint. Scheme-less `host:port` targets the gRPC port when `USE_GRPC=true`.                             |
| `NOKODO__ASSETS__VECTOR_DATABASE__QDRANT__USE_GRPC`    | bool   | `true`        |         | Prefer Qdrant gRPC transport. When enabled, the REST port stays on the client default unless you use a full URL. |
| `NOKODO__ASSETS__VECTOR_DATABASE__QDRANT__API_KEY`     | string | `null`        | private | Qdrant API key.                                                                                                  |
| `NOKODO__ASSETS__VECTOR_DATABASE__CHROMA__URL`         | string | `null`        |         | Chroma endpoint URL stub.                                                                                        |
| `NOKODO__ASSETS__VECTOR_DATABASE__CHROMA__API_KEY`     | string | `null`        | private | Chroma API key stub.                                                                                             |
| `NOKODO__ASSETS__VECTOR_DATABASE__PINECONE__URL`       | string | `null`        |         | Pinecone endpoint URL stub.                                                                                      |
| `NOKODO__ASSETS__VECTOR_DATABASE__PINECONE__API_KEY`   | string | `null`        | private | Pinecone API key.                                                                                                |
| `NOKODO__ASSETS__VECTOR_DATABASE__WEAVIATE__URL`       | string | `null`        |         | Weaviate endpoint URL stub.                                                                                      |
| `NOKODO__ASSETS__VECTOR_DATABASE__WEAVIATE__API_KEY`   | string | `null`        | private | Weaviate API key.                                                                                                |
| `NOKODO__ASSETS__VECTOR_DATABASE__MILVUS__URL`         | string | `null`        |         | Milvus endpoint URL stub.                                                                                        |
| `NOKODO__ASSETS__VECTOR_DATABASE__MILVUS__TOKEN`       | string | `null`        | private | Milvus token.                                                                                                    |
| `NOKODO__ASSETS__VECTOR_DATABASE__PGVECTOR__URL`       | string | `null`        |         | Pgvector connection URL stub.                                                                                    |
| `NOKODO__ASSETS__VECTOR_DATABASE__REDIS__URL`          | string | `null`        |         | Redis endpoint URL stub.                                                                                         |
| `NOKODO__ASSETS__VECTOR_DATABASE__REDIS__PASSWORD`     | string | `null`        | private | Redis password.                                                                                                  |
| `NOKODO__ASSETS__VECTOR_DATABASE__OPENSEARCH__URL`     | string | `null`        |         | OpenSearch endpoint URL stub.                                                                                    |
| `NOKODO__ASSETS__VECTOR_DATABASE__OPENSEARCH__API_KEY` | string | `null`        | private | OpenSearch API key.                                                                                              |

#### Vector search tuning (`NOKODO__ASSETS__VECTOR__*`)

| Variable                                         | Type            | Default                   | Description                                                                               |
| ------------------------------------------------ | --------------- | ------------------------- | ----------------------------------------------------------------------------------------- |
| `NOKODO__ASSETS__VECTOR__COLLECTION_TEMPLATE`    | string          | `nokodo-ai__{model}_bm25` | Collection name template. `{model}` is replaced with the slugified embedding model name.  |
| `NOKODO__ASSETS__VECTOR__SPARSE_VECTORS_ENABLED` | bool            | `true`                    | Enable BM25 sparse vectors for hybrid search.                                             |
| `NOKODO__ASSETS__VECTOR__FUSION_ALGORITHM`       | `rrf` \| `dbsf` | `rrf`                     | Score fusion: `rrf` (reciprocal rank fusion) or `dbsf` (distribution-based score fusion). |
| `NOKODO__ASSETS__VECTOR__NORMALIZE_SCORES`       | bool            | `true`                    | Normalize fused scores to 0-1 range.                                                      |

#### Embeddings (`NOKODO__ASSETS__EMBEDDINGS__*`)

| Variable                                  | Type | Default | Description                                   |
| ----------------------------------------- | ---- | ------- | --------------------------------------------- |
| `NOKODO__ASSETS__EMBEDDINGS__VECTOR_SIZE` | int  | `1536`  | Vector dimension for the embedding model.     |
| `NOKODO__ASSETS__EMBEDDINGS__BATCH_SIZE`  | int  | `64`    | Batch size for embedding generation (1-4096). |

#### Reranking (`NOKODO__ASSETS__RERANK__*`)

| Variable                                   | Type   | Default  | Description                                                  |
| ------------------------------------------ | ------ | -------- | ------------------------------------------------------------ |
| `NOKODO__ASSETS__RERANK__DEFAULT_STRATEGY` | string | `native` | Default reranking strategy: `none`, `native`, or `external`. |
| `NOKODO__ASSETS__RERANK__TOP_K`            | int    | `10`     | Results to keep after reranking (1-100).                     |

#### Storage (`NOKODO__ASSETS__STORAGE__*`)

| Variable                           | Type            | Default | Description                                                        |
| ---------------------------------- | --------------- | ------- | ------------------------------------------------------------------ |
| `NOKODO__ASSETS__STORAGE__BACKEND` | `local` \| `s3` | `local` | Active storage backend. Only the selected backend is instantiated. |

**Local storage** (`NOKODO__ASSETS__STORAGE__LOCAL__*`):

| Variable                                    | Type   | Default        | Description                            |
| ------------------------------------------- | ------ | -------------- | -------------------------------------- |
| `NOKODO__ASSETS__STORAGE__LOCAL__ROOT_PATH` | string | `data/uploads` | Root directory for local file uploads. |

**S3-compatible storage** (`NOKODO__ASSETS__STORAGE__S3__*`) — defaults target the dev MinIO container:

| Variable                                            | Type                                 | Default                 | Flags                | Description                                                   |
| --------------------------------------------------- | ------------------------------------ | ----------------------- | -------------------- | ------------------------------------------------------------- |
| `NOKODO__ASSETS__STORAGE__S3__ENDPOINT_URL`         | string                               | `http://localhost:9000` |                      | S3-compatible endpoint. Set to empty/null for AWS S3.         |
| `NOKODO__ASSETS__STORAGE__S3__BUCKET`               | string                               | `nokodo-ai`             |                      | S3 bucket name.                                               |
| `NOKODO__ASSETS__STORAGE__S3__REGION`               | string                               | `us-east-1`             |                      | AWS region.                                                   |
| `NOKODO__ASSETS__STORAGE__S3__ACCESS_KEY_ID`        | string                               | `minioadmin`            | private              | S3 access key ID.                                             |
| `NOKODO__ASSETS__STORAGE__S3__SECRET_ACCESS_KEY`    | string                               | `minioadmin`            | private              | S3 secret access key.                                         |
| `NOKODO__ASSETS__STORAGE__S3__PREFIX`               | string                               | ``                      |                      | Key prefix within the bucket.                                 |
| `NOKODO__ASSETS__STORAGE__S3__PRESIGNED_URL_TTL`    | int                                  | `3600`                  |                      | Presigned URL expiry in seconds.                              |
| `NOKODO__ASSETS__STORAGE__S3__MULTIPART_THRESHOLD`  | int                                  | `104857600`             |                      | Bytes above which multipart upload is used (default: 100 MB). |
| `NOKODO__ASSETS__STORAGE__S3__MULTIPART_CHUNK_SIZE` | int                                  | `10485760`              |                      | Multipart chunk size in bytes (default: 10 MB).               |
| `NOKODO__ASSETS__STORAGE__S3__MAX_RETRIES`          | int                                  | `3`                     |                      | Max S3 retry attempts.                                        |
| `NOKODO__ASSETS__STORAGE__S3__RETRY_MODE`           | `legacy` \| `standard` \| `adaptive` | `adaptive`              | Botocore retry mode. |

---

### Soft-delete (`NOKODO__SOFT_DELETE__*`)

| Variable                       | Type | Default | Description                                                       |
| ------------------------------ | ---- | ------- | ----------------------------------------------------------------- |
| `NOKODO__SOFT_DELETE__THREADS` | bool | `true`  | Soft-delete threads (sets `deleted_at`) instead of hard-deleting. |
| `NOKODO__SOFT_DELETE__NOTES`   | bool | `true`  | Soft-delete notes.                                                |
| `NOKODO__SOFT_DELETE__FILES`   | bool | `true`  | Soft-delete files.                                                |

---

### Default permissions (`NOKODO__DEFAULT_PERMISSIONS__*`)

| Variable                                          | Type      | Default   | Description                                                                |
| ------------------------------------------------- | --------- | --------- | -------------------------------------------------------------------------- |
| `NOKODO__DEFAULT_PERMISSIONS__ACTION_PERMISSIONS` | list[str] | see below | Default action permissions granted to all authenticated users. JSON array. |

Default action permissions: `SETTINGS_READ`, `THREADS_CREATE`, `PROJECTS_CREATE`, `NOTES_CREATE`, `GROUPS_CREATE`, `REMINDERS_CREATE`, `MEMORIES_CREATE`, `TASKS_CREATE`, `FILES_CREATE`.

---

## Loading order

Settings are resolved in this priority order (highest wins):

1. Programmatic `init_settings` (test overrides)
2. Database (`DbSettingsSource`) - only admin-writable fields
3. Environment variables
4. `.env` file
5. Secret files (`pydantic_settings` file secret source)

Boot settings (`BootSettings`) only load from env and `.env`.

---

## Notes

- **JSON arrays** can be passed as a JSON array string: `NOKODO__SECURITY__CORS_ORIGINS='["https://a.com","https://b.com"]'`
- **Comma-separated strings** are also accepted for `cors_origins` and `allowed_hosts`: `NOKODO__SECURITY__CORS_ORIGINS=https://a.com,https://b.com`
- **Write-locked** fields cannot be updated via the API. They can only be changed via environment variables and require a server restart.
- **Private** fields are excluded from non-admin API GET `/settings` responses.
