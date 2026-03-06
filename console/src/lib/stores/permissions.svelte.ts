import { api } from '$lib/api'
import { auth } from '$lib/auth.svelte'

class PermissionsStore {
	list = $state<string[] | null>(null)
	isLoading = $state(false)
	error = $state<string | null>(null)

	readonly isSuperuser = $derived(Boolean(auth.user?.is_superuser))

	hasPermission = (permission: string): boolean => {
		if (this.isSuperuser) return true
		const list = this.list
		if (!list) return false
		return list.includes(permission)
	}

	refresh = async (): Promise<void> => {
		const userId = auth.user?.id ?? null
		if (!userId) {
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
}

export const permissions = new PermissionsStore()
