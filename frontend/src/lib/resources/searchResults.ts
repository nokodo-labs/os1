import type { SearchResult } from '$lib/api/streaming'
import type { ResourceItem } from '$lib/components/widgets/types'

function resourceTypeForSearchResult(type: SearchResult['type']): ResourceItem['type'] {
	switch (type) {
		case 'thread':
			return 'thread'
		case 'note':
			return 'note'
		case 'reminder':
			return 'reminder_list'
		case 'calendar_event':
			return 'calendar'
		case 'memory':
			return 'file'
		case 'project':
			return 'project'
	}
}

function hrefForSearchResult(result: SearchResult): string {
	switch (result.type) {
		case 'thread':
			return `/c/${result.id}`
		case 'note':
			return `/notes/${result.id}`
		case 'reminder':
			return `/reminders/lists/${result.id}`
		case 'calendar_event':
			return '/calendar'
		case 'memory':
			return '#'
		case 'project':
			return `/projects/${result.id}`
	}
}

export function searchResultToResource(result: SearchResult): ResourceItem {
	const timestamp = Date.now()
	const updatedAt = Date.parse(result.updated_at)
	const createdAt = Date.parse(result.created_at)
	return {
		id: result.id,
		type: resourceTypeForSearchResult(result.type),
		title: result.title,
		preview: result.preview ?? undefined,
		href: hrefForSearchResult(result),
		updatedAt: Number.isFinite(updatedAt) ? updatedAt : timestamp,
		createdAt: Number.isFinite(createdAt) ? createdAt : timestamp,
		meta: result.type === 'memory' ? { source: 'memory' } : result.metadata,
	}
}
