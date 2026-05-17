<script lang="ts">
	import { resolve } from '$app/paths'
	import Bell from '$lib/components/icons/Bell.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import MimeIcon from '$lib/components/icons/MimeIcon.svelte'
	import { files } from '$lib/stores/files.svelte'
	import type { ToolExecution } from '$lib/tools'

	interface Props {
		execution: ToolExecution
		resourceType: 'note' | 'reminder' | 'file' | 'project'
		resourceId: string
	}

	let { execution, resourceType, resourceId }: Props = $props()

	// extract display info from result output
	const resultTitle = $derived.by(() => {
		if (!execution.result || execution.result.isError) return null
		const output = execution.result.output
		const titleLine = output.match(/^title:\s*(.+)/im)
		if (titleLine) return titleLine[1].trim()
		const filenameLine = output.match(/^filename:\s*(.+)/im)
		if (filenameLine) return filenameLine[1].trim()
		// "note created: [id] title" pattern
		const actionMatch = output.match(/\[[^\]]+\]\s*(.+)/)
		if (actionMatch) return actionMatch[1].trim()
		return null
	})

	const displayTitle = $derived(
		resultTitle ?? (execution.toolCall.arguments.title as string) ?? resourceId
	)

	// for file resources, get extra info from files store
	const fileRecord = $derived(resourceType === 'file' ? files.get(resourceId) : null)

	$effect(() => {
		if (resourceType === 'file') {
			void files.ensure(resourceId)
		}
	})

	const iconColor = $derived.by(() => {
		switch (resourceType) {
			case 'note':
				return 'bg-amber-500/15 text-amber-400'
			case 'reminder':
				return 'bg-violet-500/15 text-violet-400'
			case 'project':
				return 'bg-yellow-500/15 text-yellow-400'
			case 'file':
				return 'bg-rose-500/15 text-rose-400'
		}
	})

	const mimeType = $derived(fileRecord?.mime_type ?? null)
</script>

{#snippet resourceContent()}
	<div class="flex size-8 shrink-0 items-center justify-center rounded-lg {iconColor}">
		{#if resourceType === 'file'}
			<MimeIcon {mimeType} class="size-4" />
		{:else if resourceType === 'note'}
			<Document class="size-4" />
		{:else if resourceType === 'project'}
			<FinderFolder class="size-4" />
		{:else}
			<Bell class="size-4" />
		{/if}
	</div>
	<span class="text-foreground/80 min-w-0 flex-1 truncate text-sm font-medium">
		{resourceType === 'file' ? (fileRecord?.filename ?? displayTitle) : displayTitle}
	</span>
{/snippet}

{#if resourceType === 'note'}
	<a
		href={resolve('/notes/[id]', { id: resourceId })}
		class="liquid-glass liquid-glass--frosted mt-1.5 flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200 hover:brightness-110 active:scale-[0.98]"
	>
		{@render resourceContent()}
	</a>
{:else if resourceType === 'reminder'}
	<a
		href={resolve('/reminders')}
		class="liquid-glass liquid-glass--frosted mt-1.5 flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200 hover:brightness-110 active:scale-[0.98]"
	>
		{@render resourceContent()}
	</a>
{:else if resourceType === 'project'}
	<a
		href={resolve('/projects/[id]', { id: resourceId })}
		class="liquid-glass liquid-glass--frosted mt-1.5 flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200 hover:brightness-110 active:scale-[0.98]"
	>
		{@render resourceContent()}
	</a>
{:else}
	<div
		class="liquid-glass liquid-glass--frosted mt-1.5 flex items-center gap-3 rounded-xl px-3 py-2.5"
	>
		{@render resourceContent()}
	</div>
{/if}
