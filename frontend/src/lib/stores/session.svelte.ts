import { browser } from '$app/environment'

import { eventStreamClient } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { v1Client } from '$lib/api/v1/client'
import { getJwtEmail, getJwtUserId } from '$lib/auth/jwt'
import {
	clearAccessToken,
	getAccessToken,
	onAccessTokenChanged,
	setAccessToken,
} from '$lib/auth/session'

export type User = components['schemas']['User']
export type Thread = components['schemas']['Thread']

export let accessToken = $state<string | null>(getAccessToken())
export const isLoggedIn = $derived(Boolean(accessToken))

if (browser) {
	onAccessTokenChanged((token) => {
		accessToken = token
		if (token) eventStreamClient.connect(token)
		else eventStreamClient.disconnect()
	})
}

export let currentUser = $state<User | null>(null)
export let recentThreads = $state<Thread[]>([])
export let activeThread = $state<Thread | null>(null)

export type PendingChatStart = { threadId: string; content: string }
export let pendingChatStart = $state<PendingChatStart | null>(null)

export let isLoadingUser = $state(false)
export let isLoadingThreads = $state(false)

export const userDisplay = $derived.by(
	(): { name: string; email: string; avatar: string | null } => {
		const user = currentUser
		const token = accessToken
		const tokenEmail = token ? getJwtEmail(token) : null
		const email = user?.email ?? tokenEmail ?? ''
		const nameFromEmail = email ? email.split('@')[0] : 'user'
		const name = user?.display_name ?? nameFromEmail
		const avatar = user?.avatar_url ?? null
		return { name, email, avatar }
	}
)

export function setAccessTokenValue(token: string | null): void {
	accessToken = token
}

export function setCurrentUser(user: User | null): void {
	currentUser = user
}

export function updateCurrentUser(updater: (user: User | null) => User | null): void {
	currentUser = updater(currentUser)
}

export function setRecentThreads(threads: Thread[]): void {
	recentThreads = threads
}

export function updateRecentThreads(updater: (threads: Thread[]) => Thread[]): void {
	recentThreads = updater(recentThreads)
}

export function setSessionToken(token: string): void {
	setAccessToken(token)
	accessToken = token
	eventStreamClient.connect(token)
}

export function clearSession(): void {
	eventStreamClient.disconnect()
	clearAccessToken()
	accessToken = null
	currentUser = null
	recentThreads = []
	activeThread = null
}

export function setActiveThread(thread: Thread | null): void {
	activeThread = thread
}

export function setPendingChatStart(value: PendingChatStart | null): void {
	pendingChatStart = value
}

export function consumePendingChatStart(threadId: string): string | null {
	const value = pendingChatStart
	if (!value || value.threadId !== threadId) return null
	pendingChatStart = null
	return value.content
}

export async function refreshUser(): Promise<void> {
	const token = getAccessToken()
	if (!token) {
		currentUser = null
		return
	}

	const userId = getJwtUserId(token)
	if (!userId) {
		currentUser = null
		return
	}

	isLoadingUser = true
	try {
		const { data } = await v1Client().GET('/users/{user_id}', {
			params: { path: { user_id: userId } },
		})
		currentUser = data ?? null
	} finally {
		isLoadingUser = false
	}
}

export async function refreshThreads(options?: { limit?: number }): Promise<void> {
	const token = getAccessToken()
	if (!token) {
		recentThreads = []
		return
	}

	const userId = getJwtUserId(token)

	isLoadingThreads = true
	try {
		const { data } = await v1Client().GET('/threads', {
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

		recentThreads = threads
	} finally {
		isLoadingThreads = false
	}
}

export async function refreshSession(): Promise<void> {
	await Promise.all([refreshUser(), refreshThreads()])
}
