<script lang="ts">
	import { runFailureLabel } from '$lib/chat/runFailures'
	import type { RunFailureEntry } from '$lib/chat/types'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import ExclamationTriangle from '$lib/components/icons/ExclamationTriangle.svelte'
	import Stop from '$lib/components/icons/Stop.svelte'
	import { RESOURCE_META_DIVIDER } from '$lib/utils/resourceAuthors'
	import { fade } from 'svelte/transition'

	interface Props {
		failure: RunFailureEntry
		/** false once a later answer from this agent superseded the failure. */
		outstanding: boolean
		/** offered only while outstanding; re-runs through the normal run path. */
		onRetry?: () => void
		retrying?: boolean
	}

	let { failure, outstanding, onRetry, retrying = false }: Props = $props()

	const label = $derived(runFailureLabel(failure.reason))
	// stopping is something the reader did on purpose, so it is reported, never
	// alarmed about: no warning icon and no error tint.
	const selfInflicted = $derived(failure.reason === 'cancelled')
</script>

<!--
	an inline timeline row, not a card: it sits among assistant text and tool
	rows, so it matches their rhythm and stays quiet once superseded.
-->
<div class="flex items-center gap-2.5 py-1" in:fade={{ duration: 120 }}>
	<div class="flex h-5 w-6 shrink-0 items-center justify-center">
		{#if selfInflicted}
			<Stop class="text-foreground/45 h-3 w-3" />
		{:else}
			<ExclamationTriangle
				class="h-3.5 w-3.5 {outstanding ? 'text-destructive/80' : 'text-foreground/35'}"
				strokeWidth="2"
			/>
		{/if}
	</div>

	<div class="min-w-0 flex-1 text-sm">
		<span class={outstanding && !selfInflicted ? 'text-foreground/75' : 'text-foreground/45'}
			>{label}</span
		>
		{#if !outstanding}
			<span class="text-foreground/35">{RESOURCE_META_DIVIDER}answered later</span>
		{/if}
	</div>

	{#if outstanding && onRetry}
		<button
			type="button"
			class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/80 hover:bg-foreground/10 hover:text-foreground/90 flex shrink-0 cursor-pointer items-center gap-1.5 border px-3 py-1 text-xs font-medium transition-colors disabled:cursor-default disabled:opacity-55"
			disabled={retrying}
			onclick={onRetry}
		>
			<ArrowPath class="size-3.5" strokeWidth="2.5" />
			{#if retrying}
				<ShimmerText className="inline-block">retrying</ShimmerText>
			{:else}
				<span>try again</span>
			{/if}
		</button>
	{/if}
</div>
