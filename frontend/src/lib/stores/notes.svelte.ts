import { browser } from '$app/environment'
import { SvelteMap } from 'svelte/reactivity'

export interface Note {
	id: string
	title: string
	content: string
	createdAt: number
	updatedAt: number
}

const STORAGE_KEY = 'notes'

/** id → note (ordered: newest first) */
const notesMap = new SvelteMap<string, Note>()
let hydratedState = $state(false)

function nowMs(): number {
	return Date.now()
}

function newNoteId(): string {
	if (browser && typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
		return crypto.randomUUID()
	}
	return `${nowMs()}-${Math.random().toString(16).slice(2)}`
}

function readStoredNotes(): Note[] {
	if (!browser) return []
	const raw = window.localStorage.getItem(`${STORAGE_KEY}:data`)
	if (!raw) return []

	try {
		const parsed: unknown = JSON.parse(raw)
		if (!Array.isArray(parsed)) return []

		const out: Note[] = []
		for (const item of parsed) {
			if (!item || typeof item !== 'object') continue
			const record = item as Record<string, unknown>

			const id = typeof record.id === 'string' ? record.id : null
			const title = typeof record.title === 'string' ? record.title : ''
			const content = typeof record.content === 'string' ? record.content : ''
			const createdAt = typeof record.createdAt === 'number' ? record.createdAt : nowMs()
			const updatedAt = typeof record.updatedAt === 'number' ? record.updatedAt : createdAt
			if (!id) continue

			out.push({ id, title, content, createdAt, updatedAt })
		}
		return out
	} catch {
		return []
	}
}

function writeStoredNotes(): void {
	if (!browser) return
	window.localStorage.setItem(`${STORAGE_KEY}:data`, JSON.stringify([...notesMap.values()]))
}

export const notes = {
	get hydrated() {
		return hydratedState
	},
	/** all notes (ordered: newest first) */
	get all(): Note[] {
		return [...notesMap.values()]
	},
	/** @deprecated use `notes.all` instead */
	get data() {
		return this.all
	},
	hydrate(): void {
		if (hydratedState) return
		for (const note of readStoredNotes()) {
			notesMap.set(note.id, note)
		}
		hydratedState = true
	},
	get(noteId: string): Note | null {
		return notesMap.get(noteId) ?? null
	},
	/** @deprecated use `notes.get()` instead */
	getById(noteId: string): Note | null {
		return this.get(noteId)
	},
	create(): Note {
		const now = nowMs()
		const created: Note = {
			id: newNoteId(),
			title: '',
			content: '',
			createdAt: now,
			updatedAt: now,
		}
		// prepend: rebuild map with new entry first
		const entries = [[created.id, created], ...notesMap.entries()] as [string, Note][]
		notesMap.clear()
		for (const [id, note] of entries) {
			notesMap.set(id, note)
		}
		writeStoredNotes()
		return created
	},
	update(noteId: string, updates: { title?: string; content?: string }): void {
		const existing = notesMap.get(noteId)
		if (!existing) return

		const nextTitle = updates.title ?? existing.title
		const nextContent = updates.content ?? existing.content
		if (nextTitle === existing.title && nextContent === existing.content) return

		notesMap.set(noteId, {
			...existing,
			title: nextTitle,
			content: nextContent,
			updatedAt: nowMs(),
		})
		writeStoredNotes()
	},
	remove(noteId: string): void {
		if (!notesMap.delete(noteId)) return
		writeStoredNotes()
	},
}
