<script lang="ts">
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import Sidebar from '$lib/components/icons/Sidebar.svelte'
	import { getMediaUrls } from '$lib/config/media'
	import { activeRunsStore, type GlobalRunState } from '$lib/stores/activeRuns.svelte'

	const {
		isChatSidebarOpen,
		isCompactLayout,
		showTopLabels,
		onHomeClick,
		onCloseClick,
	}: {
		isChatSidebarOpen: boolean
		isCompactLayout: boolean
		showTopLabels: boolean
		onHomeClick: () => void
		onCloseClick: () => void
	} = $props()

	const mediaUrls = $derived(getMediaUrls())
	const sidebarLogoSrc = $derived(
		mediaUrls.sidebarLogo ?? 'https://nokodo.net/media/images/logo_full.svg'
	)
	const runState: GlobalRunState = $derived(activeRunsStore.state)

	const orbBg = $derived.by((): string => {
		if (runState === 'error') return 'linear-gradient(to bottom right, #ef4444, #dc2626)'
		if (runState === 'running') return 'linear-gradient(to bottom right, #eab308, #f59e0b)'
		return 'linear-gradient(to bottom right, #22c55e, #16a34a)'
	})

	const orbShadow = $derived.by((): string => {
		if (runState === 'error')
			return '0 4px 12px rgba(239,68,68,0.4), inset 0 2px 8px rgba(255,255,255,0.3)'
		if (runState === 'running')
			return '0 4px 12px rgba(234,179,8,0.4), inset 0 2px 8px rgba(255,255,255,0.3)'
		return '0 4px 12px rgba(34,197,94,0.35), inset 0 2px 8px rgba(255,255,255,0.3)'
	})

	const isRunning = $derived(runState === 'running')
</script>

<!-- logo / brand with close button -->
<div class="relative grid w-full grid-cols-[auto_1fr_auto] items-center">
	<button
		class="group text-foreground/80 hover:text-foreground relative flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full border border-transparent bg-transparent transition-all duration-200"
		onclick={onHomeClick}
		aria-label="home"
	>
		<div
			class="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-[background,box-shadow] duration-300 {isRunning
				? 'orb-bouncing'
				: ''}"
			style="background: {orbBg}; box-shadow: {orbShadow};"
		>
			{#if !isChatSidebarOpen}
				<div
					class="text-foreground absolute flex scale-75 items-center justify-center opacity-0 transition-all duration-300 group-hover:scale-100 group-hover:opacity-100"
				>
					<Sidebar class="h-4 w-4" />
				</div>
			{/if}
		</div>
	</button>

	<div
		class="flex min-w-0 items-center justify-center overflow-hidden px-2 {showTopLabels
			? 'translate-y-0 opacity-100'
			: '-translate-y-0.5 opacity-0'}"
		aria-hidden={!showTopLabels}
	>
		<img
			src={sidebarLogoSrc}
			alt="nokodo logo"
			class="h-7 w-auto -translate-y-1.25 object-contain"
		/>
	</div>

	<!-- close button -->
	<button
		class="text-foreground relative flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full border border-transparent bg-transparent transition-all {!isCompactLayout
			? 'opacity-100'
			: 'pointer-events-none opacity-0'}"
		onclick={(e) => {
			e.stopPropagation()
			onCloseClick()
		}}
		aria-label="close sidebar"
	>
		<ChevronLeft class="h-8 w-8" />
	</button>
</div>

<style>
	@keyframes orb-bounce {
		0% {
			transform: translateY(0);
			animation-timing-function: ease-out;
		}
		15% {
			transform: translateY(-6px);
			animation-timing-function: ease-in;
		}
		30% {
			transform: translateY(0);
			animation-timing-function: ease-out;
		}
		42% {
			transform: translateY(-3px);
			animation-timing-function: ease-in;
		}
		54% {
			transform: translateY(0);
			animation-timing-function: ease-out;
		}
		62% {
			transform: translateY(-1.5px);
			animation-timing-function: ease-in;
		}
		70%,
		100% {
			transform: translateY(0);
		}
	}

	.orb-bouncing {
		animation: orb-bounce 1.8s ease-in-out infinite;
	}
</style>
