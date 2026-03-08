import { browser } from '$app/environment'
import { apiClient } from '$lib/api/client'
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { session } from '$lib/stores/session.svelte'

const ROLE_EVENT_TYPES = ['role.updated', 'role.deleted']

class PermissionsStore {
	list = $state<string[] | null>(null)
	isLoading = $state(false)
	error = $state<string | null>(null)

	readonly isSuperuser = $derived(Boolean(session.currentUser?.is_superuser))

	#unsubscribe: (() => void) | null = null

	hasPermission = (permission: string): boolean => {
		if (this.isSuperuser) return true
		const list = this.list
		if (!list) return false
		return list.includes(permission)
	}

	refresh = async (): Promise<void> => {
		const token = getAccessToken()
		const userId = token ? getJwtUserId(token) : null
		if (!token || !userId) {
			this.list = null
			this.error = null
			this.isLoading = false
			return
		}

		this.isLoading = true
		this.error = null
		try {
			const { data, error } = await apiClient().GET('/v1/users/{user_id}/permissions', {
				params: { path: { user_id: userId } },
			})
			if (error || !data) {
				this.error = 'failed to load permissions'
				this.list = null
				return
			}
			this.list = data.permissions ?? []
		} finally {
			this.isLoading = false
		}
	}

	clear = (): void => {
		this.list = null
		this.error = null
		this.isLoading = false
	}

	#handleEvent = (message: StreamMessage): void => {
		if (!ROLE_EVENT_TYPES.includes(message.type)) return
		// role changed - refresh permissions (and user data for role changes)
		void this.refresh()
		void session.refreshUser()
	}

	subscribe = (): void => {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleEvent)
		}
	}

	unsubscribe = (): void => {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}
}

export const permissions = new PermissionsStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			permissions.subscribe()
		} else {
			permissions.unsubscribe()
			permissions.clear()
		}
	})
}
