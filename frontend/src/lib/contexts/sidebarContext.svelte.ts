import { getContext, setContext } from 'svelte'
import { settingsState } from '$lib/stores/settings.svelte'

const SIDEBAR_KEY = Symbol('sidebar')

export function createSidebarContext() {
	// initialize from admin setting: sidebar_collapsed means isOpen = !collapsed
	let isOpen = $state(!(settingsState.data?.ui?.sidebar_collapsed ?? false))
	let isChatSidebarOpen = $state(false)
	let selectedChatId = $state(null)

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
