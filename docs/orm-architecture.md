# nokodo AI - ORM Architecture

## vision

this document defines the data architecture for nokodo AI - a next-generation AI platform built on real-time communication, asynchronous task execution, and intelligent memory.

**core principles:**

-   **threads over chats** - conversations are more than user↔assistant exchanges
-   **events as universal communication** - everything flows through a unified event stream
-   **tasks are independent** - long-running operations aren't owned by threads
-   **async-first** - users can leave and return, nothing is lost
-   **future-proof** - architecture supports infinite extensibility
-   **projects as containers** - organize threads, files, and resources together
-   **groups for collaboration** - users share access and resources
-   **intelligence routing** - smart model selection saves costs

---

## core entities

### User

represents a platform user with authentication, preferences, and integrations

**properties:**

-   unique identifier
-   authentication details (OIDC integration)
-   profile information (name, email, avatar)
-   user preferences & settings
-   integration tokens (spotify, github, etc.)
-   usage limits & quotas

**relationships:**

-   owns multiple **Threads**
-   owns multiple **Tasks**
-   owns multiple **Projects**
-   belongs to multiple **Groups**
-   has one **Role** (admin-assigned)
-   receives **Notifications**
-   has **Memory** records
-   participates in **Threads** (AI or user-to-user)
-   has **Reminders**
-   manages **Access Control Entries (ACLs)** for shared resources

**notes:**

-   federated users & groups via OIDC
-   user settings control AI behavior, UI preferences, notification channels
-   role determines permissions, quotas, and access level (invisible to user)
-   every resource owner column ultimately points to a **User** (billing + accountability)

---

### Thread

the container for everything that happens in a conversation - messages, tool calls, task references, and the complete event timeline

**why "Thread" not "Chat":**
a chat is what users SEE (back and forth dialogue). a Thread is what actually EXISTS (dialogue + tool executions + async operations + system events + metadata)

**properties:**

-   unique identifier
-   owner (User reference - thread creator)
-   participants (array - User IDs and/or Agent IDs)
-   title (user-defined or auto-generated)
-   created timestamp
-   last activity timestamp
-   metadata (tags, folder, archived status, etc.)

**relationships:**

-   belongs to one **User** (owner/creator)
-   has multiple **participants** (Users and/or Agents)
-   may belong to a **Project**
-   may belong to a **Group** (for shared threads)
-   shares access via **Access Control Entries (ACLs)**
-   contains multiple **Messages**
-   may reference multiple **Tasks** (via messages)
-   has many **Events** scoped to it

**notes:**

-   threads are the unit of conversation history
-   **thread types:**
    -   `ai_assistant` - classic user↔AI conversation
    -   `direct_message` - user↔user (AI can assist)
    -   `group_chat` - multiple users + optional AI participants
-   participants array enables any combination of users and agents
-   deleting a thread terminates ALL attached tasks (UI shows warning)
-   task termination happens before thread deletion (ensures clean state)
-   threads can be organized, searched, archived
-   threads can belong to a **Project** for organization
-   threads can be shared with **Groups** for collaboration
-   ACLs determine who else (users, groups, agents) can view or edit the thread

---

### Message

a single turn in the conversation - can be from user, assistant, tool, or system

**properties:**

-   unique identifier
-   thread (Thread reference)
-   sender (User reference OR Agent reference - who sent this)
-   type (user / assistant / tool / system)
-   content (text, can be markdown)
-   timestamp
-   read by (array of User IDs - for multi-participant threads)
-   task reference (nullable - if this message spawned or references a task)
-   metadata (flexible JSON - type-specific fields)

**type-specific structures:**

**assistant messages:**

-   token usage object (input tokens, output tokens, total cost)
-   tool calls (array - references to tools being called)
-   model used (which model generated this response)
-   attachments (generated images, documents, etc.)

**user messages:**

-   uploads (user-uploaded files)
-   attachments (photos, documents, etc.)
-   audio recording (if agent supports direct audio input)
-   other media (video, etc.)

**tool messages:**

-   tool call ID (which tool call spawned this response)
-   tool type (web_search / code_execution / image_generation / etc.)
-   status (processing / complete / failed)
-   result data (tool-specific output)

**system messages:**

-   system event type (thread_created / settings_changed / etc.)
-   additional context

**relationships:**

-   belongs to one **Thread**
-   may reference one **Task**
-   has many **Events** scoped to it

**notes:**

-   messages follow openai message format loosely
-   varying structures based on type enable rich functionality
-   SQLAlchemy polymorphic inheritance maps `type` as the discriminator, enabling native subclasses per message kind
-   assistant and user can both include attachments/media
-   tool messages display processing status directly in chat UI
-   tool calls within messages can spawn tasks
-   messages are the building blocks of conversation timeline
-   events can attach to messages (e.g., "memory added from this message")
-   extensible design allows new message types in future

---

### Task

an independent, long-running operation with lifecycle, progress tracking, and results

**what qualifies as a task:**

-   operations that take significant time (>few seconds)
-   operations with multiple stages/steps
-   operations that need progress tracking
-   examples: code sessions, deep research, video generation

**properties:**

-   unique identifier
-   owner (User reference)
-   type (code_session / research / image_generation / custom)
-   status (pending / running / complete / failed / cancelled)
-   progress (percentage or stage indicator)
-   result (final output - could be document, artifact, file, etc.)
-   spawned from (nullable - could be thread ID, could be null if from menu/API)
-   created timestamp
-   completed timestamp (nullable)
-   metadata (type-specific configuration)

**relationships:**

-   belongs to one **User**
-   may be referenced by **Messages** (but not owned by them)
-   has many **Events** scoped to it

**notes:**

-   tasks are independent entities
-   users can spawn tasks from anywhere (chat, menu, API, scheduled jobs)
-   tasks can be queried, managed, cancelled independently
-   task progress is communicated via events
-   completed tasks produce results that can be referenced/downloaded

**code sessions:**

-   autonomous coding agent in sandboxed environment
-   iterative code changes, testing, refinement
-   automatic PR creation to github
-   full terminal access, tool usage, web access
-   multi-model support with customization

---

### Event

the universal communication primitive - everything that happens flows through events

**the event system is the nervous system of nokodo AI:**

-   live updates to frontend
-   notification delivery
-   audit trail
-   full replay capability

**properties:**

-   unique identifier (for deduplication)
-   scope (system / user / thread / message / task)
-   scope ID (nullable for system events, otherwise ID of scoped entity)
-   type (memory_added / task_progress / system_alert / spotify_track / etc.)
-   data (flexible JSON payload - contains all info needed to render event)
-   timestamp (for chronological ordering)
-   expires at (nullable - for ephemeral events with TTL)
-   version (for schema evolution)

**event scopes explained:**

**system events** (scope=system, scope_id=null)

-   maintenance alerts
-   platform announcements
-   global status updates
-   visible to ALL users

**user events** (scope=user, scope_id=user_123)

-   spotify track changes
-   calendar reminders
-   integration notifications
-   personal alerts

**thread events** (scope=thread, scope_id=thread_456)

-   memory added from conversation
-   thread metadata changes
-   conversation-level updates

**message events** (scope=message, scope_id=msg_789)

-   tool call initiated
-   tool response received
-   image generated
-   message edited/deleted

**task events** (scope=task, scope_id=task_012)

-   progress updates (stage transitions)
-   status changes (running → complete)
-   error notifications

**relationships:**

-   may reference **User** (if user-scoped)
-   may reference **Thread** (if thread-scoped)
-   may reference **Message** (if message-scoped)
-   may reference **Task** (if task-scoped)
-   creates **Notifications** (for users who should be notified)

**notes:**

-   events are emitted AFTER successful DB writes (reliability over speed)
-   events contain full payload needed for rendering (no extra fetches)
-   frontend subscribes to relevant event scopes via websocket
-   events enable full thread reconstruction (chronological replay)
-   ephemeral events (typing indicators, progress) can have TTL

---

### Notification

persistent delivery guarantee - ensures users don't miss important events

**why notifications are separate from events:**
events are the WHAT happened. notifications are WHO should know about it.

**properties:**

-   unique identifier
-   user (User reference - who should see this)
-   event (Event reference - what happened)
-   read status (boolean)
-   created timestamp
-   dismissed (boolean - user actively dismissed it)

**relationships:**

-   belongs to one **User**
-   references one **Event**

**notes:**

-   when event is emitted, notification records are created for relevant users
-   notifications = user's inbox of unread updates
-   expired events (expires_at < now) are filtered out when fetching
-   opening thread marks thread-related notifications as read
-   notification center shows unread count badge

**delivery flow:**

1. event emitted
2. sent via websocket (live delivery)
3. notification record created (persistent delivery)
4. user reconnects → fetches unread notifications
5. user opens thread → marks related notifications read

---

### Agent

user-facing AI abstraction with personality, tools, and prompting

**properties:**

-   unique identifier
-   name (e.g., "Claude")
-   description
-   system prompt
-   enabled tools (references to available tools)
-   model configuration (temperature, max tokens, etc.)
-   default model (which model to use)
-   visibility (public / private / admin-only)

**relationships:**

-   used in **Messages** (which agent responded)
-   can spawn **Tasks** (via tool calls)

**notes:**

-   agents are curated, high-quality abstractions
-   users don't see underlying models
-   agents have consistent personality across conversations
-   multi-functional - handle diverse tasks
-   zero setup required

---

### Provider

backend configuration for API providers that expose models - NOT exposed to users

**properties:**

-   unique identifier
-   name (openai / anthropic / google / groq / ollama / etc.)
-   adapter type (openai_chat_completions / anthropic_messages / google_genai / custom)
-   base API URL
-   secret token / API key (encrypted)
-   status (enabled / disabled)
-   model exposure strategy (autofetch_all / manual)
-   manual model IDs (array - used if strategy=manual)
-   last synced timestamp (for autofetch)
-   metadata (provider-specific config)

**relationships:**

-   exposes multiple **Models**

**notes:**

-   providers are admin-configured
-   adapter type defines which library module backend uses to contact API
-   adapters provide abstraction over API interactions (send message, stream responses, etc.)
-   **openai_chat_completions** is primary adapter - most common by far (OpenAI, Groq, many others)
-   other adapters (anthropic_messages, google_genai, etc.) can be added as needed
-   autofetch strategy queries provider API to discover available models
-   manual strategy uses explicitly defined model IDs
-   disabled providers hide all their models from agents
-   supports both cloud providers and local instances (ollama, vLLM, etc.)

---

### Model

backend configuration for foundation models - NOT exposed to users

**properties:**

-   unique identifier
-   provider (Provider reference)
-   model name (gpt-4, claude-3-opus, gemini-pro, etc.)
-   type (llm / embedding / image_generation / image_edit / audio / video / etc.)
-   API endpoint (can override provider base URL)
-   capabilities (array - text / vision / audio / function_calling / etc.)
-   context window size (nullable - for LLMs)
-   cost per token (input/output - nullable)
-   enabled status
-   metadata (model-specific config)

**relationships:**

-   belongs to one **Provider**
-   used by **Agents** (agents reference models)

**notes:**

-   models are config-driven, fetched from provider APIs or manually defined
-   users never see model details (privacy principle)
-   admin can add/remove/configure models
-   agents abstract away model complexity
-   type field enables filtering (e.g., only show LLMs for chat, only embeddings for memory)
-   embedding models used by memory system
-   image models used by tool calls (DALL-E, Stable Diffusion, etc.)

---

### Project

organizational container for grouping related content - threads, files, resources

**properties:**

-   unique identifier
-   owner (User reference)
-   name
-   description (nullable)
-   created timestamp
-   last modified timestamp
-   metadata (tags, color, icon, etc.)

**relationships:**

-   belongs to one **User** (owner/billing anchor)
-   shares access via **ACLs** with Users, Groups, or Agents (Projects stay resources)
-   contains multiple **Threads**
-   has many **Events** scoped to it

**notes:**

-   projects help users organize related work
-   collaborative access flows through ACLs (not implicit group ownership)
-   projects **do not** act as principals; they never inherit rights via ACLs
-   resources are attached to projects, and app logic controls how project access fans out to those resources
-   cross-project search available
-   project-level settings override user defaults

---

### Group

user collective for shared access and resource consolidation

**properties:**

-   unique identifier
-   name
-   description (nullable)
-   created timestamp
-   owner (User reference - group admin)
-   metadata (settings, quotas, etc.)

**relationships:**

-   has multiple **Users** (members)
-   gains access to **Threads**, **Projects**, and other resources via ACLs
-   has group-level quotas

**notes:**

-   groups let users band together for collaboration
-   ACL grants give groups the same access semantics as individuals
-   group-level permissions and quotas
-   useful for teams, families, organizations

---

### Access Control Entry (ACL)

generic sharing primitive that grants principals access to resources

**properties:**

-   unique identifier
-   `thread_id`, `project_id`, etc. (one nullable FK per resource type; only one populated)
-   `user_id`, `group_id`, `agent_id` (one nullable FK per principal type; only one populated)
-   role (viewer / editor / admin / custom)
-   metadata (invited_by, expires_at, notes, etc.)
-   created / updated timestamps

**relationships:**

-   each FK is a real constraint, so cascades work per resource/principal table
-   managed by the owning **User** of the resource (who can grant/revoke access)

**notes:**

-   partial-unique constraints ensure exactly one resource + one principal per row
-   ownership is **not** stored here—resources retain `owner_id` pointing to a **User**
-   adding new resource/principal types means adding new nullable columns + constraints, keeping queries simple and performant

---

### Role

admin-managed permission and access tier - invisible to users

**properties:**

-   unique identifier
-   name (e.g., "free", "pro", "enterprise", "admin")
-   permissions (array - feature flags, access controls)
-   quotas (token limits, storage limits, etc.)
-   priority (for inheritance/fallback)
-   metadata (role-specific limits or notes)

**relationships:**

-   assigned to multiple **Users**

**notes:**

-   roles manage what users can do
-   OSS/self-hosted deployments can create any role taxonomy they need
-   admin-only visibility (users don't see role names)
-   supports feature gating and tiered access
-   future: role inheritance for complex permissions

---

### Reminder

timed reminder with AI enhancement

**properties:**

-   unique identifier
-   owner (User reference)
-   content (what to remind about)
-   due timestamp
-   recurrence (nullable - daily, weekly, custom)
-   status (pending / triggered / dismissed / snoozed)
-   notification channels (push, email, etc.)
-   source (nullable - thread ID if created from conversation)
-   external sync (nullable - Google Calendar ID, Apple Reminders ID)
-   metadata (priority, tags, etc.)

**relationships:**

-   belongs to one **User**
-   may reference **Thread** (where it was created)
-   creates **Notifications** when triggered

**notes:**

-   natural language reminder creation
-   AI suggests reminders from context
-   syncs with Google/Apple ecosystems
-   multi-channel notification delivery

---

### Memory

intelligent context storage - what the AI remembers about users and conversations

**the memory system is critical - must be highly accurate:**

-   asynchronous memory manager detects, updates, deletes intelligently
-   reuses logic from OWUI extension auto-memory
-   high accuracy relevant memory detection

**properties:**

-   unique identifier
-   user (User reference - whose memory)
-   content (what is remembered)
-   source thread (nullable - which conversation this came from)
-   source message (nullable - which message triggered this)
-   created timestamp
-   last modified timestamp
-   last accessed timestamp
-   embedding vector (for semantic search)
-   metadata (tags, category, confidence, etc.)

**relationships:**

-   belongs to one **User**
-   may reference **Thread** (where it was learned)
-   may reference **Message** (what triggered it)

**notes:**

-   memories are automatically extracted from conversations
-   memory additions emit events (shown to user)
-   memories are retrieved based on relevance to current context
-   memory system can use mem0.ai OR custom implementation (embeddings + retrieval)
-   memories persist across threads (user-level knowledge)

---

## architectural patterns

### chronological reconstruction

fetch all events for a thread ordered by timestamp = complete replay of everything that happened

### live updates via websocket

frontend subscribes to relevant event scopes → receives events in real-time → renders immediately

### offline resilience

user misses events while offline → notification queue persists them → user fetches on reconnect

### task independence

tasks aren't owned by threads → can be managed separately → users can view all tasks in unified interface

### flexible querying

-   "all memories for this user" → query Memory by user_id
-   "all events in this thread" → query Events where scope=thread AND scope_id=thread_id
-   "all running tasks" → query Tasks where status=running

### eventual consistency

events emitted after DB writes → reliable state → no phantom updates

---

## future expansion hooks

### collaborative features

-   **Groups** enable shared access to threads and projects
-   **Projects** can be shared with groups
-   threads can belong to groups for collaborative access
-   events already support multi-user delivery
-   notifications already per-user

### custom integrations

-   new event types can be added dynamically
-   integration configs stored in user metadata
-   events flow through same universal system

### advanced memory

-   memory can reference external sources
-   embeddings enable semantic retrieval
-   memory graphs (relationships between memories)

### session types beyond tasks

-   multi-turn research sessions
-   creative project workflows
-   data analysis pipelines
-   all follow same task pattern

---

## design philosophy

**keep it simple, make it powerful:**

-   few entities with clear responsibilities
-   flexible schemas (metadata, data fields) for future needs
-   events as universal glue holding everything together
-   async-first mindset baked into architecture

**user experience first:**

-   instant feedback (optimistic updates via events)
-   never lose data (persistent notifications, full event log)
-   transparent progress (task events, live updates)
-   seamless across devices (event subscriptions, notification sync)

**built for scale:**

-   event stream can be sharded by user/thread
-   tasks execute independently (horizontal scaling)
-   notifications can be queued/batched
-   memory retrieval can be optimized separately

---

_this architecture supports the vision: clean, simple, powerful - built for the future of AI interaction_ ✨
