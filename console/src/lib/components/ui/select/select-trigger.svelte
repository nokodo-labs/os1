<script lang="ts">
	import { cn } from '$lib/utils'
	import { ChevronDown } from '@lucide/svelte'
	import { Select as SelectPrimitive } from 'bits-ui'

	let { class: className = '', children, ...rest }: SelectPrimitive.TriggerProps = $props()
</script>

<SelectPrimitive.Trigger
	class={cn(
		'ring-offset-background flex h-10 w-full items-center justify-between rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:ring-2 focus:ring-zinc-500 focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50',
		className
	)}
	{...rest}
>
	{#if children}
		<span class="min-w-0 flex-1 truncate text-left">{@render children()}</span>
	{/if}
	<ChevronDown class="ml-1 h-4 w-4 shrink-0 opacity-50" />
</SelectPrimitive.Trigger>
