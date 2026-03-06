<script lang="ts">
	import type { ToolExecution } from '$lib/tools'

	interface Props {
		execution: ToolExecution
	}

	let { execution }: Props = $props()

	/** parse memory items from result */
	let memories = $derived.by(() => {
		if (!execution.result || execution.result.isError) return []
		try {
			const parsed = JSON.parse(execution.result.output)
			if (Array.isArray(parsed)) {
				return parsed
					.filter(
						(m): m is { content: string } =>
							typeof m === 'object' && m !== null && typeof m.content === 'string'
					)
					.map((m) => m.content)
			}
			// check for a memories/items array field
			for (const val of Object.values(parsed)) {
				if (Array.isArray(val)) {
					return val
						.filter((v): v is string | { content: string } => {
							if (typeof v === 'string') return true
							return (
								typeof v === 'object' &&
								v !== null &&
								typeof (v as Record<string, unknown>).content === 'string'
							)
						})
						.map((v) =>
							typeof v === 'string' ? v : (v as { content: string }).content
						)
				}
			}
		} catch {
			// fallback: show raw output lines
			return execution.result.output
				.split('\n')
				.filter((line) => line.trim())
				.slice(0, 10)
		}
		return []
	})
</script>

{#if memories.length > 0}
	<div class="space-y-1">
		{#each memories as memory, idx (idx)}
			<div class="bg-foreground/5 text-foreground/80 rounded-lg px-2.5 py-1.5 text-xs">
				{memory}
			</div>
		{/each}
	</div>
{/if}
