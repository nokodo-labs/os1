import { browser } from '$app/environment'

import { apiClient } from '$lib/api/client'
import { eventStreamClient } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getJwtEmail, getJwtUserId } from '$lib/auth/jwt'
import {
	clearAccessToken,
	getAccessToken,
	onAccessTokenChanged,
	setAccessToken,
} from '$lib/auth/session'

export type User = components['schemas']['User']
export type Thread = components['schemas']['Thread']
export type PendingChatStart = { threadId: string; content: string }

class SessionStore {
	accessToken = $state<string | null>(getAccessToken())
	currentUser = $state<User | null>(null)
	recentThreads = $state<Thread[]>([])
	activeThread = $state<Thread | null>(null)
	pendingChatStart = $state<PendingChatStart | null>(null)
	isLoadingUser = $state(false)
	isLoadingThreads = $state(false)

	readonly isLoggedIn = $derived(Boolean(this.accessToken))
	readonly userDisplay = $derived.by(() => {
		const user = this.currentUser
		const token = this.accessToken
		const tokenEmail = token ? getJwtEmail(token) : null
		const email = user?.email ?? tokenEmail ?? ''
		const nameFromEmail = email ? email.split('@')[0] : 'user'
		const name = user?.display_name ?? nameFromEmail
		const avatar = user?.avatar_url ?? null
		return { name, email, avatar }
	})

	setToken = (token: string) => {
		setAccessToken(token)
		this.accessToken = token
		eventStreamClient.connect(token)
	}

	clear = () => {
		eventStreamClient.disconnect()
		clearAccessToken()
		this.accessToken = null
		this.currentUser = null
		this.recentThreads = []
		this.activeThread = null
		this.pendingChatStart = null
	}

	consumePendingChatStart = (threadId: string): string | null => {
		const value = this.pendingChatStart
		if (!value || value.threadId !== threadId) return null
		this.pendingChatStart = null
		return value.content
	}

	removeRecentThread = (threadId: string) => {
		if (!threadId) return
		this.recentThreads = this.recentThreads.filter((t) => t.id !== threadId)
	}

	updateRecentThread = (threadId: string, update: (thread: Thread) => Thread) => {
		if (!threadId) return
		const threads = this.recentThreads
		const idx = threads.findIndex((t) => t.id === threadId)
		if (idx === -1) return
		const updated = update(threads[idx])
		this.recentThreads = [updated, ...threads.slice(0, idx), ...threads.slice(idx + 1)]
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
			const { data } = await apiClient().GET('/v1/users/{user_id}', {
				params: { path: { user_id: userId } },
			})
			this.currentUser = data ?? null
		} finally {
			this.isLoadingUser = false
		}
	}

	refreshThreads = async (options?: { limit?: number }): Promise<void> => {
		const token = getAccessToken()
		if (!token) {
			this.recentThreads = []
			return
		}

		const userId = getJwtUserId(token)

		this.isLoadingThreads = true
		try {
			const { data } = await apiClient().GET('/v1/threads', {
				params: {
					query: {
						owner_id: userId,
						limit: options?.limit ?? 20,
						skip: 0,
					},
				},
			})

			const threads = (data ?? []).slice().sort((a, b) => {
				return b.last_activity_at.localeCompare(a.last_activity_at)
			})

			this.recentThreads = threads
		} finally {
			this.isLoadingThreads = false
		}
	}

	refresh = async (): Promise<void> => {
		await Promise.all([this.refreshUser(), this.refreshThreads()])
	}
}

export const session = new SessionStore()

if (browser) {
	onAccessTokenChanged((token) => {
		session.accessToken = token
		if (token) eventStreamClient.connect(token)
		else eventStreamClient.disconnect()
	})
}
