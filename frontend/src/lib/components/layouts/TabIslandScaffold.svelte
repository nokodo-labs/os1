<script lang="ts">
	import { resolve } from '$app/paths'
	import type { Pathname } from '$app/types'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import type { Component, Snippet } from 'svelte'

	/**
	 * tab island scaffold - fullscreen layout with a floating bottom island for section navigation.
	 *
	 * content scrolls beneath both the top chrome island and the bottom tab island,
	 * with padding so resting position has space for both. this means vertical space
	 * is not wasted - same pattern as the chat layout.
	 *
	 * the active tab has a sliding highlight element (lens) that animates between
	 * tabs via CSS transitions. page content fades via the View Transitions API
	 * (handled globally in the root layout).
	 */

	interface Section {
		id: string
		label: string
		icon: Component
		href: Pathname
	}

	interface Props {
		sections: Section[]
		activeId: string
		children: Snippet
	}

	let { sections, activeId, children }: Props = $props()

	let islandEl = $state<HTMLElement | null>(null)
	let islandHeight = $state(0)
	let navContainerEl = $state<HTMLElement | null>(null)
	let tabEls = $state<Record<string, HTMLElement | null>>({})

	// sliding highlight position relative to the nav container
	let highlightStyle = $state('')

	$effect(() => {
		if (!islandEl) return
		const observer = new ResizeObserver(([entry]) => {
			islandHeight = entry.contentRect.height
		})
		observer.observe(islandEl)
		return () => observer.disconnect()
	})

	// offset metrics, not rects: they ignore the hover/press scale on the tabs,
	// so the lens never inherits a transformed size.
	$effect(() => {
		const container = navContainerEl
		const activeEl = tabEls[activeId]
		if (!container || !activeEl) return

		highlightStyle = `left: ${activeEl.offsetLeft}px; top: ${activeEl.offsetTop}px; width: ${activeEl.offsetWidth}px; height: ${activeEl.offsetHeight}px;`
	})

	const bottomPad = $derived(islandHeight + 24 + 16)
</script>

<div class="absolute inset-0 overflow-y-auto">
	<div
		class="flex min-h-full flex-col"
		style="padding-top: calc(var(--chrome-island-offset, 0px) + var(--spacing-island-content)); padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); padding-bottom: {bottomPad}px; view-transition-name: tab-page-content;"
	>
		{@render children()}
	</div>
</div>

<nav
	bind:this={islandEl}
	class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2"
	aria-label="section navigation"
>
	<LiquidGlass
		class="flex items-center gap-1 rounded-full px-2 py-1.5"
		style="--island-accent: var(--accent-primary, currentColor); --island-motion: 150ms cubic-bezier(0.4, 0, 0.2, 1);"
	>
		<div bind:this={navContainerEl} class="relative flex items-center gap-1">
			<!-- sliding highlight lens -->
			{#if highlightStyle}
				<div
					class="tab-island-lens pointer-events-none absolute rounded-full bg-(--island-accent)/15 transition-all duration-300 ease-in-out"
					style={highlightStyle}
				></div>
			{/if}

			{#each sections as section (section.id)}
				{@const active = activeId === section.id}
				{@const Icon = section.icon}
				{@const link = resolve(section.href as '/')}
				<a
					bind:this={tabEls[section.id]}
					href={link}
					class="tab-island-option relative z-1 flex flex-col items-center gap-0.5 rounded-full px-5 py-1.5 hover:scale-[1.06] active:scale-[0.97]
						{active ? 'text-(--island-accent)' : 'text-foreground/50 hover:text-foreground/75'}"
					aria-current={active ? 'page' : undefined}
				>
					<Icon class="h-5 w-5" variant={active ? 'solid' : 'outline'} />
					<span class="text-[0.625rem] leading-tight font-semibold">{section.label}</span>
				</a>
			{/each}
		</div>
	</LiquidGlass>
</nav>

<style>
	/* same motion language as the island controls and the dock. the scale
	   utilities set the `scale` property, so the transition has to name it -
	   listing only colours or `transform` leaves the sizes snapping. */
	.tab-island-option {
		transition:
			scale var(--island-motion),
			color var(--island-motion);
	}

	@media (prefers-reduced-motion: reduce) {
		.tab-island-option {
			scale: 1;
			transition-duration: 0.01ms;
		}
		.tab-island-lens {
			transition-duration: 0.01ms;
		}
	}

	/* cross-fade page content during view transitions */
	@keyframes tab-fade-in {
		from {
			opacity: 0;
			transform: translateY(4px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}
	@keyframes tab-fade-out {
		from {
			opacity: 1;
			transform: none;
		}
		to {
			opacity: 0;
			transform: translateY(-4px);
		}
	}

	:root[data-vt-active='1']::view-transition-old(tab-page-content) {
		animation: tab-fade-out 180ms ease-in forwards;
	}
	:root[data-vt-active='1']::view-transition-new(tab-page-content) {
		animation: tab-fade-in 180ms ease-out 60ms both;
	}
</style>
