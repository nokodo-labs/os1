<script lang="ts">
	import { Button } from '$lib/components/ui/button'
	import { cn } from '$lib/utils'
	import { Shield } from '@lucide/svelte'
	import type { HTMLButtonAttributes } from 'svelte/elements'

	type Props = HTMLButtonAttributes & {
		variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link'
		size?: 'default' | 'sm' | 'lg' | 'icon'
		label?: string
		showLabel?: boolean
	}

	let {
		class: className,
		variant = 'ghost',
		size = 'default',
		label = 'access rules',
		showLabel = true,
		...rest
	}: Props = $props()
</script>

<Button
	{...rest}
	{variant}
	{size}
	class={cn(size === 'icon' ? '' : 'gap-2 rounded-xl', className)}
	title={rest.title ?? label}
	aria-label={showLabel && size !== 'icon' ? undefined : label}
>
	<Shield class={size === 'icon' ? 'h-3.5 w-3.5' : 'h-4 w-4'} />
	{#if showLabel && size !== 'icon'}
		{label}
	{/if}
</Button>
