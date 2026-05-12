/**
 * projects store - caches project list with WS-driven real-time updates.
 *
 * cache strategy:
 * - generous TTL (30 min) with automatic refresh on API calls
 * - websocket events trigger refetch (WS is source of truth)
 * - stale data is still displayed while fetching
 * - trust cache by default since websocket keeps it up to date
 */

import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import type { StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { showError } from '$lib/stores/notifications.svelte'
import { STORE_EVENT_TYPES, subscribeToStoreEvents } from '$lib/stores/storeEvents'
import { SvelteMap } from 'svelte/reactivity'

export type Project = components['schemas']['Project']
export type ProjectCreate = components['schemas']['ProjectCreate']
export type ProjectResourceCounts = components['schemas']['ProjectResourceCounts']
export type ProjectUpdate = components['schemas']['ProjectUpdate']

const CACHE_TTL_MS = 30 * 60 * 1000

const PROJECT_EVENT_TYPES = new Set<string>(STORE_EVENT_TYPES.projects)
const PROJECT_ACCESS_EVENT_TYPES = new Set<string>(STORE_EVENT_TYPES.resourceAccessResource)
const PROJECT_COUNT_EVENT_TYPES = new Set<string>(STORE_EVENT_TYPES.projectCounts)
const PROJECT_STREAM_EVENT_TYPES = [
	...STORE_EVENT_TYPES.projects,
	...STORE_EVENT_TYPES.resourceAccessResource,
	...STORE_EVENT_TYPES.projectCounts,
] as const

interface ProjectsCacheEntry {
	data: SvelteMap<string, Project>
	fetchedAt: number
}

interface ProjectCountsCacheEntry {
	data: ProjectResourceCounts
	fetchedAt: number
}

function buildCache(projects: Project[], fetchedAt: number): ProjectsCacheEntry {
	const data = new SvelteMap<string, Project>()
	for (const project of projects) {
		data.set(project.id, project)
	}
	return { data, fetchedAt }
}

function emptyProjectResourceCounts(): ProjectResourceCounts {
	return {
		thread_count: 0,
		note_count: 0,
		file_count: 0,
		reminder_list_count: 0,
		calendar_count: 0,
		resource_count: 0,
	} as ProjectResourceCounts
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null
}

function stringField(data: Record<string, unknown>, key: string): string | null {
	const value = data[key]
	return typeof value === 'string' && value.length > 0 ? value : null
}

function eventProjectId(data: Record<string, unknown>): string | null {
	return stringField(data, 'id') ?? stringField(data, 'project_id')
}

function accessProjectId(data: Record<string, unknown>): string | null {
	if (data.resource_type !== 'project') return null
	return stringField(data, 'resource_id')
}

function isCompleteProject(
	data: Record<string, unknown>
): data is Record<string, unknown> & Project {
	return Boolean(
		stringField(data, 'id') &&
		stringField(data, 'owner_id') &&
		Array.isArray(data.thread_ids) &&
		stringField(data, 'created_at') &&
		stringField(data, 'updated_at')
	)
}

function extractProjectIds(data: Record<string, unknown>): string[] {
	const ids: string[] = []
	const addId = (id: string): void => {
		if (!ids.includes(id)) ids.push(id)
	}
	const projectIds = data.project_ids
	if (Array.isArray(projectIds)) {
		for (const id of projectIds) {
			if (typeof id === 'string' && id.length > 0) addId(id)
		}
	}

	const projects = data.projects
	if (Array.isArray(projects)) {
		for (const project of projects) {
			if (isRecord(project)) {
				const id = stringField(project, 'id')
				if (id) addId(id)
			}
		}
	}

	const projectId = stringField(data, 'project_id')
	if (projectId) addId(projectId)

	return ids
}

// projects cache

class ProjectsCache {
	#cache = $state<ProjectsCacheEntry | null>(null)
	#countCache = new SvelteMap<string, ProjectCountsCacheEntry>()
	#inFlight: Promise<Project[]> | null = null
	#countInFlight = new Map<string, Promise<ProjectResourceCounts | null>>()
	#unsubscribe: (() => void) | null = null

	// event stream integration

	init(): void {
		if (!this.#unsubscribe) {
			this.#unsubscribe = subscribeToStoreEvents(
				PROJECT_STREAM_EVENT_TYPES,
				this.#handleStreamEvent
			)
		}
	}

	cleanup(): void {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	/** handle incoming stream events that affect project visibility or counts. */
	#handleStreamEvent = (message: StreamMessage): void => {
		const data = isRecord(message.data) ? message.data : null
		if (!data) return

		if (PROJECT_EVENT_TYPES.has(message.type)) {
			this.#handleProjectEvent(message.type, data)
			return
		}
		if (PROJECT_ACCESS_EVENT_TYPES.has(message.type)) {
			this.#handleProjectAccessEvent(data)
			return
		}
		if (PROJECT_COUNT_EVENT_TYPES.has(message.type)) {
			this.#handleProjectCountEvent(data)
		}
	}

	#handleProjectEvent(type: string, data: Record<string, unknown>): void {
		const id = eventProjectId(data)
		if (!id) return

		switch (type) {
			case 'project.created': {
				void this.#refreshProject(id)
				break
			}
			case 'project.updated': {
				if (this.#cache) {
					const existing = this.#cache.data.get(id)
					if (isCompleteProject(data)) {
						this.#cache.data.set(id, data)
					} else if (existing) {
						this.#cache.data.set(id, { ...existing, ...data } as Project)
					}
				}
				void this.#refreshProject(id)
				break
			}
			case 'project.deleted': {
				this.#cache?.data.delete(id)
				this.#countCache.delete(id)
				break
			}
		}
	}

	#handleProjectAccessEvent(data: Record<string, unknown>): void {
		const id = accessProjectId(data)
		if (!id) return
		this.invalidateResourceCounts([id])
		void this.#refreshProject(id)
	}

	#handleProjectCountEvent(data: Record<string, unknown>): void {
		const projectIds = extractProjectIds(data)
		const loadedProjectIds = projectIds.filter((id) => this.#countCache.has(id))
		this.invalidateResourceCounts(projectIds)
		for (const id of loadedProjectIds) {
			void this.loadResourceCounts(id, { force: true })
		}
	}

	async #refreshProject(id: string): Promise<Project | null> {
		if (!this.#cache) return null
		const { data, error } = await api.GET('/v1/projects/{project_id}', {
			params: { path: { project_id: id } },
		})
		if (error || !data) {
			this.#cache.data.delete(id)
			this.#countCache.delete(id)
			return null
		}
		this.#cache.data.set(data.id, data)
		return data
	}

	#isFresh(fetchedAt: number): boolean {
		return Date.now() - fetchedAt < CACHE_TTL_MS
	}

	// reads

	get list(): Project[] {
		return this.#cache ? [...this.#cache.data.values()] : []
	}

	getById(id: string): Project | null {
		return this.#cache?.data.get(id) ?? null
	}

	resourceCounts(id: string): ProjectResourceCounts | null {
		return this.#countCache.get(id)?.data ?? null
	}

	get isFresh(): boolean {
		return this.#cache !== null && this.#isFresh(this.#cache.fetchedAt)
	}

	get hasLoaded(): boolean {
		return this.#cache !== null
	}

	// load

	async load(options?: { force?: boolean }): Promise<Project[]> {
		const force = options?.force ?? false

		if (!force && this.isFresh) return this.list
		if (this.#inFlight) return this.#inFlight

		this.#inFlight = (async () => {
			const { data, error } = await api.GET('/v1/projects', {
				params: { query: { sort_by: 'updated_at', sort_dir: 'desc' } },
			})
			if (error || !data) return this.list
			this.#cache = buildCache(data, Date.now())
			return this.list
		})()

		try {
			return await this.#inFlight
		} finally {
			this.#inFlight = null
		}
	}

	async loadResourceCounts(
		id: string,
		options?: { force?: boolean }
	): Promise<ProjectResourceCounts | null> {
		const force = options?.force ?? false
		const cached = this.#countCache.get(id) ?? null
		if (!force && cached && this.#isFresh(cached.fetchedAt)) return cached.data

		const inFlight = this.#countInFlight.get(id)
		if (inFlight) return inFlight

		const request = (async () => {
			const { data, error } = await api.GET('/v1/projects/{project_id}/resource_counts', {
				params: { path: { project_id: id } },
			})
			if (error || !data) return cached?.data ?? null
			this.#countCache.set(id, { data, fetchedAt: Date.now() })
			return data
		})()

		this.#countInFlight.set(id, request)
		try {
			return await request
		} finally {
			if (this.#countInFlight.get(id) === request) {
				this.#countInFlight.delete(id)
			}
		}
	}

	// mutations - return optimistic data for caller; WS delivers truth

	async create(params: ProjectCreate, options?: { rollback?: boolean }): Promise<Project | null> {
		const doRollback = options?.rollback ?? true
		// optimistic: add placeholder project immediately
		const tempId = `temp-${Date.now()}`
		const placeholder: Project = {
			id: tempId,
			name: params.name,
			description: params.description ?? '',
			owner_id: '',
			thread_ids: [],
			created_at: new Date().toISOString(),
			updated_at: new Date().toISOString(),
		} as Project
		this.#cache?.data.set(tempId, placeholder)
		this.#countCache.set(tempId, { data: emptyProjectResourceCounts(), fetchedAt: Date.now() })

		try {
			const { data, error } = await api.POST('/v1/projects', { body: params })

			if (error || !data) {
				if (doRollback) this.#cache?.data.delete(tempId)
				this.#countCache.delete(tempId)
				showError('could not create project')
				return null
			}

			// replace placeholder with real project
			this.#cache?.data.delete(tempId)
			this.#countCache.delete(tempId)
			this.#cache?.data.set(data.id, data)
			this.#countCache.set(data.id, {
				data: emptyProjectResourceCounts(),
				fetchedAt: Date.now(),
			})
			return data
		} catch {
			if (doRollback) this.#cache?.data.delete(tempId)
			this.#countCache.delete(tempId)
			showError('could not create project')
			return null
		}
	}

	async update(
		id: string,
		params: ProjectUpdate,
		options?: { rollback?: boolean }
	): Promise<Project | null> {
		const doRollback = options?.rollback ?? true
		const existing = this.#cache?.data.get(id) ?? null

		// optimistic: apply update immediately
		if (existing) {
			this.#cache?.data.set(id, {
				...existing,
				...params,
				updated_at: new Date().toISOString(),
			} as Project)
		}

		try {
			const { data, error } = await api.PATCH('/v1/projects/{project_id}', {
				params: { path: { project_id: id } },
				body: params,
			})

			if (error || !data) {
				if (doRollback && existing) this.#cache?.data.set(id, existing)
				showError('could not update project')
				return null
			}

			this.#cache?.data.set(id, data)
			return data
		} catch {
			if (doRollback && existing) this.#cache?.data.set(id, existing)
			showError('could not update project')
			return null
		}
	}

	async remove(id: string, options?: { rollback?: boolean }): Promise<boolean> {
		const doRollback = options?.rollback ?? true
		const existing = this.#cache?.data.get(id) ?? null

		// optimistic: remove immediately
		this.#cache?.data.delete(id)
		this.#countCache.delete(id)

		try {
			const { error } = await api.DELETE('/v1/projects/{project_id}', {
				params: { path: { project_id: id } },
			})

			if (error) {
				if (doRollback && existing) this.#cache?.data.set(id, existing)
				showError('could not delete project')
				return false
			}

			return true
		} catch {
			if (doRollback && existing) this.#cache?.data.set(id, existing)
			showError('could not delete project')
			return false
		}
	}

	// lifecycle

	invalidate(): void {
		if (this.#cache) this.#cache.fetchedAt = 0
		this.invalidateResourceCounts()
	}

	invalidateResourceCounts(projectIds?: Iterable<string>): void {
		if (!projectIds) {
			for (const entry of this.#countCache.values()) entry.fetchedAt = 0
			return
		}
		for (const id of projectIds) {
			const entry = this.#countCache.get(id)
			if (entry) entry.fetchedAt = 0
		}
	}

	async refreshCached(): Promise<void> {
		const tasks: Promise<unknown>[] = []
		if (this.#cache) tasks.push(this.load({ force: true }))
		for (const id of this.#countCache.keys()) {
			tasks.push(this.loadResourceCounts(id, { force: true }))
		}
		await Promise.allSettled(tasks)
	}

	async refresh(): Promise<void> {
		await this.refreshCached()
	}

	clear(): void {
		this.#cache = null
		this.#countCache.clear()
	}
}

// singleton export

export const projects = new ProjectsCache()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			projects.init()
		} else {
			projects.cleanup()
			projects.clear()
		}
	})

	// subscribe immediately if already authenticated
	// (module may be imported after auth when navigating to a project page)
	if (getAccessToken()) {
		projects.init()
	}
}
