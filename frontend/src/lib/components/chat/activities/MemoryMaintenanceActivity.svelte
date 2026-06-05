<script lang="ts">
	import type { RunActivityState } from '$lib/chat'
	import Brain from '$lib/components/icons/Brain.svelte'
	import RunActivityRow from './RunActivityRow.svelte'

	interface Props {
		activity: RunActivityState
	}

	let { activity }: Props = $props()

	function activeLabel(value: RunActivityState): string {
		return value.title ?? 'updating memory'
	}

	function successLabel(value: RunActivityState): string {
		return value.message ?? 'memory updated'
	}

	function errorLabel(_value: RunActivityState, duration: string): string {
		return `memory update failed after ${duration}`
	}

	function cancelledLabel(_value: RunActivityState, duration: string): string {
		return `memory update cancelled after ${duration}`
	}
</script>

<RunActivityRow
	{activity}
	icon={Brain}
	iconClass="text-foreground/70 h-4.5 w-4.5"
	getActiveLabel={activeLabel}
	getSuccessLabel={successLabel}
	getErrorLabel={errorLabel}
	getCancelledLabel={cancelledLabel}
/>
