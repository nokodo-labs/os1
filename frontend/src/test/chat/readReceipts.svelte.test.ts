/**
 * read receipt derivation: cursor -> per-message sent/read/unknown state.
 *
 * uses .svelte.test.ts because the helper reaches into chat.svelte.ts for the
 * writer roster.
 */

import {
	cursorCoversMessage,
	messageReadState,
	messageReceipt,
	readBy,
	readCompletedAt,
	receiptAudience,
	type ReadCursor,
} from '$lib/chat/readReceipts'
import type { Thread } from '$lib/stores/chat.svelte'
import { describe, expect, it } from 'vitest'
import { makeThread } from './fixtures'

type Participant = NonNullable<Thread['participants']>[number]
type Level = 'reader' | 'editor' | 'admin' | null

function user(id: string, access_level: Level, is_owner = false): Participant {
	return {
		id: `p_${id}`,
		thread_id: 'thread_1',
		access_level,
		is_owner,
		kind: 'user',
		user: { id },
	}
}

function agent(id: string): Participant {
	return {
		id: `p_${id}`,
		thread_id: 'thread_1',
		access_level: 'editor',
		is_owner: false,
		kind: 'agent',
		agent: { id, name: id },
	}
}

function thread(participants: Participant[]): Thread {
	return makeThread({ id: 'thread_1', owner_id: 'me', participants })
}

const dm = thread([user('me', 'admin', true), user('them', 'editor')])
const group = thread([user('me', 'admin', true), user('a', 'editor'), user('b', 'editor')])

/** three ids in the real `msg_` + base32(uuid7) shape, ascending. */
const OLD = 'msg_0197h2m8k0f7z9s5q3x1c4b6d8'
const MID = 'msg_0197h2m8k9f7z9s5q3x1c4b6d8'
const NEW = 'msg_0197h2m9a0f7z9s5q3x1c4b6d8'

/** cursors with no observed read time - the cold-open shape. */
function cursors(entries: Record<string, string>): Map<string, ReadCursor> {
	return new Map(
		Object.entries(entries).map(([userId, messageId]) => [userId, { messageId, at: null }])
	)
}

/** cursors this session watched arrive, so each carries a moment. */
function timedCursors(entries: Record<string, [string, Date | null]>): Map<string, ReadCursor> {
	return new Map(
		Object.entries(entries).map(([userId, [messageId, at]]) => [userId, { messageId, at }])
	)
}

describe('cursorCoversMessage', () => {
	it('orders ids lexicographically, which is chronologically', () => {
		expect(cursorCoversMessage(NEW, OLD)).toBe(true)
		expect(cursorCoversMessage(OLD, NEW)).toBe(false)
	})

	it('a cursor covers the message it points at', () => {
		expect(cursorCoversMessage(MID, MID)).toBe(true)
	})

	it('holds across a timestamp boundary, where only the prefix differs', () => {
		// same uuid7 random tail, one timestamp tick apart: the compare must be
		// decided by the leading time bits, not by the tail.
		const earlier = 'msg_0197h2m8kzf7z9s5q3x1c4b6d8'
		const later = 'msg_0197h2m8m0f7z9s5q3x1c4b6d8'
		expect(cursorCoversMessage(later, earlier)).toBe(true)
		expect(cursorCoversMessage(earlier, later)).toBe(false)
	})
})

describe('receiptAudience', () => {
	it('is the other writer in a DM', () => {
		expect(receiptAudience(dm, 'me')).toEqual(['them'])
	})

	it('is every other writer in a group', () => {
		expect(receiptAudience(group, 'me')).toEqual(['a', 'b'])
	})

	it('excludes agents and spectators', () => {
		const t = thread([
			user('me', 'admin', true),
			user('them', 'editor'),
			user('lurker', 'reader'),
			agent('bot'),
		])
		expect(receiptAudience(t, 'me')).toEqual(['them'])
	})

	it('is empty in a solo thread and for a null thread', () => {
		expect(receiptAudience(thread([user('me', 'admin', true), agent('bot')]), 'me')).toEqual([])
		expect(receiptAudience(null, 'me')).toEqual([])
	})
})

describe('messageReadState - DM', () => {
	const audience = receiptAudience(dm, 'me')

	it('is read when the other cursor is at or past the message', () => {
		expect(messageReadState(MID, cursors({ them: MID }), audience)).toBe('read')
		expect(messageReadState(MID, cursors({ them: NEW }), audience)).toBe('read')
	})

	it('is unread when the other cursor is behind the message', () => {
		expect(messageReadState(MID, cursors({ them: OLD }), audience)).toBe('unread')
	})

	it('is unknown before any cursor has been seen this session', () => {
		expect(messageReadState(MID, cursors({}), audience)).toBe('unknown')
	})

	it('ignores the sender own cursor, which says nothing', () => {
		expect(messageReadState(MID, cursors({ me: NEW }), audience)).toBe('unknown')
	})
})

describe('messageReadState - group', () => {
	const audience = receiptAudience(group, 'me')

	it('is read only when every other writer has passed the message', () => {
		expect(messageReadState(MID, cursors({ a: MID, b: NEW }), audience)).toBe('read')
	})

	it('is unread while one known writer is behind', () => {
		expect(messageReadState(MID, cursors({ a: NEW, b: OLD }), audience)).toBe('unread')
	})

	it('is unread when nobody has reached it', () => {
		expect(messageReadState(MID, cursors({ a: OLD, b: OLD }), audience)).toBe('unread')
	})

	it('is unknown when the only missing writer is one nobody has heard from', () => {
		expect(messageReadState(MID, cursors({ a: NEW }), audience)).toBe('unknown')
	})

	it('is unknown when the audience is empty', () => {
		expect(messageReadState(MID, cursors({ a: NEW }), [])).toBe('unknown')
	})
})

describe('readBy', () => {
	it('lists only the audience members known to have passed the message', () => {
		const audience = receiptAudience(group, 'me')
		expect(readBy(MID, cursors({ a: NEW, b: OLD }), audience)).toEqual(['a'])
		expect(readBy(MID, cursors({ a: NEW, b: MID, me: NEW }), audience)).toEqual(['a', 'b'])
		expect(readBy(MID, cursors({}), audience)).toEqual([])
	})
})

describe('readCompletedAt', () => {
	const groupAudience = receiptAudience(group, 'me')
	const early = new Date('2026-09-01T10:00:00Z')
	const late = new Date('2026-09-01T14:30:00Z')

	it('is the LAST of the audience to pass the message', () => {
		expect(
			readCompletedAt(MID, timedCursors({ a: [MID, early], b: [NEW, late] }), groupAudience)
		).toEqual(late)
	})

	it('is unknown while somebody is still behind', () => {
		expect(
			readCompletedAt(MID, timedCursors({ a: [MID, early], b: [OLD, late] }), groupAudience)
		).toBeNull()
	})

	it('is unknown when a covering cursor arrived without a time', () => {
		// a cold-open cursor: it says WHAT was read, never when.
		expect(
			readCompletedAt(MID, timedCursors({ a: [MID, early], b: [NEW, null] }), groupAudience)
		).toBeNull()
	})

	it('is unknown for an empty audience', () => {
		expect(readCompletedAt(MID, timedCursors({ a: [NEW, late] }), [])).toBeNull()
	})
})

describe('messageReceipt', () => {
	it('an optimistic message is not even sent yet', () => {
		expect(messageReceipt(null, dm, cursors({ them: NEW }), 'me')).toEqual({
			sent: false,
			state: 'unknown',
			readBy: [],
			readAt: null,
		})
	})

	it('a persisted message is sent, and read once the other side passes it', () => {
		expect(messageReceipt(MID, dm, cursors({ them: NEW }), 'me')).toEqual({
			sent: true,
			state: 'read',
			readBy: ['them'],
			readAt: null,
		})
	})

	it('carries the moment the read was observed', () => {
		const at = new Date('2026-09-01T14:30:00Z')
		expect(messageReceipt(MID, dm, timedCursors({ them: [NEW, at] }), 'me')).toEqual({
			sent: true,
			state: 'read',
			readBy: ['them'],
			readAt: at,
		})
	})

	it('a persisted message with no cursors is sent but unknown', () => {
		expect(messageReceipt(MID, dm, cursors({}), 'me')).toEqual({
			sent: true,
			state: 'unknown',
			readBy: [],
			readAt: null,
		})
	})
})
