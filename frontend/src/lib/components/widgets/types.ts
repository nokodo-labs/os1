/**
 * shared types for resource widgets and the resources view.
 *
 * resource identity types come from the generated backend API schema.
 */

import type { components } from '$lib/api/types'

export type ResourceType = components['schemas']['SearchResourceReferenceType']

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

export type ResourceParentRef = components['schemas']['SearchResultParent']

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
	parent?: ResourceParentRef
	title: string
	subtitle?: string
	preview?: string
	href: string
	updatedAt: number
	createdAt: number
	meta?: Record<string, unknown>
}
