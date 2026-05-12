import { browser } from '$app/environment'

import { api, BackendUnreachableError } from '$lib/api/client'
import { eventStreamClient } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getJwtEmail, getJwtUserId } from '$lib/auth/jwt'
import {
	clearAccessToken,
	getAccessToken,
	onAccessTokenChanged,
	setAccessToken,
} from '$lib/auth/session.svelte'
import { type UserSummary, userDisplayName } from '$lib/utils/resourceAuthors'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'

export type User = components['schemas']['User']

class SessionStore {
	accessToken = $state<string | null>(getAccessToken())
	currentUser = $state<User | null>(null)
	isLoadingUser = $state(false)
	readonly #usersById = new SvelteMap<string, UserSummary>()
	readonly #unavailableUserIds = new SvelteSet<string>()
	#usersInFlight: Promise<void> | null = null

	readonly isLoggedIn = $derived(Boolean(this.accessToken))
	readonly currentUserId = $derived.by(() => {
		if (this.currentUser?.id) return this.currentUser.id
		return this.accessToken ? getJwtUserId(this.accessToken) : null
	})
	readonly userDisplay = $derived.by(() => {
		const user = this.currentUser
		const token = this.accessToken
		const tokenEmail = token ? getJwtEmail(token) : null
		const email = user?.email ?? tokenEmail ?? ''
		const name =
			userDisplayName({
				id: this.currentUserId,
				display_name: user?.display_name,
				username: user?.username,
			}) ?? 'user'
		const avatar = user?.avatar_url ?? null
		return { name, email, avatar }
	})

	setToken = (token: string) => {
		setAccessToken(token)
		this.accessToken = token
		eventStreamClient.connect()
	}

	clear = () => {
		eventStreamClient.disconnect()
		clearAccessToken()
		this.accessToken = null
		this.currentUser = null
		this.clearUserCache()
	}

	refreshUser = async (): Promise<void> => {
		const token = getAccessToken()
		if (!token) {
			this.currentUser = null
			return
		}

		const userId = getJwtUserId(token)
		if (!userId) {
			this.currentUser = null
			return
		}

		this.isLoadingUser = true
		try {
			const { data } = await api.GET('/v1/users/{user_id}', {
				params: { path: { user_id: userId } },
			})
			this.currentUser = data ?? null
		} catch (err) {
			if (err instanceof BackendUnreachableError) throw err
			// other unexpected errors - clear user, don't crash
			this.currentUser = null
		} finally {
			this.isLoadingUser = false
		}
	}

	refresh = async (): Promise<void> => {
		await this.refreshUser()
		await this.refreshCachedUsers()
	}

	async refreshCachedUsers(): Promise<void> {
		if (!this.accessToken || this.#usersById.size === 0) return
		const userIds = [...this.#usersById.keys()]
		const { data, error } = await api.POST('/v1/users/bulk', {
			body: { user_ids: userIds.slice(0, 100) },
		})
		if (error || !data) return
		const returnedIds: string[] = []
		for (const user of data) {
			this.#usersById.set(user.id, user)
			returnedIds.push(user.id)
		}
		for (const userId of userIds) {
			if (!returnedIds.includes(userId)) this.#unavailableUserIds.add(userId)
		}
	}

	getUserSummary(userId: string | null | undefined): UserSummary | null {
		if (!userId) return null
		if (this.currentUser?.id === userId) return this.currentUser
		return this.#usersById.get(userId) ?? null
	}

	userLabel(userId: string | null | undefined): string | null {
		if (!userId) return null
		return userDisplayName(this.getUserSummary(userId) ?? { id: userId })
	}

	authorLabel(userId: string | null | undefined): string | null {
		if (!userId) return null
		if (userId === this.currentUserId) return this.userLabel(userId) ?? 'you'
		return this.userLabel(userId)
	}

	async ensureUsers(userIds: Array<string | null | undefined>): Promise<void> {
		if (!this.accessToken) return
		const missing = uniqueUserIds(userIds).filter(
			(userId) =>
				this.currentUser?.id !== userId &&
				!this.#usersById.has(userId) &&
				!this.#unavailableUserIds.has(userId)
		)
		if (missing.length === 0) return
		if (this.#usersInFlight) await this.#usersInFlight

		const remaining = missing.filter(
			(userId) =>
				this.currentUser?.id !== userId &&
				!this.#usersById.has(userId) &&
				!this.#unavailableUserIds.has(userId)
		)
		if (remaining.length === 0) return

		this.#usersInFlight = (async () => {
			const { data, error } = await api.POST('/v1/users/bulk', {
				body: { user_ids: remaining.slice(0, 100) },
			})
			if (error || !data) return
			const returnedIds: string[] = []
			for (const user of data) {
				this.#usersById.set(user.id, user)
				returnedIds.push(user.id)
			}
			for (const userId of remaining) {
				if (!returnedIds.includes(userId)) this.#unavailableUserIds.add(userId)
			}
		})()

		try {
			await this.#usersInFlight
		} finally {
			this.#usersInFlight = null
		}
	}

	clearUserCache(): void {
		this.#usersById.clear()
		this.#unavailableUserIds.clear()
		this.#usersInFlight = null
	}
}

function uniqueUserIds(userIds: Array<string | null | undefined>): string[] {
	const result: string[] = []
	for (const userId of userIds) {
		if (!userId || result.includes(userId)) continue
		result.push(userId)
	}
	return result
}

export const session = new SessionStore()

if (browser) {
	onAccessTokenChanged((token) => {
		session.accessToken = token
		session.clearUserCache()
	})
}
