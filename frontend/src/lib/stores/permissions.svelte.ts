import { browser } from '$app/environment'
import { api } from '$lib/api/client'
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

	load = async (): Promise<void> => {
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
			const { data, error } = await api.GET('/v1/users/{user_id}/permissions', {
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

	invalidate = (): void => {
		this.list = null
	}

	#handleEvent = (message: StreamMessage): void => {
		if (!ROLE_EVENT_TYPES.includes(message.type)) return
		// role changed - refresh permissions (and user data for role changes)
		void this.load()
		void session.refreshUser()
	}

	init = (): void => {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleEvent)
		}
	}

	cleanup = (): void => {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}
}

export const permissions = new PermissionsStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			permissions.init()
		} else {
			permissions.cleanup()
			permissions.clear()
		}
	})
}
