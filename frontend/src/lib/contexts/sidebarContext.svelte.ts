import { device } from '$lib/stores/device.svelte'
import { settingsState } from '$lib/stores/settings.svelte'
import { getContext, setContext } from 'svelte'

const SIDEBAR_KEY = Symbol('sidebar')

export function createSidebarContext() {
	let isOpen = $state(false)
	let isChatSidebarOpen = $state(false)
	let selectedChatId = $state(null)
	let initialSidebarSynced = false

	// sync sidebar_collapsed setting once when settings finish loading
	$effect.root(() => {
		$effect(() => {
			if (!settingsState.ready || initialSidebarSynced) return
			initialSidebarSynced = true
			const collapsed = settingsState.data?.ui?.sidebar_collapsed ?? true
			// on mobile, sidebar always starts closed regardless of setting
			if (device.isMobile) return
			isChatSidebarOpen = !collapsed
			isOpen = !collapsed
		})
	})

	const context = {
		get isOpen() {
			return isOpen
		},
		get isChatSidebarOpen() {
			return isChatSidebarOpen
		},
		get selectedChatId() {
			return selectedChatId
		},
		toggleSidebar() {
			isOpen = !isOpen
		},
		toggleChatSidebar() {
			isChatSidebarOpen = !isChatSidebarOpen
		},
		// @ts-expect-error - svelte.ts doesn't support type annotations
		selectChat(id) {
			selectedChatId = id
		},
		openSidebar() {
			isOpen = true
		},
		closeSidebar() {
			isOpen = false
		},
		openChatSidebar() {
			isChatSidebarOpen = true
		},
		closeChatSidebar() {
			isChatSidebarOpen = false
		},
	}

	setContext(SIDEBAR_KEY, context)
	return context
}

export function useSidebar() {
	const context = getContext(SIDEBAR_KEY)
	if (!context) {
		throw new Error('useSidebar must be used within a SidebarProvider')
	}
	return context
}
