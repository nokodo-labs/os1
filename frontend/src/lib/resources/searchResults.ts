import type { SearchResult } from '$lib/api/streaming'
import type { ResourceAnchorRef, ResourceItem } from '$lib/components/widgets/types'

/** map generated search result types into widget resource types. */
function resourceTypeForSearchResult(type: SearchResult['type']): ResourceItem['type'] {
	return type === 'memory' ? 'file' : type
}

/** return the sub-resource anchor carried by a search result. */
function anchorForSearchResult(result: SearchResult): ResourceAnchorRef | undefined {
	return result.anchor ?? undefined
}

/**
 * every result is a routable container, so the href addresses the result itself,
 * with the anchor as the query param the target page focuses on arrival:
 * `?message=` on a thread, `?reminder=` on a list, `?event=` on the calendar.
 */
function hrefForSearchResult(result: SearchResult): string {
	const anchor = anchorForSearchResult(result)
	switch (result.type) {
		case 'thread':
			return anchor?.type === 'message'
				? `/c/${result.id}?message=${anchor.id}`
				: `/c/${result.id}`
		case 'note':
			return `/notes/${result.id}`
		case 'reminder_list':
			return anchor?.type === 'reminder'
				? `/reminders/lists/${result.id}?reminder=${anchor.id}`
				: `/reminders/lists/${result.id}`
		case 'calendar':
			return anchor?.type === 'calendar_event'
				? `/calendar?event=${anchor.id}&calendar=${result.id}`
				: '/calendar'
		case 'project':
			return `/projects/${result.id}`
		case 'memory':
		case 'file':
			return '#'
	}
}

export function searchResultToResource(result: SearchResult): ResourceItem {
	const timestamp = Date.now()
	const updatedAt = Date.parse(result.updated_at)
	const createdAt = Date.parse(result.created_at)
	return {
		id: result.id,
		type: resourceTypeForSearchResult(result.type),
		anchor: anchorForSearchResult(result),
		title: result.title,
		preview: result.preview ?? undefined,
		href: hrefForSearchResult(result),
		updatedAt: Number.isFinite(updatedAt) ? updatedAt : timestamp,
		createdAt: Number.isFinite(createdAt) ? createdAt : timestamp,
		meta: result.type === 'memory' ? { source: 'memory' } : result.metadata,
	}
}

/** list/dedup key: one container can yield one result per matched anchor. */
export function resourceItemKey(resource: Pick<ResourceItem, 'type' | 'id' | 'anchor'>): string {
	const anchor = resource.anchor ? `:${resource.anchor.id}` : ''
	return `${resource.type}:${resource.id}${anchor}`
}
