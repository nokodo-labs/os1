/**
 * message tree navigation - branch switching, leaf resolution, run user lookup.
 */

import { api } from '$lib/api/client'
import { SvelteSet } from 'svelte/reactivity'
import type { RunBlock } from './helpers'
import type { ChatContext } from './types'

/** walk children to find the latest (rightmost) leaf in a subtree */
export function getLatestLeaf(rootId: string, ctx: ChatContext): string {
	let curr = rootId
	while (true) {
		const kids = ctx.messageChildren.get(curr)
		if (!kids || kids.length === 0) return curr
		curr = kids[kids.length - 1]
	}
}

/** check if a leaf node is on the streaming branch by walking up to the streaming leaf */
export function isOnStreamingBranch(leafId: string, ctx: ChatContext): boolean {
	if (!ctx.streamingLeafId) {
		// if we haven't created the message yet, we are on the streaming branch
		// only if we are sitting at the parent (waiting for it)
		return ctx.streamingAssistantParentId ? leafId === ctx.streamingAssistantParentId : true
	}
	const visited = new SvelteSet<string>()
	let curr: string | null = ctx.streamingLeafId
	while (curr) {
		if (visited.has(curr)) break
		visited.add(curr)
		if (curr === leafId) return true
		const msg = ctx.messageTree.get(curr)
		if (!msg) break
		curr = msg.parent_id ?? null
	}
	return false
}

/** switch to a sibling branch at a given message node */
export async function switchBranch(
	messageId: string,
	direction: 'prev' | 'next',
	ctx: ChatContext
): Promise<void> {
	let parentId: string | null
	let siblings: string[]
	let idx: number
	let pendingVirtual = false

	const msg = ctx.messageTree.get(messageId)
	if (msg) {
		parentId = msg.parent_id ?? null
		siblings = ctx.messageChildren.get(parentId) ?? []
		idx = siblings.indexOf(messageId)
	} else if (ctx.isGenerating && ctx.streamingAssistantParentId) {
		// pending streaming placeholder not yet in the tree
		parentId = ctx.streamingAssistantParentId
		siblings = ctx.messageChildren.get(parentId) ?? []
		idx = siblings.length // virtual last entry
		pendingVirtual = true
	} else {
		return
	}

	if (idx === -1) return

	const totalCount = siblings.length + (pendingVirtual ? 1 : 0)
	if (totalCount <= 1) return

	const targetIdx = direction === 'prev' ? idx - 1 : idx + 1
	if (targetIdx < 0 || targetIdx >= totalCount) return

	// navigating back to the virtual pending entry (only during the brief pre-delta window)
	if (pendingVirtual && targetIdx >= siblings.length) {
		ctx.viewingStreamingBranch = true
		ctx.currentLeafId = ctx.streamingLeafId ?? ctx.streamingAssistantParentId
		ctx.rebuildRunBlocks()
		return
	}

	const targetId = siblings[targetIdx]
	const newLeaf = getLatestLeaf(targetId, ctx)

	if (ctx.isGenerating) {
		const onStreaming = isOnStreamingBranch(newLeaf, ctx)
		ctx.viewingStreamingBranch = onStreaming
		ctx.currentLeafId = onStreaming && ctx.streamingLeafId ? ctx.streamingLeafId : newLeaf
		ctx.rebuildRunBlocks()
		return
	}

	ctx.currentLeafId = newLeaf
	ctx.rebuildRunBlocks()

	// persist branch selection to backend
	if (ctx.thread) {
		try {
			await api.PATCH('/v1/threads/{thread_id}', {
				params: { path: { thread_id: ctx.thread.id } },
				body: { current_message_id: newLeaf },
			})
			ctx.thread = { ...ctx.thread, current_message_id: newLeaf }
		} catch (e) {
			console.error('failed to persist branch selection', e)
		}
	}
}

/**
 * find the user message that started a run by walking up from the response root.
 */
export function findRunUserMessage(block: RunBlock, ctx: ChatContext): string | null {
	const firstResponseId = block.responseRootId
	if (!firstResponseId) return null
	const firstResponse = ctx.messageTree.get(firstResponseId)
	if (!firstResponse) return null
	// walk up to find the user message
	const visited = new SvelteSet<string>()
	let parentId = firstResponse.parent_id
	while (parentId) {
		if (visited.has(parentId)) break
		visited.add(parentId)
		const parent = ctx.messageTree.get(parentId)
		if (!parent) break
		if (parent.type === 'user') return parent.id
		parentId = parent.parent_id
	}
	return null
}
