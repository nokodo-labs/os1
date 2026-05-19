/**
 * resource access store.
 *
 * this store owns all frontend permission lookups for shareable resources.
 * the cache is intentionally broad because access checks happen in many
 * components, but it is invalidated aggressively when the websocket reports
 * sharing, group, or role changes.
 *
 * cache layers:
 * - current-user levels: quick gates for edit/delete/share UI
 * - subject levels: batched lookups used by share/search surfaces
 * - rule lists: admin-only sharing editor data
 * - in-flight maps: dedupe concurrent requests for the same resource
 */

import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import type { StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { STORE_EVENT_TYPES, storeEventData, subscribeToStoreEvents } from '$lib/stores/storeEvents'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'
import { session } from './session.svelte'

export type AccessLevel = components['schemas']['AccessLevel']
export type AccessLevelResolution = components['schemas']['AccessLevelResolution']
export type AccessRuleCreate = components['schemas']['AccessRuleCreate']
export type AccessRuleResponse = components['schemas']['AccessRuleResponse']
export type AccessControlledResourceType =
	| 'thread'
	| 'note'
	| 'reminder_list'
	| 'calendar'
	| 'file'
	| 'project'
	| 'group'
	| 'agent'
	| 'memory'

const LEVEL_RANK: Record<AccessLevel, number> = {
	reader: 0,
	editor: 1,
	admin: 2,
}

const RESOURCE_ACCESS_EVENT_TYPES = [
	...STORE_EVENT_TYPES.resourceAccessGlobal,
	...STORE_EVENT_TYPES.resourceAccessResource,
] as const
const RESOURCE_ACCESS_GLOBAL_EVENTS = new Set<string>(STORE_EVENT_TYPES.resourceAccessGlobal)

function resourceKey(resourceType: AccessControlledResourceType, resourceId: string): string {
	return `${resourceType}:${resourceId}`
}

function subjectKey(
	resourceType: AccessControlledResourceType,
	resourceId: string,
	userId: string
): string {
	return `${resourceKey(resourceType, resourceId)}:${userId}`
}

function parseResourceKey(key: string): [AccessControlledResourceType, string] | null {
	const [resourceType, ...rest] = key.split(':')
	const resourceId = rest.join(':')
	if (!isAccessResourceType(resourceType) || !resourceId) return null
	return [resourceType, resourceId]
}

function parseSubjectKey(key: string): [AccessControlledResourceType, string, string] | null {
	const [resourceType, resourceId, userId] = key.split(':')
	if (!isAccessResourceType(resourceType) || !resourceId || !userId) return null
	return [resourceType, resourceId, userId]
}

function isAccessResourceType(value: unknown): value is AccessControlledResourceType {
	return (
		value === 'thread' ||
		value === 'note' ||
		value === 'reminder_list' ||
		value === 'calendar' ||
		value === 'file' ||
		value === 'project' ||
		value === 'group' ||
		value === 'agent' ||
		value === 'memory'
	)
}

export function isAccessLevel(value: unknown): value is AccessLevel {
	return value === 'reader' || value === 'editor' || value === 'admin'
}

export function accessLevelSatisfies(
	level: AccessLevel | null | undefined,
	required: AccessLevel
): boolean {
	if (!level) return false
	return LEVEL_RANK[level] >= LEVEL_RANK[required]
}

export function canEditAccessLevel(level: AccessLevel | null | undefined): boolean {
	return accessLevelSatisfies(level, 'editor')
}

export function canAdminAccessLevel(level: AccessLevel | null | undefined): boolean {
	return accessLevelSatisfies(level, 'admin')
}

export function canShareAccessLevel(level: AccessLevel | null | undefined): boolean {
	return canAdminAccessLevel(level)
}

export function canDeleteAccessLevel(level: AccessLevel | null | undefined): boolean {
	return canAdminAccessLevel(level)
}

export function readAccessLevel(value: unknown): AccessLevel | null {
	return isAccessLevel(value) ? value : null
}

class ResourceAccessStore {
	/** current-user effective level by resource key. null means fetched and denied. */
	readonly #levels = new SvelteMap<string, AccessLevel | null>()

	/** arbitrary user effective levels, keyed by resource and user. */
	readonly #subjectLevels = new SvelteMap<string, AccessLevel | null>()

	/** admin-visible sharing entries by resource key. */
	readonly #rules = new SvelteMap<string, AccessRuleResponse[]>()

	readonly #levelInFlight = new Map<string, Promise<AccessLevel | null>>()
	readonly #subjectInFlight = new Map<string, Promise<AccessLevelResolution[]>>()
	readonly #rulesInFlight = new Map<string, Promise<AccessRuleResponse[]>>()
	readonly #freshLevels = new SvelteSet<string>()
	readonly #freshSubjectLevels = new SvelteSet<string>()
	readonly #freshRules = new SvelteSet<string>()
	#version = $state(0)
	#unsubscribeStream: (() => void) | null = null

	get version(): number {
		return this.#version
	}

	level(
		resourceType: AccessControlledResourceType,
		resourceId: string,
		ownerId?: string | null
	): AccessLevel | null {
		if (ownerId && session.currentUserId === ownerId) return 'admin'
		return this.#levels.get(resourceKey(resourceType, resourceId)) ?? null
	}

	canEdit(
		resourceType: AccessControlledResourceType,
		resourceId: string,
		ownerId?: string | null
	): boolean {
		return canEditAccessLevel(this.level(resourceType, resourceId, ownerId))
	}

	canAdmin(
		resourceType: AccessControlledResourceType,
		resourceId: string,
		ownerId?: string | null
	): boolean {
		return canAdminAccessLevel(this.level(resourceType, resourceId, ownerId))
	}

	set(
		resourceType: AccessControlledResourceType,
		resourceId: string,
		level: AccessLevel | null
	): void {
		const key = resourceKey(resourceType, resourceId)
		this.#levels.set(key, level)
		this.#freshLevels.add(key)
	}

	/**
	 * fetch the current user's effective level once, then reuse it until a
	 * websocket change invalidates the resource. owners skip the network.
	 */
	async ensure(
		resourceType: AccessControlledResourceType,
		resourceId: string,
		ownerId?: string | null
	): Promise<AccessLevel | null> {
		const key = resourceKey(resourceType, resourceId)
		if (ownerId && session.currentUserId === ownerId) {
			this.#levels.set(key, 'admin')
			this.#freshLevels.add(key)
			return 'admin'
		}
		if (this.#levels.has(key) && this.#freshLevels.has(key)) {
			return this.#levels.get(key) ?? null
		}

		const existing = this.#levelInFlight.get(key)
		if (existing) return existing

		const version = this.#version
		const inFlight = this.#fetchCurrentUserLevel(resourceType, resourceId)
		this.#levelInFlight.set(key, inFlight)
		try {
			const level = await inFlight
			if (version !== this.#version)
				return await this.ensure(resourceType, resourceId, ownerId)
			this.#levels.set(key, level)
			this.#freshLevels.add(key)
			return level
		} finally {
			this.#levelInFlight.delete(key)
		}
	}

	/**
	 * resolve many users for one resource. cached answers are returned first;
	 * missing users are sent as one batch to the resource-specific endpoint.
	 */
	async resolveLevels(
		resourceType: AccessControlledResourceType,
		resourceId: string,
		subjectUserIds: string[]
	): Promise<AccessLevelResolution[]> {
		const uniqueIds = [...new Set(subjectUserIds.filter(Boolean))]
		const missingIds = uniqueIds.filter((userId) => {
			const key = subjectKey(resourceType, resourceId, userId)
			return !this.#subjectLevels.has(key) || !this.#freshSubjectLevels.has(key)
		})

		if (missingIds.length > 0) {
			const batchKey = `${resourceKey(resourceType, resourceId)}:${missingIds.toSorted().join(',')}`
			let inFlight = this.#subjectInFlight.get(batchKey)
			const version = this.#version
			if (!inFlight) {
				inFlight = resolveResourceAccessLevels(resourceType, resourceId, missingIds)
				this.#subjectInFlight.set(batchKey, inFlight)
			}
			try {
				const fetched = await inFlight
				if (version !== this.#version) {
					return await this.resolveLevels(resourceType, resourceId, subjectUserIds)
				}
				const fetchedIds = new SvelteSet<string>()
				for (const result of fetched) {
					fetchedIds.add(result.user_id)
					const key = subjectKey(resourceType, resourceId, result.user_id)
					this.#subjectLevels.set(key, result.level ?? null)
					this.#freshSubjectLevels.add(key)
				}
				for (const userId of missingIds) {
					if (!fetchedIds.has(userId)) {
						const key = subjectKey(resourceType, resourceId, userId)
						this.#subjectLevels.set(key, null)
						this.#freshSubjectLevels.add(key)
					}
				}
			} finally {
				this.#subjectInFlight.delete(batchKey)
			}
		}

		return uniqueIds.map((userId) => ({
			resource_type: resourceType,
			resource_id: resourceId,
			user_id: userId,
			level: this.#subjectLevels.get(subjectKey(resourceType, resourceId, userId)) ?? null,
		}))
	}

	/** admin-only rule cache for the share modal and future management surfaces. */
	async ensureRules(
		resourceType: AccessControlledResourceType,
		resourceId: string
	): Promise<AccessRuleResponse[]> {
		const key = resourceKey(resourceType, resourceId)
		const cached = this.#rules.get(key)
		if (cached && this.#freshRules.has(key)) return cached

		const existing = this.#rulesInFlight.get(key)
		if (existing) return existing

		const version = this.#version
		const inFlight = getResourceAccessRules(resourceType, resourceId)
		this.#rulesInFlight.set(key, inFlight)
		try {
			const rules = await inFlight
			if (version !== this.#version) return await this.ensureRules(resourceType, resourceId)
			this.#rules.set(key, rules)
			this.#freshRules.add(key)
			return rules
		} finally {
			this.#rulesInFlight.delete(key)
		}
	}

	/** save the complete share list and drop effective-level caches for this resource. */
	async replaceRules(
		resourceType: AccessControlledResourceType,
		resourceId: string,
		body: AccessRuleCreate[]
	): Promise<AccessRuleResponse[] | null> {
		const saved = await putResourceAccessRules(resourceType, resourceId, body)
		if (!saved) return null
		this.invalidate(resourceType, resourceId)
		const key = resourceKey(resourceType, resourceId)
		this.#rules.set(key, saved)
		this.#freshRules.add(key)
		return saved
	}

	invalidate(): void
	invalidate(resourceType: AccessControlledResourceType, resourceId: string): void
	invalidate(resourceType?: AccessControlledResourceType, resourceId?: string): void {
		if (!resourceType || !resourceId) {
			this.invalidateAll()
			return
		}
		this.#version += 1
		const key = resourceKey(resourceType, resourceId)
		this.#levels.delete(key)
		this.#rules.delete(key)
		this.#freshLevels.delete(key)
		this.#freshRules.delete(key)
		this.#levelInFlight.delete(key)
		this.#rulesInFlight.delete(key)

		const subjectPrefix = `${key}:`
		for (const cachedKey of [...this.#subjectLevels.keys()]) {
			if (cachedKey.startsWith(subjectPrefix)) this.#subjectLevels.delete(cachedKey)
		}
		for (const cachedKey of [...this.#freshSubjectLevels.keys()]) {
			if (cachedKey.startsWith(subjectPrefix)) this.#freshSubjectLevels.delete(cachedKey)
		}
		for (const cachedKey of [...this.#subjectInFlight.keys()]) {
			if (cachedKey.startsWith(subjectPrefix)) this.#subjectInFlight.delete(cachedKey)
		}
	}

	async refresh(): Promise<void> {
		await this.refreshStale()
	}

	invalidateAll(): void {
		this.#version += 1
		this.#freshLevels.clear()
		this.#freshSubjectLevels.clear()
		this.#freshRules.clear()
		this.#levelInFlight.clear()
		this.#subjectInFlight.clear()
		this.#rulesInFlight.clear()
	}

	clear(): void {
		this.#version += 1
		this.#levels.clear()
		this.#subjectLevels.clear()
		this.#rules.clear()
		this.#freshLevels.clear()
		this.#freshSubjectLevels.clear()
		this.#freshRules.clear()
		this.#levelInFlight.clear()
		this.#subjectInFlight.clear()
		this.#rulesInFlight.clear()
	}

	async refreshStale(): Promise<void> {
		const tasks: Promise<unknown>[] = []
		for (const key of this.#levels.keys()) {
			if (this.#freshLevels.has(key)) continue
			const parsed = parseResourceKey(key)
			if (parsed) tasks.push(this.ensure(parsed[0], parsed[1]))
		}
		for (const key of this.#rules.keys()) {
			if (this.#freshRules.has(key)) continue
			const parsed = parseResourceKey(key)
			if (parsed) tasks.push(this.ensureRules(parsed[0], parsed[1]))
		}

		const subjectGroups = new SvelteMap<
			string,
			{
				resourceType: AccessControlledResourceType
				resourceId: string
				userIds: string[]
			}
		>()
		for (const key of this.#subjectLevels.keys()) {
			if (this.#freshSubjectLevels.has(key)) continue
			const parsed = parseSubjectKey(key)
			if (!parsed) continue
			const groupKey = resourceKey(parsed[0], parsed[1])
			const group = subjectGroups.get(groupKey) ?? {
				resourceType: parsed[0],
				resourceId: parsed[1],
				userIds: [],
			}
			if (!group.userIds.includes(parsed[2])) group.userIds.push(parsed[2])
			subjectGroups.set(groupKey, group)
		}
		for (const group of subjectGroups.values()) {
			tasks.push(this.resolveLevels(group.resourceType, group.resourceId, group.userIds))
		}
		await Promise.allSettled(tasks)
	}

	init(): void {
		if (!this.#unsubscribeStream) {
			this.#unsubscribeStream = subscribeToStoreEvents(
				RESOURCE_ACCESS_EVENT_TYPES,
				this.#handleStreamEvent
			)
		}
	}

	cleanup(): void {
		this.#unsubscribeStream?.()
		this.#unsubscribeStream = null
		this.clear()
	}

	async #fetchCurrentUserLevel(
		resourceType: AccessControlledResourceType,
		resourceId: string
	): Promise<AccessLevel | null> {
		const userId = session.currentUserId
		if (!userId) return null
		try {
			const results = await this.resolveLevels(resourceType, resourceId, [userId])
			return results.find((result) => result.user_id === userId)?.level ?? null
		} catch {
			return null
		}
	}

	#handleStreamEvent = (message: StreamMessage): void => {
		if (RESOURCE_ACCESS_GLOBAL_EVENTS.has(message.type)) {
			this.invalidateAll()
			return
		}

		const data = storeEventData(message)
		const resourceType = data?.resource_type
		const resourceId = data?.resource_id
		if (!isAccessResourceType(resourceType) || typeof resourceId !== 'string') {
			this.invalidateAll()
			return
		}
		this.invalidate(resourceType, resourceId)
	}
}

export async function resolveResourceAccessLevels(
	resourceType: AccessControlledResourceType,
	resourceId: string,
	subjectUserIds: string[]
): Promise<AccessLevelResolution[]> {
	const body = { subject_user_ids: subjectUserIds }
	const { data, error } = await postResourceAccessLevelResolve(resourceType, resourceId, body)
	if (error || !data) return []
	return data
}

async function getResourceAccessRules(
	resourceType: AccessControlledResourceType,
	resourceId: string
): Promise<AccessRuleResponse[]> {
	const { data, error } = await getResourceAccessRulesResponse(resourceType, resourceId)
	if (error || !data) return []
	return data
}

async function putResourceAccessRules(
	resourceType: AccessControlledResourceType,
	resourceId: string,
	body: AccessRuleCreate[]
): Promise<AccessRuleResponse[] | null> {
	const { data, error } = await putResourceAccessRulesResponse(resourceType, resourceId, body)
	if (error || !data) return null
	return data
}

function postResourceAccessLevelResolve(
	resourceType: AccessControlledResourceType,
	resourceId: string,
	body: { subject_user_ids: string[] }
) {
	switch (resourceType) {
		case 'thread':
			return api.POST('/v1/threads/{thread_id}/access/resolve', {
				params: { path: { thread_id: resourceId } },
				body,
			})
		case 'note':
			return api.POST('/v1/notes/{note_id}/access/resolve', {
				params: { path: { note_id: resourceId } },
				body,
			})
		case 'reminder_list':
			return api.POST('/v1/reminder-lists/{list_id}/access/resolve', {
				params: { path: { list_id: resourceId } },
				body,
			})
		case 'calendar':
			return api.POST('/v1/calendars/{calendar_id}/access/resolve', {
				params: { path: { calendar_id: resourceId } },
				body,
			})
		case 'file':
			return api.POST('/v1/files/{file_id}/access/resolve', {
				params: { path: { file_id: resourceId } },
				body,
			})
		case 'project':
			return api.POST('/v1/projects/{project_id}/access/resolve', {
				params: { path: { project_id: resourceId } },
				body,
			})
		case 'group':
			return api.POST('/v1/groups/{group_id}/access/resolve', {
				params: { path: { group_id: resourceId } },
				body,
			})
		case 'agent':
			return api.POST('/v1/agents/{agent_id}/access/resolve', {
				params: { path: { agent_id: resourceId } },
				body,
			})
		case 'memory':
			return api.POST('/v1/memories/{memory_id}/access/resolve', {
				params: { path: { memory_id: resourceId } },
				body,
			})
	}
}

function getResourceAccessRulesResponse(
	resourceType: AccessControlledResourceType,
	resourceId: string
) {
	switch (resourceType) {
		case 'thread':
			return api.GET('/v1/threads/{thread_id}/access/rules', {
				params: { path: { thread_id: resourceId } },
			})
		case 'note':
			return api.GET('/v1/notes/{note_id}/access/rules', {
				params: { path: { note_id: resourceId } },
			})
		case 'reminder_list':
			return api.GET('/v1/reminder-lists/{list_id}/access/rules', {
				params: { path: { list_id: resourceId } },
			})
		case 'calendar':
			return api.GET('/v1/calendars/{calendar_id}/access/rules', {
				params: { path: { calendar_id: resourceId } },
			})
		case 'file':
			return api.GET('/v1/files/{file_id}/access/rules', {
				params: { path: { file_id: resourceId } },
			})
		case 'project':
			return api.GET('/v1/projects/{project_id}/access/rules', {
				params: { path: { project_id: resourceId } },
			})
		case 'group':
			return api.GET('/v1/groups/{group_id}/access/rules', {
				params: { path: { group_id: resourceId } },
			})
		case 'agent':
			return api.GET('/v1/agents/{agent_id}/access/rules', {
				params: { path: { agent_id: resourceId } },
			})
		case 'memory':
			return api.GET('/v1/memories/{memory_id}/access/rules', {
				params: { path: { memory_id: resourceId } },
			})
	}
}

function putResourceAccessRulesResponse(
	resourceType: AccessControlledResourceType,
	resourceId: string,
	body: AccessRuleCreate[]
) {
	switch (resourceType) {
		case 'thread':
			return api.PUT('/v1/threads/{thread_id}/access/rules', {
				params: { path: { thread_id: resourceId } },
				body,
			})
		case 'note':
			return api.PUT('/v1/notes/{note_id}/access/rules', {
				params: { path: { note_id: resourceId } },
				body,
			})
		case 'reminder_list':
			return api.PUT('/v1/reminder-lists/{list_id}/access/rules', {
				params: { path: { list_id: resourceId } },
				body,
			})
		case 'calendar':
			return api.PUT('/v1/calendars/{calendar_id}/access/rules', {
				params: { path: { calendar_id: resourceId } },
				body,
			})
		case 'file':
			return api.PUT('/v1/files/{file_id}/access/rules', {
				params: { path: { file_id: resourceId } },
				body,
			})
		case 'project':
			return api.PUT('/v1/projects/{project_id}/access/rules', {
				params: { path: { project_id: resourceId } },
				body,
			})
		case 'group':
			return api.PUT('/v1/groups/{group_id}/access/rules', {
				params: { path: { group_id: resourceId } },
				body,
			})
		case 'agent':
			return api.PUT('/v1/agents/{agent_id}/access/rules', {
				params: { path: { agent_id: resourceId } },
				body,
			})
		case 'memory':
			return api.PUT('/v1/memories/{memory_id}/access/rules', {
				params: { path: { memory_id: resourceId } },
				body,
			})
	}
}

export const resourceAccess = new ResourceAccessStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			resourceAccess.init()
		} else {
			resourceAccess.cleanup()
		}
	})

	if (getAccessToken()) {
		resourceAccess.init()
	}
}
