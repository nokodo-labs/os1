<script lang="ts">
	import PageTitle from '$lib/components/PageTitle.svelte'
	import type { Component, Snippet } from 'svelte'

	/**
	 * shared header for master/detail sidebars (reminders, notes, settings).
	 *
	 * desktop: fixed header bar aligned to the island, with optional action buttons.
	 * mobile: a heading that scrolls with the list, padded to clear the island.
	 */
	interface Props {
		icon: Component<{ class?: string; variant?: 'outline' | 'solid' }>
		label: string
		iconColor?: string
		isMobile?: boolean
		/** desktop-only action buttons rendered on the right of the header bar */
		actions?: Snippet
	}

	let { icon, label, iconColor, isMobile = false, actions }: Props = $props()
</script>

{#if isMobile}
	<div
		class="px-2 pb-4 pt-[calc(var(--chrome-island-offset,0px)+var(--spacing-island-content)+1rem)]"
	>
		<PageTitle {icon} {label} {iconColor} tag="h2" />
	</div>
{:else}
	<header
		class="mt-(--master-detail-header-top) mb-(--spacing-island-content) h-(--master-detail-header-height) relative z-10 flex shrink-0 items-center justify-between gap-3 px-[calc(var(--spacing-page-x)+0.5rem)] py-0"
	>
		<PageTitle {icon} {label} {iconColor} tag="h2" />
		{#if actions}
			<div class="flex items-center gap-1">
				{@render actions()}
			</div>
		{/if}
	</header>
{/if}
