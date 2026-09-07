# stores

svelte 5 reactive stores for frontend state. all stores use `$state` runes (no writable/readable Svelte 4 stores).

---

## store categories

### api cache stores

API-backed stores follow a standard structural contract. the contract is enforced at
the central registry with `satisfies readonly ApiCacheStore[]` rather than by a
shared superclass, because stores may be classes, object literals, or adapters.

| method         | description                                                                       |
| -------------- | --------------------------------------------------------------------------------- |
| `init()`       | subscribe to event stream + start initial fetch                                   |
| `cleanup()`    | unsubscribe from event stream                                                     |
| `load()`       | domain fetch / re-fetch API (may accept domain-specific options)                  |
| `invalidate()` | mark data stale while keeping rendered data available                             |
| `refresh()`    | explicit refetch for already-loaded cache scopes, then swap fresh data in place   |
| `clear()`      | immediately wipe all local state (full reset, revokes blob URLs where applicable) |

stores: `activeRuns`, `agents`, `chat`, `files`, `friends`, `groups`, `mcpServers`, `notes`, `notifications`, `permissions`, `projects`, `reminders`, `resourceAccess`, `settings`

#### state signals (loaded vs loading vs empty)

every list/collection cache store exposes **`hasLoaded`** so consumers never
render an empty state before the first load resolves. it flips `true` after the
first successful load and resets in `clear()`. this is the single canonical name
(no `isReady`/`ready`/`initialized` variants).

render the three states as:

- `items.length === 0 && !store.hasLoaded` -> loader
- `items.length === 0` -> empty state
- otherwise -> the list

a transient failure (error, missing token, expired cache) must keep prior data
and leave `hasLoaded` untouched - it must never present as empty.

two optional, separate signals (do not conflate with `hasLoaded`):

- `isLoading` / `loading` - a fetch is in flight; for refetch spinners. starts
  `false`, so it must not be the sole gate for the empty state.
- `hydrated` - the in-memory cache is currently populated (`fetchedAt != null`);
  unlike `hasLoaded` it can flip back when the cache is dropped (e.g. notes on
  sort change). used to pick loader-vs-stale-data during a refetch.

`shouldRefresh()` is required on every registered store: list stores return
`hasLoaded`; stores with no loaded-once collection (`activeRuns`,
`resourceAccess`) return `true`.

composite resources track their own loaded scopes behind the same top-level API:
`projects.refresh()` refreshes loaded project counts, `reminders.refresh()` refreshes
loaded lists/counts/reminder lists, `files.refresh()` refreshes loaded filters and
counts, and `resourceAccess.refresh()` refreshes loaded access levels/rules.

**lifecycle wiring** is centralized in `src/lib/stores/apiCacheRegistry.ts` and consumed by `src/lib/init.ts`:

- `cleanup()` and `clear()` are called on logout / token change
- `invalidate()` is called only when the WS actually drops (close or pong timeout): that is the one moment live data could have been missed
- when the WS re-connects (not the first connect of a boot), `refreshLifecycleStores()` runs every registered store's `shouldRefresh()` and refreshes the ones that say yes, in place; `hasLoaded` never resets, so nothing shows a skeleton
- visibility, online, bfcache restore, and event-loop freezes only send a heartbeat probe; a zombie socket then times out and takes the drop -> reconnect -> refresh path above. no hidden-duration heuristics

### websocket event contract

store event handling is centralized in `src/lib/stores/storeEvents.ts`:

- `STORE_EVENT_TYPES` is the frontend source of truth for store-relevant WS event names
- stores subscribe with `subscribeToStoreEvents()` for exact event groups or `subscribeToStoreEventPrefixes()` for intentionally broad derived windows
- payload reads should use `storeEventData()` / `storeEventString()` so handlers consistently support backend events that put ids either in `data` or at top level

event handling policy depends on resource shape:

- direct patch: event payload is the authoritative resource shape (`agents`, `notes`, calendars, reminders, chat where possible)
- item refetch: event only identifies the resource or processing status (`files`)
- full refetch: small relationship caches where partial state is easy to get wrong (`friends`, `groups`, permissions, settings)
- scoped invalidation: composite or derived caches (`projects` counts, scheduled item windows, resource access)
- stale marker only: caches with no push events of their own (`mcpServers` has no `mcp.*` events, so its mutations patch the list and `settings.updated` marks it stale)

`eventStreamClient.subscribeTypes()` and `subscribePrefixes()` route typed groups before handlers run. global `subscribe()` is reserved for generic stream consumers outside store caches.

### rollback support

state-altering mutations (create/update/remove) accept an optional `options?: { rollback?: boolean }` parameter.
rollback is enabled by default (`rollback: true`). pass `{ rollback: false }` to opt out.

stores with rollback: `notes`, `projects`, `reminders`

### ui / app-state stores

no API backing, no lifecycle. either plain `$state` objects or classes used directly:

| store           | description                                            |
| --------------- | ------------------------------------------------------ |
| `accent`        | accent color theme                                     |
| `activeRuns`    | active agent run tracking (event-driven, no API cache) |
| `appNavigation` | router-level navigation history + scroll restoration   |
| `appReadiness`  | boot-phase readiness flags                             |
| `background`    | background style (static color / dynamic)              |
| `device`        | device capabilities, GPU tier, geolocation             |
| `installPrompt` | PWA install banner                                     |
| `modals`        | modal open/close state + payloads                      |
| `network`       | online/offline status                                  |
| `pageTitle`     | current page `<title>`                                 |
| `selectedAgent` | currently selected agent for new chats                 |
| `serviceWorker` | SW update availability                                 |
| `session`       | auth session (access token, user info)                 |

---

## notifications store

`notifications` owns notification refresh/toasts and still exposes focused chat-related event fanout helpers. store-level WS routing itself lives in `storeEvents.ts`.

### toast system

`ToastItem` is a discriminated union on `type`:

```ts
type ToastItem =
  | { type: 'notification'; id: string; eventId: string; title: string; body: string; ... }
  | { type: 'ephemeral'; id: string; variant: EphemeralVariant; title: string; ... }
```

- `id` - opaque UI handle used by the toast renderer and dismiss logic
- `eventId` - only on `type === 'notification'`: the backing SSE event id, used to correlate with `Notification.event_id` for swipe-dismiss
- `variant` - only on `type === 'ephemeral'`: `'error' | 'success' | 'info' | 'warning'`

push helpers:

```ts
notifications.pushEphemeralToast('error', 'something went wrong') // returns toast id
showError('something went wrong') // convenience wrapper
```

### event fanout

other stores subscribe to specific event types via:

```ts
notifications.onThreadEvent(handler)
notifications.onMessageEvent(handler)
notifications.onNotificationEvent(handler)
```

subscriptions are cleaned up via the returned unsubscribe function.
