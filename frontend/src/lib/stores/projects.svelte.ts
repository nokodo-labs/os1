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
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { showError } from '$lib/stores/notifications.svelte'
import { SvelteMap } from 'svelte/reactivity'

export type Project = components['schemas']['Project']
export type ProjectCreate = components['schemas']['ProjectCreate']
export type ProjectUpdate = components['schemas']['ProjectUpdate']

const CACHE_TTL_MS = 30 * 60 * 1000

const PROJECT_EVENT_TYPES = ['project.created', 'project.updated', 'project.deleted']

interface ProjectsCacheEntry {
	data: SvelteMap<string, Project>
	fetchedAt: number
}

function buildCache(projects: Project[], fetchedAt: number): ProjectsCacheEntry {
	const data = new SvelteMap<string, Project>()
	for (const project of projects) {
		data.set(project.id, project)
	}
	return { data, fetchedAt }
}

// projects cache

class ProjectsCache {
	#cache = $state<ProjectsCacheEntry | null>(null)
	#inFlight: Promise<Project[]> | null = null
	#unsubscribe: (() => void) | null = null

	// event stream integration

	init(): void {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleStreamEvent)
		}
	}

	cleanup(): void {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	/**
	 * handle incoming stream events for projects.
	 * WS is the canonical source of truth - apply event data directly.
	 */
	#handleStreamEvent = (message: StreamMessage): void => {
		if (!PROJECT_EVENT_TYPES.includes(message.type)) return
		const data = message.data as Record<string, unknown> | undefined
		if (!data) return

		switch (message.type) {
			case 'project.created': {
				const project = data as unknown as Project
				if (!project?.id || !this.#cache) return
				this.#cache.data.set(project.id, project)
				break
			}
			case 'project.updated': {
				const project = data as unknown as Project
				if (!project?.id || !this.#cache) return
				const existing = this.#cache.data.get(project.id)
				if (existing) {
					this.#cache.data.set(project.id, { ...existing, ...project })
				}
				break
			}
			case 'project.deleted': {
				const id = data.id as string
				if (id) this.#cache?.data.delete(id)
				break
			}
		}
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

	get isFresh(): boolean {
		return this.#cache !== null && this.#isFresh(this.#cache.fetchedAt)
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
			created_at: new Date().toISOString(),
			updated_at: new Date().toISOString(),
		} as Project
		this.#cache?.data.set(tempId, placeholder)

		try {
			const { data, error } = await api.POST('/v1/projects', { body: params })

			if (error || !data) {
				if (doRollback) this.#cache?.data.delete(tempId)
				showError('could not create project')
				return null
			}

			// replace placeholder with real project
			this.#cache?.data.delete(tempId)
			this.#cache?.data.set(data.id, data)
			return data
		} catch {
			if (doRollback) this.#cache?.data.delete(tempId)
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
		this.#cache = null
	}

	clear(): void {
		this.#cache = null
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
