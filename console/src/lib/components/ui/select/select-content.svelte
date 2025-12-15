<script lang="ts">
	import { cn } from '$lib/utils'
	import { Select as SelectPrimitive } from 'bits-ui'

	let { class: className = '', children, ...rest } = $props()
</script>

<SelectPrimitive.Portal>
	<SelectPrimitive.Content
		class={cn(
			'z-50 min-w-[10rem] overflow-hidden rounded-md border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-md focus:outline-none',
			className
		)}
		{...rest}
	>
		<SelectPrimitive.Viewport class="p-1">
			{@render children?.()}
		</SelectPrimitive.Viewport>
	</SelectPrimitive.Content>
</SelectPrimitive.Portal>
