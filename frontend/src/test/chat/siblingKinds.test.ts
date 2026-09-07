/**
 * a message's alternatives are the children of its parent of the SAME kind.
 * mixing them is what made a brand new message flash a "2/2" branch badge: the
 * run's own user message lands under the same parent as the answer that run has
 * not produced yet.
 */

import { buildMessageChildren, siblingIdsOfKind } from '$lib/chat/helpers'
import type { ApiMessage } from '$lib/chat/types'
import { describe, expect, it } from 'vitest'
import { makeApiMessage } from './fixtures'

function tree(messages: ApiMessage[]): {
	children: Map<string | null, string[]>
	byId: Map<string, ApiMessage>
} {
	return {
		children: buildMessageChildren(messages),
		byId: new Map(messages.map((message) => [message.id, message])),
	}
}

function at(seconds: number): string {
	return new Date(Date.UTC(2026, 0, 1, 0, 0, seconds)).toISOString()
}

describe('siblingIdsOfKind', () => {
	it('does not count a run own user message as an alternative answer', () => {
		// the moment between "the message landed" and "the answer exists" is the
		// whole bug: the placeholder is parented at the previous leaf, and the
		// new user message is a child of that same leaf.
		const previousAnswer = makeApiMessage({
			id: 'a0',
			type: 'assistant',
			parent_id: 'u0',
			created_at: at(1),
		})
		const justSent = makeApiMessage({
			id: 'u1',
			type: 'user',
			parent_id: 'a0',
			created_at: at(2),
		})
		const { children, byId } = tree([previousAnswer, justSent])

		expect(siblingIdsOfKind('a0', 'response', children, byId)).toEqual([])
	})

	it('counts a root user message as user traffic, never as a response', () => {
		const firstMessage = makeApiMessage({ id: 'u1', type: 'user', parent_id: null })
		const { children, byId } = tree([firstMessage])

		expect(siblingIdsOfKind(null, 'response', children, byId)).toEqual([])
		expect(siblingIdsOfKind(null, 'user', children, byId)).toEqual(['u1'])
	})

	it('keeps every real alternative answer on a fork', () => {
		const anchor = makeApiMessage({
			id: 'u1',
			type: 'user',
			parent_id: null,
			created_at: at(1),
		})
		const first = makeApiMessage({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			created_at: at(2),
		})
		const regenerated = makeApiMessage({
			id: 'a2',
			type: 'assistant',
			parent_id: 'u1',
			created_at: at(3),
		})
		const toolOutput = makeApiMessage({
			id: 't1',
			type: 'tool',
			parent_id: 'u1',
			created_at: at(4),
		})
		const { children, byId } = tree([anchor, first, regenerated, toolOutput])

		expect(siblingIdsOfKind('u1', 'response', children, byId)).toEqual(['a1', 'a2', 't1'])
		expect(siblingIdsOfKind('u1', 'user', children, byId)).toEqual([])
	})

	it('ignores children the tree has not loaded', () => {
		const { children, byId } = tree([])
		children.set('u1', ['missing'])

		expect(siblingIdsOfKind('u1', 'response', children, byId)).toEqual([])
	})
})
