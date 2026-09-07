/**
 * per-message read receipts, derived from thread read cursors.
 *
 * a cursor is a single id - the last message a participant has read - so "did
 * they read this message" is a comparison, not a lookup. see
 * `cursorCoversMessage` for why comparing the ids as plain strings is sound.
 *
 * HONESTY: cursors only ever arrive over the live `thread.participants.*`
 * fanout; there is no GET for them yet (B16). a participant whose cursor has
 * not been seen THIS SESSION is `unknown`, never "unread" - a fresh load starts
 * with every receipt unknown and fills in as people read. renderers must draw
 * nothing at all for `unknown` rather than guessing a glyph.
 */

import { threadWriterUserIds, type Thread } from '$lib/stores/chat.svelte'

export type MessageReadState = 'unknown' | 'unread' | 'read'

/**
 * one participant's read cursor as this session knows it.
 *
 * the fanout carries no read TIME - only the message reached - so `at` is when
 * this session watched the cursor move, stamped on arrival. a cursor that was
 * already in place before we listened has none, and a receipt built on it says
 * the bare word rather than inventing a clock.
 */
export interface ReadCursor {
	messageId: string
	at: Date | null
}

export interface MessageReceipt {
	/** the message is persisted server-side (it has a real id). */
	sent: boolean
	state: MessageReadState
	/** audience members whose cursor is known to cover the message. */
	readBy: string[]
	/**
	 * when the message became read - the LAST of the audience to pass it, since
	 * that is the moment the whole audience had. null unless every one of them
	 * was watched arriving.
	 */
	readAt: Date | null
}

/**
 * whether a read cursor covers a message.
 *
 * message ids are a constant `msg_` prefix plus base32(uuid7) over an
 * ascii-ascending alphabet, so lexical order IS chronological order and a plain
 * string compare answers this without loading the cursor's message. this is the
 * ONLY place that comparison lives.
 */
export function cursorCoversMessage(cursorId: string, messageId: string): boolean {
	return cursorId >= messageId
}

/**
 * whose receipts count for a message the given user sent.
 *
 * writers only: agents never read, spectators are not part of the conversation,
 * and a writer group's members are not in the roster payload so they cannot be
 * counted either. the sender is excluded - their own cursor says nothing.
 */
export function receiptAudience(thread: Thread | null, senderUserId: string | null): string[] {
	return threadWriterUserIds(thread).filter((userId) => userId !== senderUserId)
}

/** audience members whose cursor is known to cover the message. */
export function readBy(
	messageId: string,
	cursors: ReadonlyMap<string, ReadCursor>,
	audience: readonly string[]
): string[] {
	return audience.filter((userId) => {
		const cursor = cursors.get(userId)
		return cursor !== undefined && cursorCoversMessage(cursor.messageId, messageId)
	})
}

/**
 * when the audience finished reading a message: the last of them to pass it.
 *
 * a single member whose cursor arrived without a time makes the answer unknown
 * rather than "as far as we saw" - a receipt that names the wrong moment reads
 * worse than one that names none.
 */
export function readCompletedAt(
	messageId: string,
	cursors: ReadonlyMap<string, ReadCursor>,
	audience: readonly string[]
): Date | null {
	if (audience.length === 0) return null
	let latest: Date | null = null
	for (const userId of audience) {
		const cursor = cursors.get(userId)
		if (!cursor || !cursorCoversMessage(cursor.messageId, messageId)) return null
		if (!cursor.at) return null
		if (!latest || cursor.at.getTime() > latest.getTime()) latest = cursor.at
	}
	return latest
}

/**
 * the WhatsApp rule, applied to DMs and groups alike: a message is `read` once
 * EVERY other writer's cursor covers it (in a DM that is the one other person).
 *
 * a single audience member with a known cursor that does not cover the message
 * already makes "read by all" false, so that is honestly `unread`. when the
 * only thing standing in the way is a participant nobody has heard from this
 * session, the answer is `unknown` - and so is an empty audience (a solo thread
 * has nobody to read it).
 */
export function messageReadState(
	messageId: string,
	cursors: ReadonlyMap<string, ReadCursor>,
	audience: readonly string[]
): MessageReadState {
	if (audience.length === 0) return 'unknown'
	let known = 0
	let covered = 0
	for (const userId of audience) {
		const cursor = cursors.get(userId)
		if (cursor === undefined) continue
		known += 1
		if (cursorCoversMessage(cursor.messageId, messageId)) covered += 1
	}
	if (covered === audience.length) return 'read'
	return known > covered ? 'unread' : 'unknown'
}

/**
 * the full receipt for one message.
 *
 * `messageId` is null while a message is still optimistic - nothing is
 * persisted, so it is not even `sent` yet.
 */
export function messageReceipt(
	messageId: string | null,
	thread: Thread | null,
	cursors: ReadonlyMap<string, ReadCursor>,
	senderUserId: string | null
): MessageReceipt {
	if (!messageId) return { sent: false, state: 'unknown', readBy: [], readAt: null }
	const audience = receiptAudience(thread, senderUserId)
	const state = messageReadState(messageId, cursors, audience)
	return {
		sent: true,
		state,
		readBy: readBy(messageId, cursors, audience),
		readAt: state === 'read' ? readCompletedAt(messageId, cursors, audience) : null,
	}
}
