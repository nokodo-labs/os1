<script lang="ts">
	import type { Snippet } from 'svelte'
	import { onMount } from 'svelte'
	import { getFallbackStyles, supportsSVGFilterAsBackdrop } from './compat'

	interface Props {
		children?: Snippet
		fallbackChildren?: Snippet
	}

	let { children, fallbackChildren }: Props = $props()

	let isSupported = $state(false)

	onMount(() => {
		isSupported = supportsSVGFilterAsBackdrop()
	})

	const fallbackStyle = $derived(
		Object.entries(getFallbackStyles())
			.map(([k, v]) => `${k}: ${v}`)
			.join('; ')
	)
</script>

{#if isSupported}
	{@render children?.()}
{:else if fallbackChildren}
	{@render fallbackChildren?.()}
{:else}
	<div style={fallbackStyle}>
		{@render children?.()}
	</div>
{/if}
