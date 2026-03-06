<script lang="ts">
	import type { Component } from 'svelte'

	interface PageTitleProps {
		icon: Component<{ class?: string; variant?: 'outline' | 'solid' }>
		label: string
		iconColor?: string
		tag?: 'h1' | 'h2'
		class?: string
	}

	let {
		icon: Icon,
		label,
		iconColor = 'text-foreground',
		tag = 'h1',
		class: className = '',
	}: PageTitleProps = $props()
</script>

<div class="flex items-center gap-3 {className}">
	<Icon class="h-7 w-7 shrink-0 {iconColor}" variant="solid" />
	<svelte:element this={tag} class="min-w-0 truncate text-2xl font-bold text-foreground">
		{label}
	</svelte:element>
</div>
