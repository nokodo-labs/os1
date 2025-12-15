# nokodo AI — UX specification

> the universal AI interface: clean, fluid, futuristic

---

## 🧭 design philosophy

nokodo AI is not just an AI chat app — it's evolving toward a **personal AI operating system**.

every design decision follows these principles:

| principle        | meaning                                                          |
| ---------------- | ---------------------------------------------------------------- |
| **fluidity**     | smooth transitions, physics-based motion, liquid glass aesthetic |
| **familiarity**  | consistent anchors so users never feel lost                      |
| **intelligence** | AI enhances every surface, but never overwhelms                  |
| **minimalism**   | only show what matters, hide complexity                          |

---

## 🏝️ system chrome

the **system chrome** is the persistent UI shell that anchors the entire experience — like the macOS menu bar or Windows taskbar.

nokodo AI's chrome consists of two elements:

### the island (top header)

a floating, semi-transparent header bar with **liquid glass** styling.

**structure:**

| zone                          | behavior                               |
| ----------------------------- | -------------------------------------- |
| 🏠 **home** (left)            | static — always returns to home screen |
| 📡 **activity area** (center) | dynamic — shows ongoing system events  |
| 👤 **user** (right)           | static — account, settings, profile    |

**activity area examples:**

-   🎵 music currently playing
-   🎬 AI video generation in progress
-   ⬆️ file upload status
-   ⏳ deep research session running

**dynamic adaptation:**
the island's contents adapt based on current context — additional buttons or controls appear depending on which app or page is active (similar to how macOS menu bar changes per-app).

---

### the dock (right sidebar)

a vertical sidebar housing **notifications** and **quick controls**.

**structure:**

| section               | purpose                                              |
| --------------------- | ---------------------------------------------------- |
| 🔔 **notifications**  | all system and app notifications stream here         |
| ⚡ **quick controls** | glanceable system controls (like iOS Control Center) |

**design inspiration:**

-   notifications: Android notification shade
-   quick controls: iOS Control Center + Windows 11 quick settings panel

the dock is the **status + control** hub, while the island handles **navigation + context**.

---

## 🏠 home screen

the front page acts as a **home screen**, not just a chat landing page.

### unified search bar

a single text input, front and center, that serves dual purpose:

| mode            | behavior                                           |
| --------------- | -------------------------------------------------- |
| **chat mode**   | type freely → sends message to AI, starts new chat |
| **search mode** | type → suggestions appear → select to navigate     |

**what it searches:**

-   apps
-   notes & documents
-   reminders & calendar events
-   messages & chats
-   anything in the system

**UX clarity rule:**
to prevent accidental searches when user just wants to chat, **non-chat actions require explicit selection** of a suggestion. keyboard shortcuts (↑↓ navigate, Enter select) enable speed for power users.

**inspiration:** Google Pixel launcher search bar — always present, searches everything, opens apps instantly.

---

## ✨ visual language

### liquid glass aesthetic

the signature visual style across all surfaces:

-   **semi-transparent** elements with blur/frosted effects
-   **depth and layering** — UI feels like floating glass panels
-   **subtle reflections** and gradient shifts
-   **premium, futuristic feel** — inspired by Apple's design language

### motion & transitions

-   **physics-based animations** — elements feel weighty and natural
-   **View Transitions API** for seamless page-to-page morphing
-   graceful degradation: no transition (or unsupported browser) if API unavailable

---

## 📱 "everything app" trajectory

nokodo AI is designed to expand into a **universal access point**:

### productivity layer

-   📝 notes
-   ⏰ reminders
-   📅 calendar integration

### communication layer

-   💬 user messaging (WhatsApp/iMessage style)
-   🤖 AI participants in group chats
-   humans + AIs in the same conversation

### system integration layer

-   🏠 smart home controls
-   🎵 music (Spotify, etc.)
-   📧 email management
-   🔗 infinite extensibility via plugins

### future: phone launcher mode

nokodo AI becomes the **home screen itself** — the primary interface to your device.

user behavior insight (from Pixel launcher usage):

-   ~60% — tap AI-suggested apps
-   ~30% — search for app by name
-   ~10% — manually scroll through apps

→ nokodo can own that 90% with smart suggestions + unified search.

---

## 🎯 UX rules

| rule                               | rationale                                              |
| ---------------------------------- | ------------------------------------------------------ |
| **never expose internal workings** | users don't need to see how the magic happens          |
| **never expose model details**     | "AI" is one thing to users, not GPT-4 vs Claude vs etc |
| **native artifacts**               | render generated content inline, interactive           |
| **progressive disclosure**         | simple by default, powerful when needed                |

---

## 🗺️ information architecture

```
┌─────────────────────────────────────────────┐────────────┐
│              THE ISLAND (header)            │  THE DOCK  │
│   🏠 home    [  activity area  ]    👤 user│            │
├─────────────────────────────────────────────│            │
│                                             │            │
│                                             │            │
│                                             │            │
│              main content area              │     🔔     │
│                                             │     🔔     │
│         (home / chat / app / etc)           │     ⚡     │
│                                             │     🎛️     │
│                                             │            │
└─────────────────────────────────────────────┴────────────┘
```

---

_fluid · intelligent · universal_
_nokodo AI — your interface to everything_ ✨
