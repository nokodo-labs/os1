<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'

	interface Props {
		/** the form differs from the values the modal opened with. */
		dirty: boolean
		/** a save is already in flight. */
		saving?: boolean
		/** the modal's own reason for refusing a save, e.g. an empty required field. */
		blockedReason?: string | null
		label?: string
		savingLabel?: string
		/** submits the surrounding form by default; pass a handler to act instead. */
		onclick?: () => void
		class?: string
	}

	let {
		dirty,
		saving = false,
		blockedReason = null,
		label = 'save',
		savingLabel = 'saving',
		onclick,
		class: className = '',
	}: Props = $props()

	// inert rather than `disabled`: the button keeps its place in the tab order and
	// carries the reason it cannot act, instead of being silently dimmed.
	const inertReason = $derived(
		saving
			? `${savingLabel} in progress`
			: (blockedReason ?? (dirty ? null : 'no changes to save'))
	)
	const inert = $derived(inertReason !== null)

	function handleClick(event: MouseEvent): void {
		if (inert) {
			event.preventDefault()
			return
		}
		onclick?.()
	}

	const baseClass =
		'rounded-pill inline-flex min-h-9 items-center justify-center gap-1.5 bg-(--accent-primary) px-4 text-sm font-semibold text-white transition-all duration-150'
</script>

<button
	type="submit"
	class="{baseClass} {inert
		? 'cursor-not-allowed opacity-55'
		: 'cursor-pointer hover:brightness-[1.06] active:scale-[0.97]'} {className}"
	aria-disabled={inert}
	aria-label={inertReason ? `${label}, ${inertReason}` : undefined}
	title={inertReason ?? undefined}
	onclick={handleClick}
>
	<Check class="h-4 w-4" />
	{#if saving}
		<ShimmerText className="inline-block">{savingLabel}</ShimmerText>
	{:else}
		<span>{label}</span>
	{/if}
</button>
