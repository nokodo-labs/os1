# 📎 nokodo native attachment system — technical spec

## 1. philosophy

attachments are **resources**, not messages. they have a **relevance window** and should not burn tokens when they're no longer contextually needed. the system optimizes cost while preserving full access at any time.

---

## 2. attachment types

| type           | handling                                                                                                                                                                                    |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **native**     | modalities the model supports natively (image, audio, video). can be sent directly in context                                                                                               |
| **non-native** | everything else (pdf, csv, code files, etc.). ALWAYS sent as reference. accessed via dedicated tools (`search_attachment`, `read_attachment`). **separate concern — not part of this spec** |

> NOTE: "native" status is a RUNTIME property, computed based on attachment file type and available ChatModel native modalities for the selected Agent.

---

## 3. attachment states

every native attachment in a chat is in one of two states:

- **🟢 active** — the full file is included in LLM context at its original message position
- **🔘 reference** — a lightweight JSON summary is included instead. the model knows the attachment exists but cannot see it

---

## 4. auto-decay system

- attachments start as **active** on upload
- after **N turns**, they auto-decay to **reference**
- **N is configurable per type** in user/system settings:
    - `image_decay_turns`: default 3–5
    - `audio_decay_turns`: default 2–4
    - `video_decay_turns`: default 1–2
- decay is **silent** — no notifications, UI just updates visually

---

## 5. async summarization

- triggered **immediately on upload**, runs asynchronously
- uses a **cheap task model** with the relevant modality
- produces a short text description of the attachment
- summary is stored with the attachment metadata and used in the reference object
- must complete before decay can kick in (summary is required for reference)

---

## 6. reference schema

when an attachment is in reference state, the model receives something like:

```json
{
	"type": "image",
	"id": "att_29fka",
	"status": "reference",
	"original_message_index": 3,
	"summary": "screenshot of a database schema with 4 tables: users, chats, messages, attachments",
	"filename": "schema_v2.png"
}
```

delivered via system prompt or equivalent injection point, similar to how memories are currently surfaced.

---

## 7. reveal tool — agent-initiated reactivation

when the model determines it needs to actually SEE a referenced attachment:

### flow:

1. model calls `reveal_attachment` tool with the attachment ID
2. system sets attachment state to **active**, reattaching it to its **original message**
3. tool returns `{ "success": true }`
4. context is reconstructed — model now sees the attachment natively on the next inference pass
5. model completes its reasoning/tasks
6. after the **run completes** (final assistant message emitted), attachment returns to reference

### decay timer reset:

- a reveal **resets the decay timer** — attachment stays active for another N turns before auto-decaying again
- prevents reveal loops where agent has to keep re-revealing on follow-up turns

### guardrails:

- batch support: tool should accept **multiple IDs** in one call to avoid multiple reconstruction passes
- instructions-level guidance to prevent unnecessary reveals (model should check summary first)

---

## 8. user-facing toggle

- users can **manually toggle** any attachment between active/reference at any time
- toggles are accessible via the **attachment tray** (see UX below)
- manual toggle to active also **resets decay timer**
- manual toggle to reference is **immediate** (no decay delay)

---

## 9. UX components

### attachment tray

- **collapsible bar** above message input, visible when chat has attachments
- shows all attachments with: status indicator, filename, summary text, toggle switch
- only appears when ≥1 attachment exists in chat

### inline message indicators

- **active attachment**: shows preview (thumbnail, player, etc.)
- **reference attachment**: shows muted pill with type icon + filename

### optional power-user feature

- token cost estimate next to active attachments in tray

---

## 10. key implementation notes

- attachment state is just a **flag** checked during context array construction (no complex runtime logic)
- context reconstruction already happens every turn — reveal/decay is just a flag flip before the build step
- all state changes (decay, reveal, toggle) modify the **same canonical attachment record** on the original message — single source of truth, no duplication
