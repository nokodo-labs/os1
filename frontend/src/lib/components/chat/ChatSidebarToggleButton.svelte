<script lang="ts">
	import Sidebar from '$lib/components/icons/Sidebar.svelte'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'

	type SidebarContext = {
		toggleChatSidebar?: () => void
		isChatSidebarOpen?: boolean
	}

	const sidebar = useSidebar() as SidebarContext | null
</script>

<button
	class="flex cursor-pointer items-center justify-center opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
	onclick={() => sidebar?.toggleChatSidebar?.()}
	aria-label={sidebar?.isChatSidebarOpen ? 'close sidebar' : 'open sidebar'}
	aria-expanded={sidebar?.isChatSidebarOpen}
>
	<Sidebar variant="solid" />
</button>
