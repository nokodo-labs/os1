/**
 * notes store - caches notes with API persistence.
 * follows similar pattern to reminders store.
 *
 * cache strategy:
 * - generous TTL with automatic refresh on API calls
 * - stale data is still displayed while fetching
 * - trust cache by default
 */

import { apiClient } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { SvelteMap } from 'svelte/reactivity'

// types from API
type ApiNote = components['schemas']['Note']

export interface Note {
	id: string
	title: string
	content: string
	labels: string[]
	createdAt: number
	updatedAt: number
}

// cache TTL
const CACHE_TTL_MS = 30 * 60 * 1000 // 30 minutes

/** id → note (ordered: newest first) */
const notesMap = new SvelteMap<string, Note>()
let fetchedAt: number | null = null
let inFlight: Promise<Note[]> | null = null

function isFresh(): boolean {
	return fetchedAt !== null && Date.now() - fetchedAt < CACHE_TTL_MS
}

function toNote(apiNote: ApiNote): Note {
	return {
		id: apiNote.id,
		title: apiNote.title,
		content: apiNote.content,
		labels: apiNote.labels ?? [],
		createdAt: new Date(apiNote.created_at).getTime(),
		updatedAt: new Date(apiNote.updated_at).getTime(),
	}
}

export const notes = {
	get hydrated() {
		return fetchedAt !== null
	},
	/** all notes (ordered: newest first) */
	get all(): Note[] {
		return [...notesMap.values()]
	},

	async load(options?: { force?: boolean }): Promise<Note[]> {
		const force = options?.force ?? false

		if (!force && isFresh()) {
			return this.all
		}

		if (inFlight) return inFlight

		inFlight = (async () => {
			const { data, error } = await apiClient().GET('/v1/notes', {
				params: { query: { sort_by: 'updated_at', sort_dir: 'desc' } },
			})
			if (error || !data) return this.all

			notesMap.clear()
			for (const apiNote of data) {
				const note = toNote(apiNote)
				notesMap.set(note.id, note)
			}
			fetchedAt = Date.now()
			return this.all
		})()

		try {
			return await inFlight
		} finally {
			inFlight = null
		}
	},

	get(noteId: string): Note | null {
		return notesMap.get(noteId) ?? null
	},

	async create(): Promise<Note | null> {
		const { data, error } = await apiClient().POST('/v1/notes', {
			body: { title: '', content: '' },
		})
		if (error || !data) return null

		const created = toNote(data)

		// prepend: rebuild map with new entry first
		const entries = [[created.id, created], ...notesMap.entries()] as [string, Note][]
		notesMap.clear()
		for (const [id, note] of entries) {
			notesMap.set(id, note)
		}

		return created
	},

	async update(noteId: string, updates: { title?: string; content?: string }): Promise<void> {
		const existing = notesMap.get(noteId)
		if (!existing) return

		const nextTitle = updates.title ?? existing.title
		const nextContent = updates.content ?? existing.content
		if (nextTitle === existing.title && nextContent === existing.content) return

		// optimistic update
		notesMap.set(noteId, {
			...existing,
			title: nextTitle,
			content: nextContent,
			updatedAt: Date.now(),
		})

		const { error } = await apiClient().PUT('/v1/notes/{note_id}', {
			params: { path: { note_id: noteId } },
			body: { title: nextTitle, content: nextContent },
		})

		if (error) {
			// rollback on failure
			notesMap.set(noteId, existing)
		}
	},

	async remove(noteId: string): Promise<boolean> {
		const existing = notesMap.get(noteId)
		if (!existing) return false

		// optimistic delete
		notesMap.delete(noteId)

		const { error } = await apiClient().DELETE('/v1/notes/{note_id}', {
			params: { path: { note_id: noteId } },
		})

		if (error) {
			// rollback on failure
			notesMap.set(noteId, existing)
			return false
		}

		return true
	},
}
