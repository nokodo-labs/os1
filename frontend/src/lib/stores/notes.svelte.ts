/**
 * notes store - caches notes with API persistence + WS-driven real-time updates.
 *
 * cache strategy:
 * - generous TTL (30 min) with automatic refresh on API calls
 * - websocket events update cache directly (WS is source of truth)
 * - stale data is still displayed while fetching
 * - trust cache by default since websocket keeps it up to date
 */

import { browser } from '$app/environment'
import { apiClient } from '$lib/api/client'
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { onAccessTokenChanged } from '$lib/auth/session.svelte'
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

export type NotesSortBy = 'updated_at' | 'created_at' | 'title'
export type SortDir = 'asc' | 'desc'
export type NotesSortMode = `${NotesSortBy}:${SortDir}`

// cache TTL
const CACHE_TTL_MS = 30 * 60 * 1000 // 30 minutes

/** id → note (ordered: newest first) */
const notesMap = new SvelteMap<string, Note>()
let fetchedAt: number | null = null
let inFlight: Promise<Note[]> | null = null
let currentSortMode = $state<NotesSortMode>('updated_at:desc')

function parseSortMode(mode: NotesSortMode): { sort_by: NotesSortBy; sort_dir: SortDir } {
	const [sort_by, sort_dir] = mode.split(':') as [NotesSortBy, SortDir]
	return { sort_by, sort_dir }
}

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

	get sortMode(): NotesSortMode {
		return currentSortMode
	},
	set sortMode(mode: NotesSortMode) {
		if (mode === currentSortMode) return
		currentSortMode = mode
		fetchedAt = null
		void this.load({ force: true })
	},

	async load(options?: { force?: boolean }): Promise<Note[]> {
		const force = options?.force ?? false

		if (!force && isFresh()) {
			return this.all
		}

		if (inFlight) return inFlight

		inFlight = (async () => {
			const { sort_by, sort_dir } = parseSortMode(currentSortMode)
			const { data, error } = await apiClient().GET('/v1/notes', {
				params: { query: { sort_by, sort_dir } },
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

// event stream integration

let notesUnsub: (() => void) | null = null

function handleNoteEvent(message: StreamMessage): void {
	const data = message.data as Record<string, unknown> | undefined
	if (!data) return

	if (message.type === 'note.created') {
		const apiNote = data as unknown as ApiNote
		if (!apiNote?.id) return
		const note = toNote(apiNote)
		if (notesMap.has(note.id)) {
			// already exists (created locally): apply authoritative data
			notesMap.set(note.id, note)
		} else {
			// new note from another session: prepend
			const entries = [[note.id, note], ...notesMap.entries()] as [string, Note][]
			notesMap.clear()
			for (const [id, n] of entries) {
				notesMap.set(id, n)
			}
		}
		if (fetchedAt === null) fetchedAt = Date.now()
	} else if (message.type === 'note.updated') {
		const id = data.id as string
		if (!id) return
		const existing = notesMap.get(id)
		if (!existing) return
		// merge partial update into existing cache entry
		const merged = { ...existing }
		if ('title' in data) merged.title = data.title as string
		if ('content' in data) merged.content = data.content as string
		if ('labels' in data) merged.labels = (data.labels as string[]) ?? []
		if ('updated_at' in data) merged.updatedAt = new Date(data.updated_at as string).getTime()
		notesMap.set(id, merged)
	} else if (message.type === 'note.deleted') {
		const noteId = data.id as string
		if (noteId) notesMap.delete(noteId)
	}
}

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			if (!notesUnsub) {
				notesUnsub = eventStreamClient.subscribe(handleNoteEvent)
			}
		} else {
			notesUnsub?.()
			notesUnsub = null
			notesMap.clear()
			fetchedAt = null
		}
	})
}
