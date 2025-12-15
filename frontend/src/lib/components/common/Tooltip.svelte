<script lang="ts">
	import type { Snippet } from 'svelte'
	import { onDestroy, onMount } from 'svelte'
	import tippy, { type Instance, type Placement } from 'tippy.js'
	import 'tippy.js/dist/tippy.css'

	interface Props {
		content: string
		placement?: Placement
		className?: string
		children: Snippet
	}

	let { content, placement = 'top', className = '', children }: Props = $props()

	let tooltipElement: HTMLElement
	let tooltipInstance: Instance | null = null

	onMount(() => {
		if (tooltipElement && content) {
			tooltipInstance = tippy(tooltipElement, {
				content: content,
				placement: placement,
				arrow: false,
				offset: [0, 8],
				animation: 'scale',
				duration: [200, 150],
			})
		}
	})

	$effect(() => {
		if (tooltipInstance && content) {
			tooltipInstance.setContent(content)
		}
	})

	onDestroy(() => {
		if (tooltipInstance) {
			tooltipInstance.destroy()
		}
	})
</script>

<div bind:this={tooltipElement} class={className}>
	{@render children()}
</div>

<style>
	:global(.tippy-box) {
		background-color: #000;
		border-radius: 999px;
		padding: 6px 12px;
		font-size: 0.75rem;
	}

	:global(.tippy-box .tippy-content) {
		padding: 0;
	}
</style>
