import type { SearchResult, SearchResultParent } from '$lib/api/streaming'
import type { ResourceItem } from '$lib/components/widgets/types'

/** map generated search result types into widget resource types. */
function resourceTypeForSearchResult(type: SearchResult['type']): ResourceItem['type'] {
	return type === 'memory' ? 'file' : type
}

/** return the immediate parent resource carried by a search result. */
function parentForSearchResult(result: SearchResult): SearchResultParent | undefined {
	return result.parent ?? undefined
}

function hrefForSearchResult(result: SearchResult): string {
	switch (result.type) {
		case 'thread':
			return `/c/${result.id}`
		case 'note':
			return `/notes/${result.id}`
		case 'reminder': {
			const parent = parentForSearchResult(result)
			return parent?.type === 'reminder_list' ? `/reminders/lists/${parent.id}` : '#'
		}
		case 'calendar_event':
			return '#'
		case 'memory':
			return '#'
		case 'project':
			return `/projects/${result.id}`
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
		parent: parentForSearchResult(result),
		title: result.title,
		preview: result.preview ?? undefined,
		href: hrefForSearchResult(result),
		updatedAt: Number.isFinite(updatedAt) ? updatedAt : timestamp,
		createdAt: Number.isFinite(createdAt) ? createdAt : timestamp,
		meta: result.type === 'memory' ? { source: 'memory' } : result.metadata,
	}
}
