# stores

svelte 5 reactive stores for frontend state. all stores use `$state` runes (no writable/readable Svelte 4 stores).

---

## store categories

### api cache stores

class instances backed by API data. follow a standard lifecycle contract:

| method         | description                                                                         |
| -------------- | ----------------------------------------------------------------------------------- |
| `init()`       | subscribe to event stream + start initial fetch                                     |
| `cleanup()`    | unsubscribe from event stream + wipe state                                          |
| `load()`       | fetch / re-fetch from API (no state wipe)                                           |
| `invalidate()` | mark data stale (soft reset, no blob revocation) so the next `load()` fetches fresh |
| `clear()`      | immediately wipe all local state (full reset, revokes blob URLs where applicable)   |

stores: `agents`, `chat`, `files`, `friends`, `groups`, `notes`, `notifications`, `permissions`, `preferences`, `projects`, `reminders`

> `settings` uses free functions (`loadSettings`, `invalidateSettings`, `clearSettings`) instead of a class - it is functionally equivalent.

**lifecycle wiring** is centralized in `src/lib/init.ts`:

- `init()` is called after auth token is available
- `cleanup()` and `clear()` are called on logout / token change
- `invalidate()` is called on WS disconnect (missed events = stale data)

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

`notifications` doubles as the **event fanout hub** - all SSE stream messages flow through it. it also owns the toast queue.

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
