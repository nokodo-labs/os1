<script lang="ts">
	import {
		PlaceholderRotation,
		placeholderSwapTimings,
	} from '$lib/chat/placeholderRotation.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { untrack } from 'svelte'
	import { backOut, cubicOut } from 'svelte/easing'
	import { fly } from 'svelte/transition'

	interface Props {
		/** the library to cycle through; rotation is off when it is empty. */
		examples: readonly string[]
		/** rotate only while the field is genuinely empty and idle. */
		active: boolean
	}

	let { examples, active }: Props = $props()

	// swapping the library out swaps the queue with it
	const rotation = $derived.by(() => new PlaceholderRotation({ examples }))
	const timings = $derived(placeholderSwapTimings(device.prefersReducedMotion))

	// untracked: start() seeds `current`, which this effect must not depend on
	$effect(() => {
		if (!active) return
		untrack(rotation.start)
		return rotation.stop
	})
</script>

<!--
	decorative twin of the native placeholder, which cannot animate. the real
	textarea keeps its static placeholder for assistive tech and just renders it
	transparent while this layer is up, so nothing here is ever announced.
-->
{#if active && rotation.current}
	<div
		data-placeholder-rotation
		class="pointer-events-none absolute inset-0 overflow-hidden"
		aria-hidden="true"
	>
		{#key rotation.current}
			<span
				class="text-foreground/40 absolute inset-x-1 top-0 block truncate text-[0.9375rem] leading-6 select-none"
				in:fly={{
					y: 14,
					duration: timings.inMs,
					delay: timings.inDelayMs,
					easing: backOut,
				}}
				out:fly={{ y: -14, duration: timings.outMs, easing: cubicOut }}
				>{rotation.current}</span
			>
		{/key}
	</div>
{/if}
