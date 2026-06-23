<script lang="ts">
	import type { RunActivityState } from '$lib/chat'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import type { Component } from 'svelte'
	import { onDestroy } from 'svelte'
	import { fade } from 'svelte/transition'

	type IconComponent = Component<{ class?: string }>
	type ActiveLabel = (activity: RunActivityState) => string
	type TerminalLabel = (activity: RunActivityState, duration: string) => string

	interface Props {
		activity: RunActivityState
		icon?: IconComponent
		iconClass?: string
		getActiveLabel: ActiveLabel
		getSuccessLabel: TerminalLabel
		getErrorLabel: TerminalLabel
		getCancelledLabel: TerminalLabel
	}

	let {
		activity,
		icon: Icon = ArchiveBox,
		iconClass = 'text-foreground/45 h-3.5 w-3.5',
		getActiveLabel,
		getSuccessLabel,
		getErrorLabel,
		getCancelledLabel,
	}: Props = $props()

	let now = $state(Date.now())
	let interval: ReturnType<typeof setInterval> | null = null
	let isActive = $derived(activity.status === 'running')

	function stopTimer(): void {
		if (interval) {
			clearInterval(interval)
			interval = null
		}
	}

	$effect(() => {
		if (!isActive) {
			stopTimer()
			return
		}
		now = Date.now()
		interval = setInterval(() => {
			now = Date.now()
		}, 1000)
		return stopTimer
	})

	onDestroy(stopTimer)

	function formatDuration(milliseconds: number): string {
		const seconds = Math.max(0, Math.round(milliseconds / 1000))
		if (seconds < 60) return `${seconds}s`
		const minutes = Math.floor(seconds / 60)
		const remainder = seconds % 60
		return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`
	}

	let duration = $derived.by(() => {
		const end = activity.endedAt?.getTime() ?? now
		return formatDuration(end - activity.startedAt.getTime())
	})

	let label = $derived.by(() => {
		if (activity.status === 'running') return getActiveLabel(activity)
		if (activity.status === 'success') return getSuccessLabel(activity, duration)
		if (activity.status === 'cancelled') return getCancelledLabel(activity, duration)
		return getErrorLabel(activity, duration)
	})
</script>

<div class="flex items-start gap-2.5 py-1" in:fade={{ duration: 120 }}>
	<div class="relative mt-px flex h-5 w-6 shrink-0 items-center justify-center">
		<Icon class={iconClass} />
	</div>

	<div class="min-w-0 flex-1 text-sm">
		{#if isActive}
			<ShimmerText className="text-foreground/90">{label}</ShimmerText>
		{:else}
			<span class="text-foreground/60">{label}</span>
		{/if}
	</div>
</div>
