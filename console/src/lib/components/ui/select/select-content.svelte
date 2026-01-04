<script lang="ts">
	import { cn } from '$lib/utils'
	import { Select as SelectPrimitive } from 'bits-ui'

	let { class: className = '', children, ...rest } = $props()
</script>

<SelectPrimitive.Portal>
	<SelectPrimitive.Content
		class={cn(
			'z-50 max-h-[60vh] w-(--bits-select-anchor-width) max-w-(--bits-select-anchor-width) min-w-(--bits-select-anchor-width) overflow-x-hidden overflow-y-auto rounded-md border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-md focus:outline-none',
			className
		)}
		{...rest}
	>
		<div class="p-1">
			{@render children?.()}
		</div>
	</SelectPrimitive.Content>
</SelectPrimitive.Portal>
