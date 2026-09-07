/**
 * inline chat system events - what happened TO the chat rather than what
 * anyone said, rendered as centered quiet rows between the bubbles.
 *
 * membership rides `access.updated`: there is no discrete "joined"/"left"
 * event, so the transition is DERIVED from each change's before/after rule
 * exactly the way the backend's own renderer does it
 * (`api/v1/service/chat/filters/message_event.py`), so the agent's view of the
 * conversation and the reader's view say the same thing.
 *
 * agent presence rides `thread.participants.added/removed` with `kind: "agent"`
 * and is anchored to the thread head, which is what makes it survive a reload
 * through the by-message-ids event fetch. an `access.updated` only carries that
 * anchor when the thread's writer model flipped, so most membership rows are
 * live-only until the backend anchors them (see B item in the ledger).
 */

export type ChatSystemEventKind =
	| 'member_added'
	| 'member_invited'
	| 'member_joined'
	| 'member_left'
	| 'member_removed'
	| 'member_access_changed'
	| 'group_added'
	| 'group_removed'
	| 'agent_added'
	| 'agent_removed'
	| 'title_changed'

/** a system event, resolved down to what a row needs and nothing more. */
export interface ChatSystemEvent {
	/** dedupe key: the same event arrives live and again from the event log. */
	id: string
	kind: ChatSystemEventKind
	threadId: string
	createdAt: Date
	/** who acted, or null when the emitter names no trustworthy actor. */
	actorUserId: string | null
	/** name the event carried for the actor, when it denormalized one. */
	actorName: string | null
	/** the user, group or agent the row is about. */
	subjectId: string | null
	subjectName: string | null
	/** resulting access level, for a level change. */
	level: string | null
	/** the new chat title, for a rename. */
	title: string | null
	/** anchor message, when the event carries one. */
	messageId: string | null
}

/** one run of row copy; `strong` marks the names inside it. */
export interface SystemRowSegment {
	text: string
	strong?: boolean
}

/** resolves ids to names, and knows which of them is the reader. */
export interface SystemNameResolver {
	/** display name for a user, group or agent id; null when unknown. */
	name(id: string): string | null
	currentUserId: string | null
}

export interface RawSystemEvent {
	id?: string
	type: string
	data: Record<string, unknown>
	created_at?: string | null
	message_id?: string | null
	thread_id?: string | null
}

export interface ParseSystemEventOptions {
	/**
	 * the viewer's id, passed ONLY when this session caused the event.
	 *
	 * `thread.updated` names no actor (its `user_id` is the thread owner, not
	 * whoever renamed it), so the row stays actor-less rather than crediting the
	 * wrong person - except for the reader's own rename, which is knowable.
	 */
	selfActorUserId?: string | null
	/**
	 * whether a rename earns a row.
	 *
	 * off by default: a solo chat titles ITSELF from the conversation, so every
	 * new chat would open with a rename notice. only a chat several people share
	 * has a title anyone else needs telling about.
	 */
	renameRows?: boolean
}

export const ACCESS_UPDATED_EVENT_TYPE = 'access.updated'
export const THREAD_UPDATED_EVENT_TYPE = 'thread.updated'
export const THREAD_PARTICIPANT_ADDED_EVENT_TYPE = 'thread.participants.added'
export const THREAD_PARTICIPANT_REMOVED_EVENT_TYPE = 'thread.participants.removed'

/** event types that can produce a system row. */
export const CHAT_SYSTEM_EVENT_TYPES = [
	ACCESS_UPDATED_EVENT_TYPE,
	THREAD_UPDATED_EVENT_TYPE,
	THREAD_PARTICIPANT_ADDED_EVENT_TYPE,
	THREAD_PARTICIPANT_REMOVED_EVENT_TYPE,
] as const

function text(value: unknown): string | null {
	return typeof value === 'string' && value.length > 0 ? value : null
}

function timestamp(value: string | null | undefined): Date {
	if (!value) return new Date()
	const parsed = new Date(value)
	return Number.isNaN(parsed.getTime()) ? new Date() : parsed
}

interface RuleSnapshot {
	subjectUserId: string | null
	subjectGroupId: string | null
	level: string | null
}

function ruleSnapshot(value: unknown): RuleSnapshot | null {
	if (!value || typeof value !== 'object' || Array.isArray(value)) return null
	const rule = value as Record<string, unknown>
	return {
		subjectUserId: text(rule.subject_user_id),
		subjectGroupId: text(rule.subject_group_id),
		level: text(rule.level),
	}
}

/**
 * classify one canonical ACL transition.
 *
 * role rules and the everyone rule name no person, so they are membership in
 * name only and never become a row.
 */
function accessChangeKind(
	before: RuleSnapshot | null,
	after: RuleSnapshot | null,
	actorUserId: string | null
): { kind: ChatSystemEventKind; subjectId: string; level: string | null } | null {
	const rule = after ?? before
	if (!rule) return null
	const subjectId = rule.subjectGroupId ?? rule.subjectUserId
	if (!subjectId) return null
	const isGroup = rule.subjectGroupId !== null
	const isSelf = actorUserId !== null && actorUserId === rule.subjectUserId

	if (!before) {
		if (isGroup) return { kind: 'group_added', subjectId, level: after?.level ?? null }
		const kind = after?.level === 'reader' ? 'member_invited' : 'member_added'
		return { kind, subjectId, level: after?.level ?? null }
	}
	if (!after) {
		if (isGroup) return { kind: 'group_removed', subjectId, level: null }
		return { kind: isSelf ? 'member_left' : 'member_removed', subjectId, level: null }
	}
	if (isSelf && after.level !== 'reader') {
		return { kind: 'member_joined', subjectId, level: after.level }
	}
	// a no-op rewrite (reordering, an unchanged level) is not something that
	// happened to the chat, so it earns no row.
	if (before.level === after.level) return null
	return { kind: 'member_access_changed', subjectId, level: after.level }
}

function parseAccessUpdated(event: RawSystemEvent, threadId: string): ChatSystemEvent[] {
	const data = event.data
	if (text(data.resource_type) !== 'thread') return []
	const changes = data.changes
	if (!Array.isArray(changes)) return []

	const actorUserId = text(data.actor_user_id)
	const createdAt = timestamp(event.created_at)
	// the anchor rides the payload here, not the event's own column.
	const messageId = text(data.message_id) ?? text(event.message_id)
	const revision = typeof data.revision === 'number' ? String(data.revision) : 'r'
	const baseId = event.id ?? `${ACCESS_UPDATED_EVENT_TYPE}:${threadId}:${revision}`

	const rows: ChatSystemEvent[] = []
	changes.forEach((change, index) => {
		if (!change || typeof change !== 'object' || Array.isArray(change)) return
		const entry = change as Record<string, unknown>
		const classified = accessChangeKind(
			ruleSnapshot(entry.before),
			ruleSnapshot(entry.after),
			actorUserId
		)
		if (!classified) return
		rows.push({
			id: `${baseId}:${index}`,
			kind: classified.kind,
			threadId,
			createdAt,
			actorUserId,
			actorName: text(data.actor_name),
			subjectId: classified.subjectId,
			subjectName: null,
			level: classified.level,
			title: null,
			messageId,
		})
	})
	return rows
}

function parseAgentPresence(event: RawSystemEvent, threadId: string): ChatSystemEvent[] {
	const data = event.data
	// the same two types also carry a user's private per-thread state (read
	// cursor, mute/pin); only the agent instances are chat history.
	if (text(data.kind) !== 'agent') return []
	const agentId = text(data.agent_id)
	if (!agentId || !event.id) return []
	return [
		{
			id: event.id,
			kind:
				event.type === THREAD_PARTICIPANT_ADDED_EVENT_TYPE
					? 'agent_added'
					: 'agent_removed',
			threadId,
			createdAt: timestamp(event.created_at),
			actorUserId: text(data.actor_user_id),
			actorName: text(data.actor_name),
			subjectId: agentId,
			subjectName: text(data.agent_name),
			level: null,
			title: null,
			messageId: text(event.message_id),
		},
	]
}

function parseThreadUpdated(
	event: RawSystemEvent,
	threadId: string,
	options: ParseSystemEventOptions
): ChatSystemEvent[] {
	if (!options.renameRows) return []
	const data = event.data
	// a restore fans out the WHOLE thread payload, which repeats the title
	// without anything having changed. the rename payload is partial, so the
	// presence of creation fields is what tells the two apart.
	if ('created_at' in data || 'participants' in data) return []
	const title = text(data.title)
	if (!title) return []
	const createdAt = timestamp(event.created_at)
	return [
		{
			id: event.id ?? `${THREAD_UPDATED_EVENT_TYPE}:${threadId}:${createdAt.getTime()}`,
			kind: 'title_changed',
			threadId,
			createdAt,
			actorUserId: options.selfActorUserId ?? null,
			actorName: null,
			subjectId: null,
			subjectName: null,
			level: null,
			title,
			messageId: null,
		},
	]
}

/**
 * parse one raw event into the system rows it produces.
 *
 * an `access.updated` can carry several changes and therefore several rows;
 * everything else yields at most one.
 */
export function parseChatSystemEvents(
	event: RawSystemEvent,
	options: ParseSystemEventOptions = {}
): ChatSystemEvent[] {
	const threadId =
		text(event.thread_id) ?? text(event.data.thread_id) ?? text(event.data.resource_id)
	if (!threadId) return []

	switch (event.type) {
		case ACCESS_UPDATED_EVENT_TYPE:
			return parseAccessUpdated(event, threadId)
		case THREAD_PARTICIPANT_ADDED_EVENT_TYPE:
		case THREAD_PARTICIPANT_REMOVED_EVENT_TYPE:
			return parseAgentPresence(event, threadId)
		case THREAD_UPDATED_EVENT_TYPE:
			return parseThreadUpdated(event, threadId, options)
		default:
			return []
	}
}

const USER_SUBJECT_KINDS: ReadonlySet<ChatSystemEventKind> = new Set([
	'member_added',
	'member_invited',
	'member_joined',
	'member_left',
	'member_removed',
	'member_access_changed',
])

/**
 * every USER id these rows need a name for, so the caller can fetch the ones
 * the roster no longer holds - somebody who left is named by a row but is not
 * a participant any more. group and agent subjects are excluded: they are not
 * users and the roster is the only place they resolve from.
 */
export function systemEventUserIds(events: Iterable<ChatSystemEvent>): string[] {
	const ids: string[] = []
	for (const event of events) {
		const candidates = USER_SUBJECT_KINDS.has(event.kind)
			? [event.actorUserId, event.subjectId]
			: [event.actorUserId]
		for (const id of candidates) {
			if (id && !ids.includes(id)) ids.push(id)
		}
	}
	return ids
}

function label(
	id: string | null,
	denormalized: string | null,
	resolver: SystemNameResolver,
	fallback: string
): string {
	if (id && id === resolver.currentUserId) return 'you'
	if (id) {
		const resolved = resolver.name(id)
		if (resolved) return resolved
	}
	return denormalized ?? fallback
}

/** the row's copy, with the names marked so they can carry weight. */
export function systemEventSegments(
	event: ChatSystemEvent,
	resolver: SystemNameResolver
): SystemRowSegment[] {
	const actor = label(event.actorUserId, event.actorName, resolver, 'someone')
	const subject = label(event.subjectId, event.subjectName, resolver, 'someone')

	switch (event.kind) {
		case 'member_added':
		case 'agent_added':
			return [
				{ text: actor, strong: true },
				{ text: ' added ' },
				{ text: subject, strong: true },
				{ text: ' to this chat' },
			]
		case 'member_invited':
			return [
				{ text: actor, strong: true },
				{ text: ' invited ' },
				{ text: subject, strong: true },
				{ text: ' to this chat' },
			]
		case 'member_removed':
		case 'agent_removed':
			return [
				{ text: actor, strong: true },
				{ text: ' removed ' },
				{ text: subject, strong: true },
				{ text: ' from this chat' },
			]
		case 'member_left':
			return [{ text: subject, strong: true }, { text: ' left the chat' }]
		case 'member_joined':
			return [{ text: subject, strong: true }, { text: ' joined the chat' }]
		case 'member_access_changed':
			return [
				{ text: actor, strong: true },
				{ text: ' changed ' },
				{ text: subject, strong: true },
				{ text: `'s access to ${event.level ?? 'none'}` },
			]
		case 'group_added':
			return [
				{ text: actor, strong: true },
				{ text: ' shared this chat with ' },
				{
					text: label(event.subjectId, event.subjectName, resolver, 'a group'),
					strong: true,
				},
			]
		case 'group_removed':
			return [
				{ text: actor, strong: true },
				{ text: ' removed ' },
				{
					text: label(event.subjectId, event.subjectName, resolver, 'a group'),
					strong: true,
				},
				{ text: ' from this chat' },
			]
		case 'title_changed': {
			const title = event.title ?? ''
			if (!event.actorUserId) {
				return [{ text: 'the chat title is now ' }, { text: title, strong: true }]
			}
			return [
				{ text: actor, strong: true },
				{ text: ' changed the chat title to ' },
				{ text: title, strong: true },
			]
		}
	}
}

export interface BeginningOfChatInput {
	kind: 'solo' | 'direct' | 'group'
	/** the other person in a DM, or the lone agent in a solo chat. */
	counterpartName: string | null
	/** the group's name. */
	chatName: string | null
	/** who created the chat, already resolved ("you" for the reader). */
	creatorName: string | null
}

/**
 * the row that opens a transcript.
 *
 * a group names its founding; a one-to-one chat names the person you are
 * talking to. anything it cannot name is dropped rather than guessed, so an
 * unresolved roster degrades to a shorter sentence instead of "someone".
 */
export function beginningOfChatSegments(input: BeginningOfChatInput): SystemRowSegment[] {
	if (input.kind === 'group') {
		const name = input.chatName?.trim() || null
		if (input.creatorName && name) {
			return [
				{ text: input.creatorName, strong: true },
				{ text: ' created ' },
				{ text: name, strong: true },
			]
		}
		if (input.creatorName) {
			return [{ text: input.creatorName, strong: true }, { text: ' created this group chat' }]
		}
		if (name) {
			return [{ text: 'this is the beginning of ' }, { text: name, strong: true }]
		}
		return []
	}

	const counterpart = input.counterpartName?.trim() || null
	if (!counterpart) return []
	return [
		{ text: 'this is the beginning of your chat with ' },
		{ text: counterpart, strong: true },
	]
}
