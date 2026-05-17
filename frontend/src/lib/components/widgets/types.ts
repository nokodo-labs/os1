/**
 * shared types for resource widgets and the resources view.
 *
 * resource types closely map to the backend AccessRule model's FK columns,
 * which define all resource types a user can interact with.
 */

export type ResourceType = 'thread' | 'note' | 'reminder_list' | 'project' | 'file' | 'calendar'

export type ResourceSortBy = 'updated_at' | 'created_at' | 'title'
export type SortDir = 'asc' | 'desc'
export type ResourceSortMode = `${ResourceSortBy}:${SortDir}`

export type ResourceFilterMode =
	| 'all'
	| 'threads'
	| 'notes'
	| 'reminders'
	| 'files'
	| 'projects'
	| 'calendars'

export type ResourceLayoutMode = 'grid' | 'list'

/** shared props accepted by all resource widget components */
export interface WidgetProps {
	resource: ResourceItem
	layout?: ResourceLayoutMode
	class?: string
	onclick?: () => void
}

export interface ResourceItem {
	id: string
	type: ResourceType
	title: string
	subtitle?: string
	preview?: string
	href: string
	updatedAt: number
	createdAt: number
	meta?: Record<string, unknown>
}
