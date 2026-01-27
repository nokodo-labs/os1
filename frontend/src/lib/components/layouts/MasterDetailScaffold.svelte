<script lang="ts">
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { Snippet } from 'svelte'

	/**
	 * master/detail scaffold for apps like reminders, settings, etc.
	 *
	 * desktop: fixed master sidebar on left + content area on right.
	 * mobile: content fills screen; master is a separate route.
	 *
	 * API:
	 * - master: snippet for the master sidebar content (receives { isMobile } for layout adjustments)
	 * - children: snippet for the detail/content area
	 * - masterWidthClass: tailwind width class for the master sidebar (default: 'w-[clamp(280px,30vw,520px)]')
	 * - ariaLabel: accessibility label for the master sidebar
	 */
	interface Props {
		/** master sidebar content (rendered on desktop, or as full page on mobile) */
		master: Snippet<[{ isMobile: boolean }]>
		/** detail/content area */
		children: Snippet
		/** tailwind width class for the master sidebar */
		masterWidthClass?: string
		/** accessibility label for the master sidebar */
		ariaLabel?: string
	}

	let {
		master,
		children,
		masterWidthClass = 'w-[clamp(280px,30vw,520px)]',
		ariaLabel = 'sidebar',
	}: Props = $props()

	const chrome = useSystemChrome()

	// register/unregister layout insets with chrome context
	$effect(() => {
		if (device.isMobile) {
			chrome.clearLayoutInsets()
			return
		}

		chrome.setLayoutInsets({
			leftWidthClass: masterWidthClass,
			leftViewTransitionName: 'master-sidebar',
		})

		return () => {
			chrome.clearLayoutInsets()
		}
	})
</script>

{#if !device.isMobile}
	<!-- desktop: fixed master sidebar -->
	<aside
		class="fixed inset-y-0 left-0 z-40 {masterWidthClass} overflow-hidden"
		aria-label={ariaLabel}
		style="view-transition-name: master-sidebar;"
	>
		<div class="relative h-full px-[clamp(10px,4vw,32px)] pt-[clamp(12px,1vw,32px)] pb-10">
			{@render master({ isMobile: false })}
			<!-- separator (doesn't reach top/bottom) -->
			<div
				class="pointer-events-none absolute top-[clamp(28px,4vw,44px)] right-0 bottom-[clamp(28px,4vw,44px)] w-px bg-linear-to-b from-transparent via-white/10 to-transparent"
				aria-hidden="true"
			></div>
		</div>
	</aside>
{/if}

<!-- content area: scrollbar at edge, padding inside content -->
<div
	class="absolute inset-0 overflow-y-auto"
	style="padding-top: calc(var(--chrome-island-offset, 0px) + 16px);"
>
	<div class="px-[clamp(12px,3vw,36px)] pb-10">
		{@render children()}
	</div>
</div>
