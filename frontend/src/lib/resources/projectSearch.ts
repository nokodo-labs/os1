/**
 * search inside one project.
 *
 * the unified search endpoint takes no project filter, so a scoped search asks
 * the per-resource endpoints, which do: `/v1/threads/search` and
 * `/v1/notes/search` both take `project_id`. they answer with the resources
 * themselves rather than search result items, so a scoped hit carries no matched
 * passage preview and no anchor: it routes to the thread or note, nothing more.
 */

import { api } from '$lib/api/client'
import type { SearchResourceType } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import type { ResourceItem } from '$lib/components/widgets/types'

type ApiThread = components['schemas']['Thread']
type ApiNote = components['schemas']['Note']

const DEFAULT_LIMIT = 20
const NOTE_PREVIEW_LENGTH = 200

export interface ProjectSearchOptions {
	query: string
	projectId: string
	/** result kinds to look for; only threads and notes are project-scopable. */
	types?: SearchResourceType[]
	limit?: number
	/**
	 * also match messages on branches that were edited or regenerated away.
	 *
	 * left off for user-facing search: such a message is not on the branch the
	 * thread opens at, so the chat page cannot reveal it (the anchor falls back
	 * to the live tail) and the hit reads as a broken result.
	 */
	includeAllBranches?: boolean
	signal?: AbortSignal
}

function threadToResource(thread: ApiThread): ResourceItem {
	return {
		id: thread.id,
		type: 'thread',
		title: thread.title ?? 'untitled chat',
		href: `/c/${thread.id}`,
		updatedAt: Date.parse(thread.last_activity_at),
		createdAt: Date.parse(thread.created_at),
		meta: {
			tags: thread.tags,
			owner_id: thread.owner_id,
			project_ids: thread.project_ids,
		},
	}
}

function noteToResource(note: ApiNote): ResourceItem {
	return {
		id: note.id,
		type: 'note',
		title: note.title || 'untitled note',
		preview: note.content.slice(0, NOTE_PREVIEW_LENGTH),
		href: `/notes/${note.id}`,
		updatedAt: Date.parse(note.updated_at),
		createdAt: Date.parse(note.created_at),
		meta: {
			labels: note.labels,
			owner_id: note.user_id,
			project_ids: note.project_ids,
		},
	}
}

/**
 * ranked hits from both endpoints, merged newest first.
 *
 * the two rankings cannot be compared to each other, so recency is what orders
 * the merged list.
 */
export async function searchProjectResources(
	options: ProjectSearchOptions
): Promise<ResourceItem[]> {
	const limit = options.limit ?? DEFAULT_LIMIT
	const types = options.types
	const wantsThreads = !types || types.includes('thread')
	const wantsNotes = !types || types.includes('note')

	const [threads, notes] = await Promise.all([
		wantsThreads
			? api.GET('/v1/threads/search', {
					params: {
						query: {
							q: options.query,
							limit,
							project_id: options.projectId,
							include_all_branches: options.includeAllBranches ?? false,
						},
					},
					signal: options.signal,
				})
			: null,
		wantsNotes
			? api.GET('/v1/notes/search', {
					params: {
						query: { q: options.query, limit, project_id: options.projectId },
					},
					signal: options.signal,
				})
			: null,
	])

	return [
		...(threads?.data?.items ?? []).map(threadToResource),
		...(notes?.data?.items ?? []).map(noteToResource),
	].sort((first, second) => second.updatedAt - first.updatedAt)
}
