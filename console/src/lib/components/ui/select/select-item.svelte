<script lang="ts">
	import { cn } from '$lib/utils'
	import { Check } from '@lucide/svelte'
	import { Select as SelectPrimitive } from 'bits-ui'
	import type { Snippet } from 'svelte'

	type Props = Omit<SelectPrimitive.ItemProps, 'children'> & {
		children?: Snippet
	}

	let { class: className = '', children, ...rest }: Props = $props()
</script>

<SelectPrimitive.Item
	class={cn(
		'group relative flex w-full cursor-pointer items-center rounded-sm px-3 py-2 text-sm text-zinc-200 outline-none select-none hover:bg-zinc-800 hover:text-white data-highlighted:bg-zinc-800 data-highlighted:text-white data-[state=checked]:bg-zinc-800',
		className
	)}
	{...rest}
>
	<span
		class="absolute left-2 flex h-3.5 w-3.5 items-center justify-center text-zinc-100 opacity-0 transition-opacity group-data-[state=checked]:opacity-100"
	>
		<Check class="h-3 w-3" />
	</span>
	<span class="flex-1 truncate">
		{@render children?.()}
	</span>
</SelectPrimitive.Item>
