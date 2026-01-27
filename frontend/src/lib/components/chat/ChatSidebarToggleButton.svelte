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
	class="flex h-12 w-auto min-w-8 cursor-pointer items-center justify-center px-1 text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97] md:w-12 md:px-0"
	onclick={() => sidebar?.toggleChatSidebar?.()}
	aria-label={sidebar?.isChatSidebarOpen ? 'close sidebar' : 'open sidebar'}
	aria-expanded={sidebar?.isChatSidebarOpen}
>
	<Sidebar className="h-6 w-6" />
</button>
