<script lang="ts">
	/**
	 * the think row's live label: a shuffled walk through the thinking verbs,
	 * swapped every few seconds, shimmering the whole time it runs.
	 */

	import { createThinkingVerbCycle, thinkingVerbDelayMs } from '$lib/chat/thinkingVerbs'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import { device } from '$lib/stores/device.svelte'

	interface Props {
		className?: string
	}

	let { className = '' }: Props = $props()

	const SWAP_MS = 240

	const cycle = createThinkingVerbCycle()

	let current = $state(cycle.next())
	let previous = $state<string | null>(null)
	let seq = $state(0)
	let rotateTimer: ReturnType<typeof setTimeout> | null = null
	let swapTimer: ReturnType<typeof setTimeout> | null = null

	$effect(() => {
		scheduleNext()
		return () => {
			if (rotateTimer) clearTimeout(rotateTimer)
			if (swapTimer) clearTimeout(swapTimer)
			rotateTimer = null
			swapTimer = null
		}
	})

	function scheduleNext() {
		rotateTimer = setTimeout(() => {
			advance()
			scheduleNext()
		}, thinkingVerbDelayMs())
	}

	function advance() {
		const next = cycle.next()
		if (device.prefersReducedMotion) {
			previous = null
			current = next
			return
		}
		previous = current
		current = next
		seq += 1
		if (swapTimer) clearTimeout(swapTimer)
		swapTimer = setTimeout(() => {
			previous = null
			swapTimer = null
		}, SWAP_MS)
	}
</script>

<span
	class="verb-swap"
	data-thinking-verb={current}
	data-swapping={previous !== null ? '' : undefined}
	>{#key seq}{#if previous !== null}<span class="verb verb-out" aria-hidden="true"
				><ShimmerText {className}>{previous}</ShimmerText></span
			>{/if}<span class="verb verb-in"><ShimmerText {className}>{current}</ShimmerText></span
		>{/key}</span
>

<style>
	.verb-swap {
		position: relative;
		display: inline-block;
	}

	.verb-out {
		position: absolute;
		top: 0;
		left: 0;
		white-space: nowrap;
	}

	.verb-swap[data-swapping] .verb-in {
		animation: verb-swap-in 240ms cubic-bezier(0.22, 1, 0.36, 1) both;
	}

	.verb-swap[data-swapping] .verb-out {
		animation: verb-swap-out 240ms cubic-bezier(0.22, 1, 0.36, 1) both;
	}

	@keyframes verb-swap-in {
		from {
			transform: translateY(0.45em);
			opacity: 0;
		}
		to {
			transform: translateY(0);
			opacity: 1;
		}
	}

	@keyframes verb-swap-out {
		from {
			transform: translateY(0);
			opacity: 1;
		}
		to {
			transform: translateY(-0.45em);
			opacity: 0;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.verb-swap[data-swapping] .verb-in,
		.verb-swap[data-swapping] .verb-out {
			animation: none;
		}
	}
</style>
