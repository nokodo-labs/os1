<script lang="ts">
	import type { ToolExecution } from '$lib/tools'
	import { ToolCard } from './tools'

	interface Props {
		execution: ToolExecution
		compact?: boolean
	}

	let { execution, compact = false }: Props = $props()
</script>

<ToolCard {execution} {compact} />
