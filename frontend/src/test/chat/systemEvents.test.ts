/**
 * inline chat system events: parsing the canonical events into rows, the copy
 * each row renders, and the two beginning-of-chat headers.
 */

import {
	beginningOfChatSegments,
	parseChatSystemEvents,
	systemEventSegments,
	systemEventUserIds,
	type ChatSystemEvent,
	type RawSystemEvent,
	type SystemNameResolver,
} from '$lib/chat/systemEvents'
import { describe, expect, it } from 'vitest'

const threadId = 'thread_1'
const alice = 'user_alice'
const bob = 'user_bob'

const names: Record<string, string> = {
	[alice]: 'alice',
	[bob]: 'bob',
	group_crew: 'the crew',
	agent_nova: 'nova',
}

function resolver(currentUserId: string | null = null): SystemNameResolver {
	return { currentUserId, name: (id) => names[id] ?? null }
}

function copy(event: ChatSystemEvent, currentUserId: string | null = null): string {
	return systemEventSegments(event, resolver(currentUserId))
		.map((segment) => segment.text)
		.join('')
}

function accessEvent(
	changes: Array<{ before: unknown; after: unknown }>,
	overrides: Partial<RawSystemEvent> = {}
): RawSystemEvent {
	return {
		id: 'event_access',
		type: 'access.updated',
		thread_id: threadId,
		created_at: '2026-01-01T00:00:10.000Z',
		data: {
			resource_type: 'thread',
			resource_id: threadId,
			actor_user_id: alice,
			revision: 3,
			changes,
		},
		...overrides,
	}
}

function rule(overrides: Record<string, unknown>): Record<string, unknown> {
	return {
		id: 'rule_1',
		subject_user_id: null,
		subject_group_id: null,
		subject_role_id: null,
		level: 'editor',
		order_index: 0,
		...overrides,
	}
}

describe('parseChatSystemEvents - access.updated membership', () => {
	it('reads an added member from a rule that appeared', () => {
		const [row] = parseChatSystemEvents(
			accessEvent([{ before: null, after: rule({ subject_user_id: bob }) }])
		)

		expect(row.kind).toBe('member_added')
		expect(row.subjectId).toBe(bob)
		expect(row.actorUserId).toBe(alice)
		expect(copy(row)).toBe('alice added bob to this chat')
	})

	it('calls a reader grant an invitation, not an addition', () => {
		const [row] = parseChatSystemEvents(
			accessEvent([{ before: null, after: rule({ subject_user_id: bob, level: 'reader' }) }])
		)

		expect(row.kind).toBe('member_invited')
		expect(copy(row)).toBe('alice invited bob to this chat')
	})

	it('reads a removal from a rule that disappeared', () => {
		const [row] = parseChatSystemEvents(
			accessEvent([{ before: rule({ subject_user_id: bob }), after: null }])
		)

		expect(row.kind).toBe('member_removed')
		expect(copy(row)).toBe('alice removed bob from this chat')
	})

	it('calls it leaving when the actor removed themselves', () => {
		const [row] = parseChatSystemEvents(
			accessEvent([{ before: rule({ subject_user_id: alice }), after: null }])
		)

		expect(row.kind).toBe('member_left')
		expect(copy(row)).toBe('alice left the chat')
	})

	it('calls an accepted invite joining', () => {
		const [row] = parseChatSystemEvents(
			accessEvent([
				{
					before: rule({ subject_user_id: alice, level: 'reader' }),
					after: rule({ subject_user_id: alice, level: 'editor' }),
				},
			])
		)

		expect(row.kind).toBe('member_joined')
		expect(copy(row)).toBe('alice joined the chat')
	})

	it('reports another person level change', () => {
		const [row] = parseChatSystemEvents(
			accessEvent([
				{
					before: rule({ subject_user_id: bob, level: 'reader' }),
					after: rule({ subject_user_id: bob, level: 'editor' }),
				},
			])
		)

		expect(row.kind).toBe('member_access_changed')
		expect(copy(row)).toBe("alice changed bob's access to editor")
	})

	it('renders group shares and un-shares', () => {
		const [added] = parseChatSystemEvents(
			accessEvent([{ before: null, after: rule({ subject_group_id: 'group_crew' }) }])
		)
		const [removed] = parseChatSystemEvents(
			accessEvent([{ before: rule({ subject_group_id: 'group_crew' }), after: null }])
		)

		expect(copy(added)).toBe('alice shared this chat with the crew')
		expect(copy(removed)).toBe('alice removed the crew from this chat')
	})

	it('names the reader as "you"', () => {
		const [row] = parseChatSystemEvents(
			accessEvent([{ before: null, after: rule({ subject_user_id: bob }) }])
		)

		expect(copy(row, alice)).toBe('you added bob to this chat')
	})

	it('emits one row per change and keeps them distinct', () => {
		const rows = parseChatSystemEvents(
			accessEvent([
				{ before: null, after: rule({ subject_user_id: bob }) },
				{ before: rule({ subject_user_id: alice }), after: null },
			])
		)

		expect(rows).toHaveLength(2)
		expect(new Set(rows.map((row) => row.id)).size).toBe(2)
	})

	it('ignores rules that name nobody, and rewrites that changed nothing', () => {
		expect(
			parseChatSystemEvents(
				accessEvent([{ before: null, after: rule({ subject_role_id: 'role_1' }) }])
			)
		).toEqual([])
		expect(
			parseChatSystemEvents(
				accessEvent([
					{
						before: rule({ subject_user_id: bob, order_index: 0 }),
						after: rule({ subject_user_id: bob, order_index: 1 }),
					},
				])
			)
		).toEqual([])
	})

	it('ignores acl changes on anything that is not this thread', () => {
		expect(
			parseChatSystemEvents(
				accessEvent([{ before: null, after: rule({ subject_user_id: bob }) }], {
					data: {
						resource_type: 'note',
						resource_id: 'note_1',
						changes: [{ before: null, after: rule({ subject_user_id: bob }) }],
					},
				})
			)
		).toEqual([])
	})

	it('keeps the payload anchor so the row can survive a reload', () => {
		const [row] = parseChatSystemEvents(
			accessEvent([{ before: null, after: rule({ subject_user_id: bob }) }], {
				data: {
					resource_type: 'thread',
					resource_id: threadId,
					actor_user_id: alice,
					message_id: 'msg_head',
					changes: [{ before: null, after: rule({ subject_user_id: bob }) }],
				},
			})
		)

		expect(row.messageId).toBe('msg_head')
	})
})

describe('parseChatSystemEvents - agent presence', () => {
	function agentEvent(type: string): RawSystemEvent {
		return {
			id: 'event_agent',
			type,
			thread_id: threadId,
			message_id: 'msg_head',
			created_at: '2026-01-01T00:00:20.000Z',
			data: {
				thread_id: threadId,
				actor_user_id: alice,
				actor_name: 'alice',
				kind: 'agent',
				agent_id: 'agent_nova',
				agent_name: 'nova',
			},
		}
	}

	it('renders an agent joining and leaving the chat', () => {
		const [added] = parseChatSystemEvents(agentEvent('thread.participants.added'))
		const [removed] = parseChatSystemEvents(agentEvent('thread.participants.removed'))

		expect(added.kind).toBe('agent_added')
		expect(added.messageId).toBe('msg_head')
		expect(copy(added)).toBe('alice added nova to this chat')
		expect(copy(removed)).toBe('alice removed nova from this chat')
	})

	it('ignores the user-state twin that rides the same event types', () => {
		expect(
			parseChatSystemEvents({
				id: 'event_state',
				type: 'thread.participants.updated',
				thread_id: threadId,
				data: {
					thread_id: threadId,
					user_id: bob,
					kind: 'user',
					last_read_message_id: 'msg_1',
				},
			})
		).toEqual([])
		expect(
			parseChatSystemEvents({
				id: 'event_state',
				type: 'thread.participants.added',
				thread_id: threadId,
				data: { thread_id: threadId, user_id: bob, kind: 'user', muted: true },
			})
		).toEqual([])
	})
})

describe('parseChatSystemEvents - renames', () => {
	function renamed(data: Record<string, unknown>): RawSystemEvent {
		return {
			id: 'event_rename',
			type: 'thread.updated',
			thread_id: threadId,
			created_at: '2026-01-01T00:00:30.000Z',
			data,
		}
	}

	it('stays silent unless renames are asked for', () => {
		expect(parseChatSystemEvents(renamed({ id: threadId, title: 'trip' }))).toEqual([])
	})

	it('renders the rename without a name when the actor is unknowable', () => {
		const [row] = parseChatSystemEvents(renamed({ id: threadId, title: 'trip' }), {
			renameRows: true,
		})

		expect(row.kind).toBe('title_changed')
		expect(copy(row)).toBe('the chat title is now trip')
	})

	it('names the reader for their own rename', () => {
		const [row] = parseChatSystemEvents(renamed({ id: threadId, title: 'trip' }), {
			renameRows: true,
			selfActorUserId: alice,
		})

		expect(copy(row, alice)).toBe('you changed the chat title to trip')
	})

	it('ignores an activity bump and a whole-thread republish', () => {
		expect(
			parseChatSystemEvents(renamed({ id: threadId, last_activity_at: 'now' }), {
				renameRows: true,
			})
		).toEqual([])
		expect(
			parseChatSystemEvents(
				renamed({ id: threadId, title: 'trip', created_at: 'then', participants: [] }),
				{ renameRows: true }
			)
		).toEqual([])
	})
})

describe('systemEventUserIds', () => {
	it('collects the people a row names, and never a group or an agent', () => {
		const [member] = parseChatSystemEvents(
			accessEvent([{ before: null, after: rule({ subject_user_id: bob }) }])
		)
		const [group] = parseChatSystemEvents(
			accessEvent([{ before: null, after: rule({ subject_group_id: 'group_crew' }) }])
		)

		expect(systemEventUserIds([member, group])).toEqual([alice, bob])
	})
})

describe('beginningOfChatSegments', () => {
	function text(segments: { text: string }[]): string {
		return segments.map((segment) => segment.text).join('')
	}

	it('names the other person in a one-to-one chat', () => {
		expect(
			text(
				beginningOfChatSegments({
					kind: 'direct',
					counterpartName: 'bob',
					chatName: null,
					creatorName: null,
				})
			)
		).toBe('this is the beginning of your chat with bob')
	})

	it('names the founding of a group', () => {
		expect(
			text(
				beginningOfChatSegments({
					kind: 'group',
					counterpartName: null,
					chatName: 'the crew',
					creatorName: 'alice',
				})
			)
		).toBe('alice created the crew')
	})

	it('degrades gracefully when the group has no name or no known creator', () => {
		expect(
			text(
				beginningOfChatSegments({
					kind: 'group',
					counterpartName: null,
					chatName: null,
					creatorName: 'alice',
				})
			)
		).toBe('alice created this group chat')
		expect(
			text(
				beginningOfChatSegments({
					kind: 'group',
					counterpartName: null,
					chatName: 'the crew',
					creatorName: null,
				})
			)
		).toBe('this is the beginning of the crew')
		expect(
			beginningOfChatSegments({
				kind: 'group',
				counterpartName: null,
				chatName: null,
				creatorName: null,
			})
		).toEqual([])
	})

	it('opens a solo chat with the assistant it names, and stays silent otherwise', () => {
		expect(
			text(
				beginningOfChatSegments({
					kind: 'solo',
					counterpartName: 'nova',
					chatName: null,
					creatorName: null,
				})
			)
		).toBe('this is the beginning of your chat with nova')
		expect(
			beginningOfChatSegments({
				kind: 'solo',
				counterpartName: null,
				chatName: null,
				creatorName: null,
			})
		).toEqual([])
	})
})
