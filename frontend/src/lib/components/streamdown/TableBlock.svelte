<script lang="ts">
	import { useStreamdown } from 'svelte-streamdown'
	import type { Snippet } from 'svelte'
	import TableControls from './TableControls.svelte'

	let {
		token,
		children,
	}: {
		token: { raw: string }
		children: Snippet
	} = $props()

	const streamdown = useStreamdown()
	const id = $props.id()
	const style = $derived(streamdown.isMounted ? streamdown.animationBlockStyle : '')
</script>

{#if streamdown.controls.table}
	<TableControls {id} raw={token.raw} />
{/if}
<div
	data-streamdown-table={id}
	{style}
	class={`${streamdown.theme.table.base} group`}
	style:overscroll-behavior-x="none"
>
	<table class={streamdown.theme.table.table}>
		{@render children()}
	</table>
</div>
