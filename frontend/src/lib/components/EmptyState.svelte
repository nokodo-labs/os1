<script lang="ts">
	import type { Snippet } from 'svelte'

	interface Props {
		label: string
		description?: string
		icon?: Snippet
		class?: string
		compact?: boolean
	}

	let { label, description, icon, class: className = '', compact = false }: Props = $props()
</script>

<div
	data-empty-state
	data-empty-state-label={label}
	class="text-foreground/50 flex min-w-0 flex-col items-center justify-center text-center {compact
		? 'gap-2 px-3 py-4'
		: 'min-h-40 gap-3 px-4 py-10'} {className}"
>
	{#if icon}
		<div
			class="bg-foreground/6 text-foreground/58 flex size-12 items-center justify-center rounded-full"
		>
			{@render icon()}
		</div>
	{/if}
	<div class="flex min-w-0 flex-col items-center gap-1.5">
		<p data-empty-label class="text-foreground/55 text-sm font-semibold">
			{label}
		</p>
		{#if description}
			<p class="text-foreground/38 max-w-xs text-xs leading-5">
				{description}
			</p>
		{/if}
	</div>
</div>
