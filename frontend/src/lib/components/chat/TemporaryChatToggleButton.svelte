<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import ChatBubbleDotted from '$lib/components/icons/ChatBubbleDotted.svelte'
	import ChatBubbleDottedChecked from '$lib/components/icons/ChatBubbleDottedChecked.svelte'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { chat } from '$lib/stores/chat.svelte'

	type SidebarContext = {
		selectChat?: (id: string | null) => void
	}

	const sidebar = useSidebar() as SidebarContext | null

	const chatParam = $derived(browser ? page.url.searchParams.get('chat') : null)

	const isActive = $derived(chatParam === 'temp' || (chat.activeThread?.is_temporary ?? false))

	function requestHomeInputFocus() {
		if (!browser) return
		window.dispatchEvent(new CustomEvent('nokodo:focus-home-input'))
	}

	function goHome() {
		sidebar?.selectChat?.(null)
		const isAlreadyHome = page.url.pathname === '/' && chatParam === null
		if (isAlreadyHome) {
			requestHomeInputFocus()
			return
		}
		void goto(resolve('/'), { keepFocus: true, noScroll: true })
	}

	function goTemp() {
		sidebar?.selectChat?.(null)
		const isAlreadyTemp = page.url.pathname === '/' && chatParam === 'temp'
		if (isAlreadyTemp) {
			requestHomeInputFocus()
			return
		}
		// @ts-expect-error resolve typing is narrower than our constructed URL
		void goto(resolve('/?chat=temp' as never), { keepFocus: true, noScroll: true })
	}

	function toggle() {
		if (isActive) {
			goHome()
		} else {
			goTemp()
		}
	}
</script>

<button
	class="flex h-12 w-auto min-w-8 cursor-pointer items-center justify-center px-1 text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97] md:w-12 md:px-0"
	onclick={toggle}
	aria-label="temporary chat"
>
	{#if isActive}
		<ChatBubbleDottedChecked className="h-6 w-6" />
	{:else}
		<ChatBubbleDotted className="h-6 w-6" />
	{/if}
</button>
