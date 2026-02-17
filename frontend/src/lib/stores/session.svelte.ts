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
} from '$lib/auth/session.svelte'

export type User = components['schemas']['User']

class SessionStore {
	accessToken = $state<string | null>(getAccessToken())
	currentUser = $state<User | null>(null)
	isLoadingUser = $state(false)

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
		eventStreamClient.connect()
	}

	clear = () => {
		eventStreamClient.disconnect()
		clearAccessToken()
		this.accessToken = null
		this.currentUser = null
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

	refresh = async (): Promise<void> => {
		await this.refreshUser()
	}
}

export const session = new SessionStore()

if (browser) {
	onAccessTokenChanged((token) => {
		session.accessToken = token
	})
}
