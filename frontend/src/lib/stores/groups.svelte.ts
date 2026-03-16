/**
 * groups store - caches group list + memberships with WS-driven real-time updates.
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
import { SvelteMap } from 'svelte/reactivity'

export type Group = components['schemas']['Group']
export type GroupCreate = components['schemas']['GroupCreate']
export type GroupUpdate = components['schemas']['GroupUpdate']
export type GroupMembershipCreate = components['schemas']['GroupMembershipCreate']
export type GroupMembershipResponse = components['schemas']['GroupMembershipResponse']
export type GroupMemberRole = components['schemas']['GroupMemberRole']

const CACHE_TTL_MS = 30 * 60 * 1000

const GROUP_EVENT_TYPES = [
	'group.created',
	'group.updated',
	'group.deleted',
	'group.member_added',
	'group.member_removed',
]

interface GroupsCacheEntry {
	data: SvelteMap<string, Group>
	fetchedAt: number
}

function buildCache(groups: Group[], fetchedAt: number): GroupsCacheEntry {
	const data = new SvelteMap<string, Group>()
	for (const group of groups) {
		data.set(group.id, group)
	}
	return { data, fetchedAt }
}

// groups cache

class GroupsCache {
	#cache = $state<GroupsCacheEntry | null>(null)
	#inFlight: Promise<Group[]> | null = null
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
	 * handle incoming stream events for groups.
	 * WS is the canonical source of truth - refetch on any group mutation.
	 */
	#handleStreamEvent = (message: StreamMessage): void => {
		if (GROUP_EVENT_TYPES.includes(message.type)) {
			void this.load({ force: true })
		}
	}

	#isFresh(fetchedAt: number): boolean {
		return Date.now() - fetchedAt < CACHE_TTL_MS
	}

	// reads

	get list(): Group[] {
		return this.#cache ? [...this.#cache.data.values()] : []
	}

	getById(id: string): Group | null {
		return this.#cache?.data.get(id) ?? null
	}

	get isFresh(): boolean {
		return this.#cache !== null && this.#isFresh(this.#cache.fetchedAt)
	}

	// load

	async load(options?: { force?: boolean }): Promise<Group[]> {
		const force = options?.force ?? false

		if (!force && this.isFresh) return this.list
		if (this.#inFlight) return this.#inFlight

		this.#inFlight = (async () => {
			const { data, error } = await api.GET('/v1/groups', {
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

	async create(params: GroupCreate): Promise<Group | null> {
		const { data, error } = await api.POST('/v1/groups', { body: params })
		if (error || !data) return null
		return data
	}

	async update(id: string, params: GroupUpdate): Promise<Group | null> {
		const { data, error } = await api.PATCH('/v1/groups/{group_id}', {
			params: { path: { group_id: id } },
			body: params,
		})
		if (error || !data) return null
		return data
	}

	async remove(id: string): Promise<boolean> {
		const { error } = await api.DELETE('/v1/groups/{group_id}', {
			params: { path: { group_id: id } },
		})
		return !error
	}

	async addMember(
		groupId: string,
		member: GroupMembershipCreate
	): Promise<GroupMembershipResponse | null> {
		const { data, error } = await api.POST('/v1/groups/{group_id}/members', {
			params: { path: { group_id: groupId } },
			body: member,
		})
		if (error || !data) return null
		return data
	}

	async removeMember(groupId: string, userId: string): Promise<boolean> {
		const { error } = await api.DELETE('/v1/groups/{group_id}/members/{user_id}', {
			params: { path: { group_id: groupId, user_id: userId } },
		})
		return !error
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

export const groups = new GroupsCache()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			groups.init()
		} else {
			groups.cleanup()
			groups.clear()
		}
	})

	// subscribe immediately if already authenticated
	// (module may be imported after auth when navigating to a groups page)
	if (getAccessToken()) {
		groups.init()
	}
}
