/**
 * `/branch` page loading, shared by the thread loader and the thread cache.
 *
 * a branch page is the ONE message-loading path: it carries a window of the
 * selected chain plus the branches hanging off it. keeping the request and the
 * cached shape in one module is what stops a second loader from writing a
 * branch-blind `/messages` list into the cache the loader reads back.
 */

import { api } from '$lib/api/client'
import type { components, paths } from '$lib/api/types'

type ApiMessage = components['schemas']['Message']

export type BranchPage = components['schemas']['BranchPageOut_Message_']

type BranchQuery = NonNullable<
	paths['/v1/threads/{thread_id}/branch']['get']['parameters']['query']
>

/** `/branch` caps limit at 200. */
export const BRANCH_PAGE_LIMIT = 120

/**
 * paging state a branch page leaves behind, kept next to its messages.
 *
 * depth is counted from the branch leaf, so every offset shifts the moment
 * anyone appends: scroll with these cursors, never with `skip`.
 */
export interface BranchPaging {
	/** next page toward the branch root; null when the root is loaded. */
	cursorTowardRoot: string | null
	/** next page toward the branch leaf; null when the tail is loaded. */
	cursorTowardLeaf: string | null
	hasTowardRoot: boolean
	hasTowardLeaf: boolean
	/** full alternative count per forked message, as `[parent_id, total]`. */
	siblingCounts: [string, number][]
}

export interface BranchPageQuery {
	limit?: number
	cursor?: string
	anchorMessageId?: string
}

export interface BranchPageResult {
	page: BranchPage | null
	status: number | undefined
}

/** fetch one branch page; a null page carries the status so callers can react. */
export async function fetchBranchPage(
	threadId: string,
	query: BranchPageQuery = {}
): Promise<BranchPageResult> {
	const params: BranchQuery = { limit: query.limit ?? BRANCH_PAGE_LIMIT }
	if (query.cursor) params.cursor = query.cursor
	if (query.anchorMessageId) params.anchor_message_id = query.anchorMessageId

	const { data, error, response } = await api.GET('/v1/threads/{thread_id}/branch', {
		params: { path: { thread_id: threadId }, query: params },
	})
	if (error || !data) return { page: null, status: response?.status }
	return { page: data, status: response?.status }
}

/** what a page says about continuing in either direction. */
export function branchPagingOf(page: BranchPage): BranchPaging {
	return {
		cursorTowardRoot: page.has_toward_root ? (page.cursor_toward_root ?? null) : null,
		cursorTowardLeaf: page.has_toward_leaf ? (page.cursor_toward_leaf ?? null) : null,
		hasTowardRoot: page.has_toward_root,
		hasTowardLeaf: page.has_toward_leaf,
		siblingCounts: page.sibling_counts.map((entry) => [entry.parent_id, entry.total]),
	}
}

export function mergeMessages(...groups: ApiMessage[][]): ApiMessage[] {
	const byId = new Map<string, ApiMessage>()
	for (const group of groups) {
		for (const msg of group) byId.set(msg.id, msg)
	}
	return Array.from(byId.values())
}

/** everything a page contributes to the tree: its chain plus carried branches. */
export function branchPageMessages(page: BranchPage): ApiMessage[] {
	return mergeMessages(page.messages, page.siblings)
}
