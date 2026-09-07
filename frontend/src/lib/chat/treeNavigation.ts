/**
 * message tree navigation - branch switching, leaf resolution, run user lookup.
 */

import { api } from '$lib/api/client'
import { SvelteSet } from 'svelte/reactivity'
import { fetchEventsForThread, ingestMessages } from './dataLoader'
import { siblingIdsOfKind, type RunBlock } from './helpers'
import type { ChatContext } from './types'

/**
 * how many alternatives a branch page carries per forked message.
 *
 * the page reports the FULL count in `sibling_counts` but ships only the first
 * few branches, so anything past this cap is paged from the siblings endpoint.
 */
const SIBLING_FANOUT_CAP = 5

/** how many extra alternatives one overflow fetch pulls in. */
const SIBLING_OVERFLOW_LIMIT = 50

/** walk children to find the latest (rightmost) leaf in a subtree */
export function getLatestLeaf(rootId: string, ctx: ChatContext): string {
	let curr = rootId
	while (true) {
		const kids = ctx.messageChildren.get(curr)
		if (!kids || kids.length === 0) return curr
		curr = kids[kids.length - 1]
	}
}

/**
 * move traffic the backend displaced onto its new parent: a run answers the
 * snapshot it last read, so its output lands BEFORE traffic it never saw.
 * order is the tree, never arrival time. returns whether the view changed.
 */
export function reparentSuccessors(
	ctx: ChatContext,
	parentId: string,
	messageIds: readonly string[] | null | undefined
): boolean {
	if (!messageIds || messageIds.length === 0) return false
	// unknown parent: leave them for the next reload rather than orphan them.
	if (!ctx.messageTree.has(parentId)) return false
	let changed = false
	let movedId: string | null = null
	for (const id of messageIds) {
		if (id === parentId) continue
		const existing = ctx.messageTree.get(id)
		if (!existing) continue
		movedId = id
		if ((existing.parent_id ?? null) === parentId) continue
		ctx.messageTree.set(id, { ...existing, parent_id: parentId })
		changed = true
	}
	// follow the traffic down, unless a live bubble is streaming (it renders
	// after the whole branch).
	if (movedId && ctx.currentLeafId === parentId && !ctx.streamingAssistant) {
		const leafId = getLatestLeaf(movedId, ctx)
		if (leafId !== ctx.currentLeafId) {
			ctx.currentLeafId = leafId
			changed = true
		}
	}
	return changed
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

/**
 * pull in the alternatives a branch page could not carry.
 *
 * a page ships at most five branches per forked message while `sibling_counts`
 * reports the true total, so a fork with more than that has alternatives the
 * tree has never seen. they are always the newest ones (the endpoint orders by
 * creation), so they page from the cap onward. returns whether anything new
 * landed in the tree.
 */
async function loadOverflowSiblings(parentId: string, ctx: ChatContext): Promise<boolean> {
	const threadId = ctx.thread?.id
	if (!threadId) return false
	const total = ctx.siblingCounts.get(parentId)
	const known = (ctx.messageChildren.get(parentId) ?? []).length
	if (!total || known >= total) return false

	const { data, error } = await api.GET(
		'/v1/threads/{thread_id}/messages/{message_id}/siblings',
		{
			params: {
				path: { thread_id: threadId, message_id: parentId },
				query: {
					skip: Math.max(known, SIBLING_FANOUT_CAP),
					limit: SIBLING_OVERFLOW_LIMIT,
				},
			},
		}
	)
	if (error || !data || data.length === 0) return false
	if (threadId !== ctx.thread?.id) return false

	const fresh = data.filter((message) => !ctx.messageTree.has(message.id))
	if (fresh.length === 0) return false
	ingestMessages(fresh, ctx)
	await fetchEventsForThread(
		threadId,
		fresh.map((message) => message.id),
		ctx,
		() => threadId === ctx.thread?.id
	)
	return true
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

	// the switcher walks alternatives of one kind, exactly as the timeline
	// counts them: mixing user traffic with a run's output would step onto an
	// entry the indicator never showed.
	const siblingsOf = (parent: string | null, kind: 'user' | 'response'): string[] =>
		siblingIdsOfKind(parent, kind, ctx.messageChildren, ctx.messageTree)

	const msg = ctx.messageTree.get(messageId)
	if (msg) {
		parentId = msg.parent_id ?? null
		siblings = siblingsOf(parentId, msg.type === 'user' ? 'user' : 'response')
		idx = siblings.indexOf(messageId)
	} else if (ctx.isGenerating && ctx.streamingAssistantParentId) {
		// pending streaming placeholder not yet in the tree
		parentId = ctx.streamingAssistantParentId
		siblings = siblingsOf(parentId, 'response')
		idx = siblings.length // virtual last entry
		pendingVirtual = true
	} else {
		return
	}

	if (idx === -1) return

	// a fork can hold more alternatives than a page carries, and the extra ones
	// are always the newest, so reaching the end of what is loaded is where the
	// rest get pulled in.
	if (
		parentId &&
		!pendingVirtual &&
		direction === 'next' &&
		idx === siblings.length - 1 &&
		(await loadOverflowSiblings(parentId, ctx))
	) {
		siblings = siblingsOf(parentId, msg && msg.type === 'user' ? 'user' : 'response')
		idx = siblings.indexOf(messageId)
		if (idx === -1) return
	}

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

	const leafBeforeSwitch = ctx.currentLeafId
	ctx.currentLeafId = newLeaf
	ctx.rebuildRunBlocks()

	// selecting canon is its own operation, not a thread field write: in a
	// multi-writer thread it needs `threads:manage` and 403s without it.
	if (ctx.thread && newLeaf) {
		const threadId = ctx.thread.id
		// a rejected switch never moved the server, so keeping the view on the
		// new branch shows one the thread does not have - it snaps back on the
		// next reload with nothing to explain it. put the reader where they were.
		const revertRoam = (): void => {
			if (ctx.thread?.id !== threadId || ctx.currentLeafId !== newLeaf) return
			ctx.currentLeafId = leafBeforeSwitch
			ctx.rebuildRunBlocks()
		}
		try {
			const { data, error } = await api.POST('/v1/threads/{thread_id}/switch', {
				params: { path: { thread_id: threadId } },
				body: { message_id: newLeaf },
			})
			if (error || !data?.ok) {
				console.error('failed to persist branch selection', error)
				revertRoam()
				return
			}
			ctx.thread = {
				...ctx.thread,
				current_message_id: data.current_message_id ?? newLeaf,
			}
		} catch (e) {
			console.error('failed to persist branch selection', e)
			revertRoam()
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
