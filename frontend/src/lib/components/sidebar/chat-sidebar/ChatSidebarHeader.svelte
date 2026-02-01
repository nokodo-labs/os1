<script lang="ts">
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import Sidebar from '$lib/components/icons/Sidebar.svelte'

	export let isChatSidebarOpen: boolean
	export let isCompactLayout: boolean
	export let showTopLabels: boolean
	export let onHomeClick: () => void
	export let onCloseClick: () => void
</script>

<!-- Logo / Brand with Close Button -->
<div class="relative grid w-full grid-cols-[auto_1fr_auto] items-center">
	<button
		class="group relative flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full border border-transparent bg-transparent text-white/80 transition-all duration-200 hover:text-white"
		onclick={onHomeClick}
		aria-label="Home"
	>
		<!-- Symmetrical float animation (centered) -->
		<div
			class="relative flex h-8 w-8 shrink-0 animate-[float_3s_ease-in-out_infinite] items-center justify-center rounded-full shadow-[0_4px_12px_var(--accent-shadow),inset_0_2px_8px_rgba(255,255,255,0.3)] transition-[background,box-shadow] duration-300 group-hover:shadow-[0_6px_16px_var(--accent-shadow),inset_0_2px_8px_rgba(255,255,255,0.4)]"
			style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-secondary));"
		>
			{#if !isChatSidebarOpen}
				<div
					class="absolute flex scale-75 items-center justify-center text-white opacity-0 transition-all duration-300 group-hover:scale-100 group-hover:opacity-100"
				>
					<Sidebar class="h-4 w-4" />
				</div>
			{/if}
		</div>
	</button>

	<div
		class="flex min-w-0 items-center justify-center overflow-hidden px-2 transition-[opacity,transform] duration-200 ease-out {showTopLabels
			? 'translate-y-0 opacity-100'
			: '-translate-y-0.5 opacity-0'}"
		aria-hidden={!showTopLabels}
	>
		<img
			src="https://nokodo.net/media/images/logo_full.svg"
			alt="nokodo logo"
			class="h-7 w-auto shrink-0 -translate-y-[5px] object-contain"
		/>
	</div>

	<!-- Close button -->
	<button
		class="relative flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full border border-transparent bg-transparent text-white/80 transition-all duration-200 hover:border-white/10 hover:bg-white/5 hover:text-white active:scale-[0.99] {!isCompactLayout
			? 'opacity-100'
			: 'pointer-events-none opacity-0'}"
		onclick={(e) => {
			e.stopPropagation()
			onCloseClick()
		}}
		aria-label="Close sidebar"
	>
		<ChevronLeft class="h-5 w-5" />
	</button>
</div>

<style>
	/* Symmetrical float animation (centered at 0, oscillates up/down) */
	@keyframes float {
		0%,
		100% {
			transform: translateY(0px);
		}
		50% {
			transform: translateY(-8px);
		}
	}
</style>
