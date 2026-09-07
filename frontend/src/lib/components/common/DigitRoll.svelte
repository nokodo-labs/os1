<script lang="ts">
	/**
	 * renders a number as fixed-width slots where only the digits that actually
	 * changed roll over: the old digit drops out the bottom while the new one
	 * falls in from the top.
	 */

	import { device } from '$lib/stores/device.svelte'
	import { onDestroy, untrack } from 'svelte'

	interface Props {
		/** the text to display; digits roll, everything else swaps in place. */
		value: string
		className?: string
	}

	let { value, className = '' }: Props = $props()

	const ROLL_MS = 200

	interface Slot {
		char: string
		isDigit: boolean
		/** the digit still falling out, or null when the slot is settled. */
		previous: string | null
		/** bumped per roll so the slot's nodes are rebuilt and replay the roll. */
		seq: number
	}

	let slots = $state<Slot[]>([])
	let rolls = 0
	/** one pending settle timer per slot, indexed alongside the slots. */
	let settleTimers: (ReturnType<typeof setTimeout> | null)[] = []

	$effect(() => {
		const next = value
		untrack(() => applyValue(next))
	})

	onDestroy(() => {
		for (const timer of settleTimers) if (timer) clearTimeout(timer)
		settleTimers = []
	})

	function applyValue(next: string) {
		const rolling = !device.prefersReducedMotion
		slots = [...next].map((char, index) => {
			const isDigit = char >= '0' && char <= '9'
			const held = slots[index]
			if (!held || held.char === char) {
				return { char, isDigit, previous: held?.previous ?? null, seq: held?.seq ?? 0 }
			}
			if (!rolling || !isDigit || !held.isDigit) {
				clearSettle(index)
				return { char, isDigit, previous: null, seq: held.seq }
			}
			rolls += 1
			scheduleSettle(index)
			return { char, isDigit, previous: held.char, seq: rolls }
		})
	}

	function scheduleSettle(index: number) {
		clearSettle(index)
		settleTimers[index] = setTimeout(() => {
			settleTimers[index] = null
			const slot = slots[index]
			if (slot) slots[index] = { ...slot, previous: null }
		}, ROLL_MS)
	}

	function clearSettle(index: number) {
		const timer = settleTimers[index]
		if (timer) {
			clearTimeout(timer)
			settleTimers[index] = null
		}
	}
</script>

<!-- authored without whitespace between slots so the value stays one word to copy -->
<span class="digit-roll {className}" data-digit-roll={value}
	>{#each slots as slot, index (index)}{#if slot.isDigit}<span
				class="digit-slot"
				data-rolling={slot.previous !== null ? '' : undefined}
				>{#key slot.seq}{#if slot.previous !== null}<span
							class="digit digit-out"
							aria-hidden="true">{slot.previous}</span
						>{/if}<span class="digit digit-in">{slot.char}</span>{/key}</span
			>{:else}<span class="digit-fixed">{slot.char}</span>{/if}{/each}</span
>

<style>
	.digit-roll {
		display: inline-flex;
		align-items: baseline;
		font-variant-numeric: tabular-nums;
	}

	.digit-slot {
		position: relative;
		display: inline-block;
		width: 1ch;
		text-align: center;
	}

	.digit-out {
		position: absolute;
		inset: 0;
	}

	.digit-slot[data-rolling] .digit-in {
		animation: digit-roll-in 200ms cubic-bezier(0.22, 1, 0.36, 1) both;
	}

	.digit-slot[data-rolling] .digit-out {
		animation: digit-roll-out 200ms cubic-bezier(0.22, 1, 0.36, 1) both;
	}

	@keyframes digit-roll-in {
		from {
			transform: translateY(-0.6em);
			opacity: 0;
		}
		to {
			transform: translateY(0);
			opacity: 1;
		}
	}

	@keyframes digit-roll-out {
		from {
			transform: translateY(0);
			opacity: 1;
		}
		to {
			transform: translateY(0.6em);
			opacity: 0;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.digit-slot[data-rolling] .digit-in,
		.digit-slot[data-rolling] .digit-out {
			animation: none;
		}
	}
</style>
