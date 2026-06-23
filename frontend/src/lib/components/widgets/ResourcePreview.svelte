<script lang="ts">
	import type { Snippet } from 'svelte'

	interface Props {
		icon?: Snippet
		children?: Snippet
		label?: string
		caption?: string
		showFallback?: boolean
		tone?: 'amber' | 'emerald' | 'rose' | 'sky' | 'yellow'
		class?: string
	}

	let {
		icon,
		children,
		label,
		caption,
		showFallback = true,
		tone = 'sky',
		class: className = '',
	}: Props = $props()

	const toneClasses = $derived.by(() => {
		switch (tone) {
			case 'amber':
				return 'bg-amber-500/10 text-amber-300 ring-amber-300/15'
			case 'emerald':
				return 'bg-emerald-500/10 text-emerald-300 ring-emerald-300/15'
			case 'rose':
				return 'bg-rose-500/10 text-rose-300 ring-rose-300/15'
			case 'yellow':
				return 'bg-yellow-400/10 text-yellow-300 ring-yellow-300/15'
			case 'sky':
				return 'bg-sky-500/10 text-sky-300 ring-sky-300/15'
		}
	})
</script>

<div
	class="relative mb-4 flex h-36 shrink-0 overflow-hidden rounded-t-2xl rounded-b-xl ring-1 {toneClasses} {className}"
>
	<div class="absolute inset-0 opacity-70">
		<div class="absolute inset-x-0 top-0 h-px bg-white/20"></div>
		<div
			class="absolute inset-x-0 bottom-0 h-1/2 bg-linear-to-t from-black/10 to-transparent"
		></div>
	</div>

	{#if showFallback}
		<div
			class="relative flex h-full w-full flex-col items-center justify-center gap-2 px-4 text-center"
		>
			{#if icon}
				<div
					class="flex size-12 items-center justify-center rounded-2xl bg-white/10 *:size-6"
				>
					{@render icon()}
				</div>
			{/if}
			{#if label}
				<span class="max-w-full truncate text-sm font-medium">{label}</span>
			{/if}
			{#if caption}
				<span class="max-w-full truncate text-xs text-current/65">{caption}</span>
			{/if}
		</div>
	{/if}

	{#if children}
		<div class="absolute inset-0">
			{@render children()}
		</div>
	{/if}
</div>
