import { derived, get, writable } from 'svelte/store'

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

export const accessToken = writable<string | null>(getAccessToken())
export const isLoggedIn = derived(accessToken, (token) => Boolean(token))

if (typeof window !== 'undefined') {
	onAccessTokenChanged((token) => {
		accessToken.set(token)
		if (token) eventStreamClient.connect(token)
		else eventStreamClient.disconnect()
	})
}

export const currentUser = writable<User | null>(null)
export const recentThreads = writable<Thread[]>([])
export const activeThread = writable<Thread | null>(null)

export type PendingChatStart = { threadId: string; content: string }
export const pendingChatStart = writable<PendingChatStart | null>(null)

export const isLoadingUser = writable(false)
export const isLoadingThreads = writable(false)

export const userDisplay = derived(
	[currentUser, accessToken],
	([user, token]): { name: string; email: string; avatar: string | null } => {
		const tokenEmail = token ? getJwtEmail(token) : null
		const email = user?.email ?? tokenEmail ?? ''
		const nameFromEmail = email ? email.split('@')[0] : 'user'
		const name = user?.display_name ?? nameFromEmail
		const avatar = user?.avatar_url ?? null
		return { name, email, avatar }
	}
)

export function setSessionToken(token: string): void {
	setAccessToken(token)
	accessToken.set(token)
	eventStreamClient.connect(token)
}

export function clearSession(): void {
	eventStreamClient.disconnect()
	clearAccessToken()
	accessToken.set(null)
	currentUser.set(null)
	recentThreads.set([])
	activeThread.set(null)
}

export function setActiveThread(thread: Thread | null): void {
	activeThread.set(thread)
}

export function setPendingChatStart(value: PendingChatStart | null): void {
	pendingChatStart.set(value)
}

export function consumePendingChatStart(threadId: string): string | null {
	const value = get(pendingChatStart)
	if (!value || value.threadId !== threadId) return null
	pendingChatStart.set(null)
	return value.content
}

export async function refreshUser(): Promise<void> {
	const token = getAccessToken()
	if (!token) {
		currentUser.set(null)
		return
	}

	const userId = getJwtUserId(token)
	if (!userId) {
		currentUser.set(null)
		return
	}

	isLoadingUser.set(true)
	try {
		const { data } = await v1Client().GET('/users/{user_id}', {
			params: { path: { user_id: userId } },
		})
		currentUser.set(data ?? null)
	} finally {
		isLoadingUser.set(false)
	}
}

export async function refreshThreads(options?: { limit?: number }): Promise<void> {
	const token = getAccessToken()
	if (!token) {
		recentThreads.set([])
		return
	}

	const userId = getJwtUserId(token)

	isLoadingThreads.set(true)
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

		recentThreads.set(threads)
	} finally {
		isLoadingThreads.set(false)
	}
}

export async function refreshSession(): Promise<void> {
	await Promise.all([refreshUser(), refreshThreads()])
}
