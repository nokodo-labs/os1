# API Type Safety

Modern type-safe API architecture using OpenAPI TypeScript generation.

## Architecture

```
FastAPI OpenAPI Schema → openapi-typescript → TypeScript Types → Type-safe API Calls
```

## Benefits

-   **Zero Dependencies**: Native fetch, no axios or HTTP libraries
-   **Full Type Safety**: Compile-time errors for invalid API calls
-   **Auto-sync**: Backend changes automatically reflected in frontend types
-   **Modern**: Built on web standards (fetch, async/await)
-   **Future-proof**: No external HTTP library to become outdated

## Setup

### 1. Start Backend

```bash
cd backend
uvicorn api.main:app --reload
```

Backend serves OpenAPI schema at: `http://localhost:8000/v1/openapi.json`

### 2. Generate Types

```bash
cd frontend
npm run generate:api-types
```

This generates `src/lib/api/types.ts` from the OpenAPI schema.

## Usage

### Basic API Calls

```typescript
import { api } from "$lib/api";

// All fully typed from OpenAPI schema
const users = await api.getUsers({ skip: 0, limit: 10 });
const user = await api.getUser(1);
const newUser = await api.createUser({
	email: "test@example.com",
	username: "test",
	password: "password123",
});
```

### In Svelte Components

```svelte
<script lang="ts">
  import { api, type User } from '$lib/api'

  let users = $state<User[]>([])
  let loading = $state(false)

  async function loadUsers() {
    loading = true
    try {
      users = await api.getUsers()
    } catch (error) {
      console.error('Failed to load users:', error)
    } finally {
      loading = false
    }
  }
</script>

<button onclick={loadUsers} disabled={loading}>
  {loading ? 'Loading...' : 'Load Users'}
</button>

{#each users as user}
  <div>{user.username} - {user.email}</div>
{/each}
```

### Error Handling

```typescript
import { api, APIError } from "$lib/api";

try {
	const user = await api.getUser(999);
} catch (error) {
	if (error instanceof APIError) {
		console.error(`API Error (${error.status}):`, error.message);
		// Access full response
		console.log("Details:", error.response);
	}
}
```

### Advanced: Direct Client

```typescript
import { apiClient } from "$lib/api";

// For custom endpoints not in api.ts
const data = await apiClient.get<CustomType>("/custom-endpoint", {
	params: { filter: "value" },
});

// All HTTP methods available
await apiClient.post("/endpoint", { data: "value" });
await apiClient.put("/endpoint", { data: "value" });
await apiClient.patch("/endpoint", { data: "value" });
await apiClient.delete("/endpoint");
```

## Workflow

### Adding New Endpoints

1. **Add backend endpoint** in FastAPI:

```python
@router.get("/items")
async def get_items() -> list[Item]:
    return items
```

2. **Regenerate types**:

```bash
npm run generate:api-types
```

3. **Add typed function** in `frontend/src/lib/api/index.ts`:

```typescript
async getItems(): Promise<Item[]> {
	return apiClient.get<Item[]>('/items')
}
```

4. **Use with full type safety**:

```typescript
const items = await api.getItems(); // Fully typed!
```

### Type Safety Benefits

```typescript
// ✅ Valid - compiles
const user = await api.getUser(1);
console.log(user.email); // TypeScript knows user.email exists

// ❌ Invalid - won't compile
const user = await api.getUser("invalid"); // Error: argument must be number
console.log(user.invalidField); // Error: property doesn't exist

// ✅ Create user with validation
await api.createUser({
	email: "test@example.com",
	username: "test",
	password: "pass123",
}); // TypeScript enforces required fields

// ❌ Missing field - won't compile
await api.createUser({
	email: "test@example.com",
	// Error: username and password required
});
```

## Files

-   `src/lib/api/client.ts` - Base fetch client with error handling
-   `src/lib/api/types.ts` - **Auto-generated** (DO NOT EDIT MANUALLY)
-   `src/lib/api/index.ts` - Typed API functions for all endpoints

## Troubleshooting

### Backend not running

```
Error: fetch failed
```

Start backend: `cd backend && uvicorn api.main:app --reload`

### Types out of sync

```typescript
// Type error after backend changes
```

Regenerate: `npm run generate:api-types`

### Type generation fails

Check that:

-   Backend is running on `http://localhost:8000`
-   OpenAPI endpoint is accessible: `http://localhost:8000/v1/openapi.json`
-   `openapi-typescript` is installed: `npm install`

## Why Not Axios?

-   **Native fetch** is the web standard (2025)
-   **Zero dependencies** = future-proof
-   **Better streaming** support with fetch
-   **Smaller bundle** size
-   **Type safety** via OpenAPI generation > manual typing
-   **Auto-sync** backend/frontend types

Modern approach: Let OpenAPI handle types, let fetch handle requests.
