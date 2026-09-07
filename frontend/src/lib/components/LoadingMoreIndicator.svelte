<script lang="ts">
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'

	let { className = '', label = 'loading more' } = $props<{
		className?: string
		label?: string
	}>()
</script>

<div class="loading-more flex items-center justify-center py-4 {className}" aria-label={label}>
	<NokodoLoader className="opacity-70" expanded={false} />
</div>

<style>
	/*
	 * the collapsed loader still lays out the whole word "nokodo" with only "ok"
	 * painted, and splash.css slides it sideways to roughly compensate - which is
	 * calibrated for the splash screen, not for a list. this loader never opens,
	 * so drop the unpainted letters from layout and the flex centring lands on
	 * exactly what is on screen.
	 */
	.loading-more :global(.nokodo-loader) {
		transform: none;
	}

	.loading-more :global(.nokodo-loader__hidden) {
		display: none;
	}
</style>
