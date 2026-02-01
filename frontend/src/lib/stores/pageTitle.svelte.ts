import { settingsState } from '$lib/stores/settings.svelte'

class TitleStore {
	pageTitle = $state('')

	pageFullTitle = $derived.by(() => {
		const rawTitle = this.pageTitle.trim()
		const appName = settingsState.data?.branding?.site_name?.trim() ?? ''

		if (!rawTitle) return appName
		if (!appName) return rawTitle
		return `${rawTitle} · ${appName}`
	})
}

export const pageTitleStore = new TitleStore()
