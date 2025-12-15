<script lang="ts">
	let { message, hint = undefined, className = '' } = $props()
</script>

<div
	class={`col-span-full rounded-2xl border border-dashed border-zinc-800 py-12 text-center text-zinc-500 ${className}`}
>
	<p>{message}</p>
	{#if hint}
		<p class="mt-2 text-xs text-zinc-500">{hint}</p>
	{/if}
</div>
