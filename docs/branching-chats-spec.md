# Branching Chats

## Core Concept

A branching chat is a **tree of messages**, not a list.  
Each message knows its parent; the "current conversation" is one root→leaf path.

```
         [user-1]
            │
       [assistant-1]
         /       \
    [user-2]    [user-3]   ← fork (edit / regenerate)
        │           │
  [asst-2]      [asst-3]
```

Forking isn't special — you just insert a new message whose `parent_id` points to any existing node.

---

## 1 · Database

```sql
CREATE TABLE chat (
    id          UUID PRIMARY KEY,
    user_id     UUID NOT NULL,
    title       TEXT,
    current_id  UUID,  -- active leaf; FK added after message table exists
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE message (
    id          UUID PRIMARY KEY,
    chat_id     UUID NOT NULL REFERENCES chat(id) ON DELETE CASCADE,
    parent_id   UUID REFERENCES message(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,  -- 'user' | 'assistant' | 'system'
    content     JSONB NOT NULL,
    model       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE chat
    ADD CONSTRAINT fk_chat_current
    FOREIGN KEY (current_id) REFERENCES message(id) ON DELETE SET NULL;

CREATE INDEX idx_message_chat   ON message(chat_id);
CREATE INDEX idx_message_parent ON message(parent_id);
```

The tree is **implicit** in `parent_id`. You never store structure explicitly.

---

## 2 · Backend

### get current branch (LLM context)

```python
def get_branch(db, chat_id: UUID) -> list[Message]:
    chat = db.get(Chat, chat_id)
    msgs, cur = [], db.get(Message, chat.current_id)
    while cur:
        msgs.insert(0, cur)
        cur = db.get(Message, cur.parent_id) if cur.parent_id else None
    return msgs
```

### add message

```python
def add_message(db, chat_id: UUID, parent_id: UUID | None,
                role: str, content, model: str | None = None) -> Message:
    msg = Message(id=uuid4(), chat_id=chat_id, parent_id=parent_id,
                  role=role, content=content, model=model)
    db.add(msg)
    chat = db.get(Chat, chat_id)
    chat.current_id = msg.id
    db.commit()
    return msg
```

### get siblings

```python
def get_siblings(db, message_id: UUID) -> list[Message]:
    msg = db.get(Message, message_id)
    return db.query(Message).filter(
        Message.parent_id == msg.parent_id,
        Message.chat_id == msg.chat_id
    ).order_by(Message.created_at).all()
```

### switch branch

```python
def switch_branch(db, chat_id: UUID, target_id: UUID):
    """Set current_id to deepest leaf descending from target."""
    leaf = target_id
    while (children := db.query(Message).filter(Message.parent_id == leaf).all()):
        leaf = children[-1].id
    db.get(Chat, chat_id).current_id = leaf
    db.commit()
```

### endpoints

| method | route                  | body / params            | returns               |
| ------ | ---------------------- | ------------------------ | --------------------- |
| `POST` | `/chats/{id}/messages` | `{ parent_id, content }` | new assistant message |
| `GET`  | `/chats/{id}/messages` | —                        | current branch (list) |
| `GET`  | `/chats/{id}/tree`     | —                        | all messages (flat)   |
| `POST` | `/chats/{id}/switch`   | `{ message_id }`         | ok                    |

---

## 3 · Frontend

### data shape

```ts
interface Message {
	id: string;
	parentId: string | null;
	childrenIds: string[]; // computed client-side
	role: "user" | "assistant" | "system";
	content: unknown;
}

interface History {
	currentId: string | null;
	messages: Record<string, Message>;
}
```

### build tree from flat array

```ts
function buildHistory(msgs: Message[], currentId: string): History {
	const messages: Record<string, Message> = {};
	for (const m of msgs) messages[m.id] = { ...m, childrenIds: [] };
	for (const m of msgs) {
		if (m.parentId) messages[m.parentId]?.childrenIds.push(m.id);
	}
	return { currentId, messages };
}
```

### get current branch

```ts
function getBranch(h: History): Message[] {
	const result: Message[] = [];
	let cur = h.currentId ? h.messages[h.currentId] : null;
	while (cur) {
		result.unshift(cur);
		cur = cur.parentId ? h.messages[cur.parentId] : null;
	}
	return result;
}
```

### sibling navigation

```ts
function getSiblings(h: History, id: string): string[] {
	const m = h.messages[id];
	if (!m.parentId)
		return Object.values(h.messages)
			.filter((x) => !x.parentId)
			.map((x) => x.id);
	return h.messages[m.parentId].childrenIds;
}

function siblingAt(h: History, id: string, delta: number): string {
	const sibs = getSiblings(h, id);
	return sibs[
		Math.max(0, Math.min(sibs.length - 1, sibs.indexOf(id) + delta))
	];
}
```

### svelte flow graph

```ts
function toFlowGraph(h: History) {
	const nodes = Object.values(h.messages).map((m) => ({
		id: m.id,
		type: "message",
		data: { message: m },
		position: { x: 0, y: 0 },
	}));
	const edges = Object.values(h.messages)
		.filter((m) => m.parentId)
		.map((m) => ({
			id: `${m.parentId}-${m.id}`,
			source: m.parentId!,
			target: m.id,
		}));
	return { nodes, edges };
}
```

---

## summary

| layer        | what you need                                                          |
| ------------ | ---------------------------------------------------------------------- |
| **DB**       | `message.parent_id` + `chat.current_id`                                |
| **Backend**  | walk `parent_id` for context; update `current_id` on every new message |
| **Frontend** | compute `childrenIds` on load; navigate by changing `currentId`        |
