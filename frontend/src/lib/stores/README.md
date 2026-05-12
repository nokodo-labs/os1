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

stores: `activeRuns`, `agents`, `chat`, `files`, `friends`, `groups`, `notes`, `notifications`, `permissions`, `projects`, `reminders`, `resourceAccess`, `settings`

composite resources track their own loaded scopes behind the same top-level API:
`projects.refresh()` refreshes loaded project counts, `reminders.refresh()` refreshes
loaded lists/counts/reminder lists, `files.refresh()` refreshes loaded filters and
counts, and `resourceAccess.refresh()` refreshes loaded access levels/rules.

**lifecycle wiring** is centralized in `src/lib/stores/apiCacheRegistry.ts` and consumed by `src/lib/init.ts`:

- `cleanup()` and `clear()` are called on logout / token change
- `invalidate()` is called on WS disconnect, blur/hidden, resume, and execution gaps
- lifecycle invalidation never refetches by itself; owning pages/components call `load()`, `ensure()`, or `refresh()` when the data is actually needed again

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
