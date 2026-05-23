<script lang="ts">
	import type { RunActivityState } from '$lib/chat'
	import RunActivityRow from './RunActivityRow.svelte'

	interface Props {
		activity: RunActivityState
	}

	let { activity }: Props = $props()

	function activeLabel(value: RunActivityState): string {
		return value.title ?? 'compacting chat'
	}

	function successLabel(_value: RunActivityState, duration: string): string {
		return `chat compacted in ${duration}`
	}

	function errorLabel(_value: RunActivityState, duration: string): string {
		return `compaction failed after ${duration}`
	}

	function cancelledLabel(_value: RunActivityState, duration: string): string {
		return `compaction cancelled after ${duration}`
	}
</script>

<RunActivityRow
	{activity}
	getActiveLabel={activeLabel}
	getSuccessLabel={successLabel}
	getErrorLabel={errorLabel}
	getCancelledLabel={cancelledLabel}
/>
