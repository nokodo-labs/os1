/**
 * synthetic threads for exercising transcript UI that real dev data cannot reach.
 *
 * multi-writer conversations need several accounts to produce, so the states
 * they render (sender identity, grouping, cross-participant replies) are
 * otherwise only reachable in production. these scenarios build the same
 * payloads the API returns, so the thread page renders them through its normal
 * path with nothing stubbed.
 */

import type { Thread } from '$lib/stores/chat.svelte'
import type { ApiMessage } from './types'

type Participant = NonNullable<Thread['participants']>[number]

export interface DebugScenario {
	id: string
	label: string
	description: string
	build: (viewerId: string) => { thread: Thread; messages: ApiMessage[] }
}

const THREAD_ID = 'thread_debugmultiwriter00000000'
const AGENT_ID = 'agent_debug00000000000000000'

/** cast people: ids are stable so a reload keeps the same conversation. */
const PEOPLE = {
	ada: { id: 'user_debugada000000000000000', name: 'ada lovelace' },
	linus: { id: 'user_debuglinus00000000000000', name: 'linus' },
	grace: { id: 'user_debuggrace00000000000000', name: 'grace hopper' },
} as const

function userParticipant(id: string, name: string, isOwner = false): Participant {
	return {
		id: `participant_${id}`,
		thread_id: THREAD_ID,
		is_owner: isOwner,
		access_level: 'editor',
		kind: 'user',
		user: { id, display_name: name, username: name, avatar_url: null },
	}
}

function agentParticipant(): Participant {
	return {
		id: `participant_${AGENT_ID}`,
		thread_id: THREAD_ID,
		is_owner: false,
		access_level: 'editor',
		kind: 'agent',
		invoke_on_mention: true,
		agent: { id: AGENT_ID, name: 'assistant', profile_image_url: null },
	}
}

/** minutes since an arbitrary fixed start, so timestamps read naturally. */
function at(minute: number): string {
	const base = new Date()
	base.setHours(9, 0, 0, 0)
	return new Date(base.getTime() + minute * 60_000).toISOString()
}

interface MessageSpec {
	id: string
	from: string | 'agent'
	text: string
	minute: number
	parent: string | null
	runId: string
	replyTo?: string
}

function toMessage(spec: MessageSpec): ApiMessage {
	const isAgent = spec.from === 'agent'
	return {
		id: spec.id,
		thread_id: THREAD_ID,
		parent_id: spec.parent,
		type: isAgent ? 'assistant' : 'user',
		content: [{ type: 'text', text: spec.text }],
		tool_calls: [],
		sender_agent_id: isAgent ? AGENT_ID : null,
		sender_user_id: isAgent ? null : spec.from,
		reply_to_message_id: spec.replyTo ?? null,
		metadata: { run_id: spec.runId },
		created_at: at(spec.minute),
		updated_at: at(spec.minute),
	} as ApiMessage
}

/** chain specs into a parent-linked branch, so the page walks a real tree. */
function chain(specs: Omit<MessageSpec, 'parent'>[]): ApiMessage[] {
	let parent: string | null = null
	const messages: ApiMessage[] = []
	for (const spec of specs) {
		messages.push(toMessage({ ...spec, parent }))
		parent = spec.id
	}
	return messages
}

/**
 * the viewer owns every scenario: ownership short-circuits access resolution
 * to admin locally, so the transcript is never read-only for lack of a server.
 */
function thread(
	participants: Participant[],
	leafId: string,
	title: string,
	viewerId: string
): Thread {
	return {
		id: THREAD_ID,
		title,
		tags: [],
		is_temporary: false,
		owner_id: viewerId,
		current_message_id: leafId,
		last_activity_at: at(60),
		created_at: at(0),
		updated_at: at(60),
		deleted_at: null,
		projects: [],
		participants,
	} as Thread
}

/**
 * the everyday case: several people talking, an agent answering when asked.
 * covers name/avatar grouping, own-vs-other alignment and consecutive runs.
 */
function groupConversation(viewerId: string): { thread: Thread; messages: ApiMessage[] } {
	const messages = chain([
		{
			id: 'msg_dbg01',
			from: PEOPLE.ada.id,
			text: 'morning, are we still shipping today?',
			minute: 0,
			runId: 'run_dbg01',
		},
		{
			id: 'msg_dbg02',
			from: PEOPLE.ada.id,
			text: 'i finished the migration last night',
			minute: 1,
			runId: 'run_dbg01',
		},
		{
			id: 'msg_dbg03',
			from: PEOPLE.linus.id,
			text: 'yes, assuming CI is green',
			minute: 3,
			runId: 'run_dbg02',
		},
		{
			id: 'msg_dbg04',
			from: viewerId,
			text: 'CI went green ten minutes ago',
			minute: 5,
			runId: 'run_dbg03',
		},
		{
			id: 'msg_dbg05',
			from: PEOPLE.grace.id,
			text: 'can someone summarise what changed?',
			minute: 6,
			runId: 'run_dbg04',
		},
		{
			id: 'msg_dbg06',
			from: 'agent',
			text: 'the migration renames the passages table and backfills anchors. no API surface changed, so clients need no update.',
			minute: 7,
			runId: 'run_dbg04',
			replyTo: 'msg_dbg05',
		},
		{
			id: 'msg_dbg07',
			from: PEOPLE.grace.id,
			text: 'perfect, thank you',
			minute: 8,
			runId: 'run_dbg05',
		},
	])
	const participants = [
		userParticipant(viewerId, 'you', true),
		userParticipant(PEOPLE.ada.id, PEOPLE.ada.name),
		userParticipant(PEOPLE.linus.id, PEOPLE.linus.name),
		userParticipant(PEOPLE.grace.id, PEOPLE.grace.name),
		agentParticipant(),
	]
	return { thread: thread(participants, 'msg_dbg07', 'ship day', viewerId), messages }
}

/**
 * replies that reach past the message directly above them - the case the
 * transcript renders a quote for.
 */
function crossTalk(viewerId: string): { thread: Thread; messages: ApiMessage[] } {
	const messages = chain([
		{
			id: 'msg_dbg11',
			from: PEOPLE.ada.id,
			text: 'i have two questions. first, do we keep the old cursors?',
			minute: 0,
			runId: 'run_dbg11',
		},
		{
			id: 'msg_dbg12',
			from: PEOPLE.linus.id,
			text: 'unrelated: the staging box is out of disk',
			minute: 1,
			runId: 'run_dbg12',
		},
		{
			id: 'msg_dbg13',
			from: viewerId,
			text: 'i cleared 40gb, should be fine now',
			minute: 2,
			runId: 'run_dbg13',
			replyTo: 'msg_dbg12',
		},
		{
			id: 'msg_dbg14',
			from: PEOPLE.grace.id,
			text: 'no, the old cursors are depth-based and break on append',
			minute: 4,
			runId: 'run_dbg14',
			replyTo: 'msg_dbg11',
		},
		{
			id: 'msg_dbg15',
			from: viewerId,
			text: '@assistant can you confirm that?',
			minute: 5,
			runId: 'run_dbg15',
		},
		{
			id: 'msg_dbg16',
			from: 'agent',
			text: 'confirmed. cursors store a message id precisely because depth counts from the leaf, so any append shifts it.',
			minute: 6,
			runId: 'run_dbg15',
			replyTo: 'msg_dbg15',
		},
		{
			id: 'msg_dbg17',
			from: 'agent',
			text: 'the older format is still accepted for one release, then rejected with a 422 that tells the client to reload.',
			minute: 6,
			runId: 'run_dbg15',
		},
	])
	const participants = [
		userParticipant(viewerId, 'you', true),
		userParticipant(PEOPLE.ada.id, PEOPLE.ada.name),
		userParticipant(PEOPLE.linus.id, PEOPLE.linus.name),
		userParticipant(PEOPLE.grace.id, PEOPLE.grace.name),
		agentParticipant(),
	]
	return { thread: thread(participants, 'msg_dbg17', 'cursors + staging', viewerId), messages }
}

/** a DM: exactly two humans, the smallest multi-writer thread. */
function directMessage(viewerId: string): { thread: Thread; messages: ApiMessage[] } {
	const messages = chain([
		{
			id: 'msg_dbg21',
			from: PEOPLE.ada.id,
			text: 'hey, got a minute?',
			minute: 0,
			runId: 'run_dbg21',
		},
		{
			id: 'msg_dbg22',
			from: viewerId,
			text: 'sure, what is up',
			minute: 1,
			runId: 'run_dbg22',
		},
		{
			id: 'msg_dbg23',
			from: PEOPLE.ada.id,
			text: 'the reply quote only shows when the answer reached past the line above it. is that deliberate?',
			minute: 2,
			runId: 'run_dbg23',
		},
		{
			id: 'msg_dbg24',
			from: viewerId,
			text: 'yes, otherwise every single turn would quote the message right above it',
			minute: 4,
			runId: 'run_dbg24',
			replyTo: 'msg_dbg23',
		},
	])
	const participants = [
		userParticipant(viewerId, 'you', true),
		userParticipant(PEOPLE.ada.id, PEOPLE.ada.name),
	]
	return { thread: thread(participants, 'msg_dbg24', 'ada lovelace', viewerId), messages }
}

/** a long same-author burst, for grouping and avatar placement. */
function rapidFire(viewerId: string): { thread: Thread; messages: ApiMessage[] } {
	const lines = [
		'ok so',
		'i looked into the flash timing',
		'1600ms was way too long',
		'it reads as a stain rather than a blink',
		'650 feels right',
		'anyway, done',
	]
	const messages = chain([
		{
			id: 'msg_dbg31',
			from: viewerId,
			text: 'how did the timing land?',
			minute: 0,
			runId: 'run_dbg31',
		},
		...lines.map((text, i) => ({
			id: `msg_dbg4${i}`,
			from: PEOPLE.linus.id,
			text,
			minute: 1 + i,
			runId: 'run_dbg32',
		})),
	])
	const participants = [
		userParticipant(viewerId, 'you', true),
		userParticipant(PEOPLE.linus.id, PEOPLE.linus.name),
	]
	return {
		thread: thread(participants, `msg_dbg4${lines.length - 1}`, 'linus', viewerId),
		messages,
	}
}

export const DEBUG_SCENARIOS: DebugScenario[] = [
	{
		id: 'group',
		label: 'group conversation',
		description: 'four humans and an agent. sender names, avatars, own-vs-other sides.',
		build: groupConversation,
	},
	{
		id: 'cross-talk',
		label: 'cross-talk replies',
		description: 'two conversations interleaved, so replies reach past the line above.',
		build: crossTalk,
	},
	{
		id: 'dm',
		label: 'direct message',
		description: 'exactly two humans - the smallest multi-writer thread.',
		build: directMessage,
	},
	{
		id: 'rapid-fire',
		label: 'rapid fire',
		description: 'one person sending six messages in a row. grouping and avatar placement.',
		build: rapidFire,
	},
]
