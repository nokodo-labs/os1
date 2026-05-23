<script lang="ts">
	import type { RunActivityState } from '$lib/chat'
	import RunActivityRow from './RunActivityRow.svelte'

	interface Props {
		activity: RunActivityState
	}

	let { activity }: Props = $props()

	function displayName(value: RunActivityState): string {
		return value.message ?? value.title ?? value.activityType.replace(/_/g, ' ')
	}

	function activeLabel(value: RunActivityState): string {
		return displayName(value)
	}

	function successLabel(value: RunActivityState, duration: string): string {
		return `${displayName(value)} completed in ${duration}`
	}

	function errorLabel(value: RunActivityState, duration: string): string {
		return `${displayName(value)} failed after ${duration}`
	}

	function cancelledLabel(value: RunActivityState, duration: string): string {
		return `${displayName(value)} cancelled after ${duration}`
	}
</script>

<RunActivityRow
	{activity}
	getActiveLabel={activeLabel}
	getSuccessLabel={successLabel}
	getErrorLabel={errorLabel}
	getCancelledLabel={cancelledLabel}
/>
