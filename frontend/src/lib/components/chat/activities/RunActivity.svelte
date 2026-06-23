<script lang="ts">
	import type { RunActivityState } from '$lib/chat'
	import { getRunActivityRenderer } from './registry'

	interface Props {
		activity: RunActivityState
	}

	let { activity }: Props = $props()

	let ActivityRenderer = $derived(getRunActivityRenderer(activity.activityType))
</script>

<ActivityRenderer {activity} />
