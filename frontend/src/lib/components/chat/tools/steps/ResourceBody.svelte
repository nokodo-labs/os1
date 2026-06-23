<script lang="ts">
	/** renders a clickable resource preview extracted from a tool result. */

	import { resolve } from '$app/paths'
	import Bell from '$lib/components/icons/Bell.svelte'
	import CalendarIcon from '$lib/components/icons/Calendar.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import MimeIcon from '$lib/components/icons/MimeIcon.svelte'
	import { files } from '$lib/stores/files.svelte'
	import type { ToolExecution } from '$lib/tools'
	import {
		parseJsonRecord,
		readNonEmptyString,
		readRecordField,
		readStringField,
	} from '$lib/utils/records'

	type ResourceType =
		| 'note'
		| 'reminder'
		| 'reminder_list'
		| 'file'
		| 'project'
		| 'chat'
		| 'calendar_event'

	interface Props {
		execution: ToolExecution
		resourceType: ResourceType
		resourceId: string
	}

	let { execution, resourceType, resourceId }: Props = $props()

	/** parses the tool result output as a structured resource payload. */
	function parseOutput(): Record<string, unknown> | null {
		if (!execution.result || execution.result.isError) return null
		return parseJsonRecord(execution.result.output)
	}

	const parsedOutput = $derived(parseOutput())
	const nestedResource = $derived.by(() => {
		switch (resourceType) {
			case 'reminder':
				return readRecordField(parsedOutput, 'reminder')
			case 'reminder_list':
				return readRecordField(parsedOutput, 'list')
			case 'calendar_event':
				return readRecordField(parsedOutput, 'event')
			case 'chat':
				return readRecordField(parsedOutput, 'chat')
			default:
				return parsedOutput
		}
	})

	// extract display info from result output
	const resultTitle = $derived.by(() => {
		const jsonTitle =
			readStringField(nestedResource, 'title') ??
			readStringField(nestedResource, 'name') ??
			readStringField(nestedResource, 'filename')
		if (jsonTitle) return jsonTitle
		if (!execution.result || execution.result.isError) return null
		const output = execution.result.output
		const titleLine = output.match(/^title:\s*(.+)/im)
		if (titleLine) return readNonEmptyString(titleLine[1])
		const filenameLine = output.match(/^filename:\s*(.+)/im)
		if (filenameLine) return readNonEmptyString(filenameLine[1])
		// "note created: [id] title" pattern
		const actionMatch = output.match(/\[[^\]]+\]\s*(.+)/)
		if (actionMatch) return readNonEmptyString(actionMatch[1])
		return null
	})

	const displayTitle = $derived(
		resultTitle ?? readNonEmptyString(execution.toolCall.arguments.title) ?? resourceId
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
			case 'chat':
				return 'bg-sky-500/15 text-sky-400'
			case 'note':
				return 'bg-amber-500/15 text-amber-400'
			case 'reminder':
			case 'reminder_list':
				return 'bg-violet-500/15 text-violet-400'
			case 'calendar_event':
				return 'bg-emerald-500/15 text-emerald-400'
			case 'project':
				return 'bg-yellow-500/15 text-yellow-400'
			case 'file':
				return 'bg-rose-500/15 text-rose-400'
		}
	})

	const mimeType = $derived(fileRecord?.mime_type ?? null)
	const reminderListId = $derived(
		resourceType === 'reminder' ? readStringField(nestedResource, 'list_id') : null
	)
	const linkClass =
		'liquid-glass liquid-glass--frosted mt-1.5 flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200 hover:brightness-110 active:scale-[0.98]'
	const frameClass =
		'liquid-glass liquid-glass--frosted mt-1.5 flex items-center gap-3 rounded-xl px-3 py-2.5'
</script>

{#snippet resourceContent()}
	<div class="flex size-8 shrink-0 items-center justify-center rounded-lg {iconColor}">
		{#if resourceType === 'file'}
			<MimeIcon {mimeType} class="size-4" />
		{:else if resourceType === 'chat'}
			<ChatBubble class="size-4" />
		{:else if resourceType === 'note'}
			<Document class="size-4" />
		{:else if resourceType === 'project'}
			<FinderFolder class="size-4" />
		{:else if resourceType === 'calendar_event'}
			<CalendarIcon class="size-4" />
		{:else}
			<Bell class="size-4" />
		{/if}
	</div>
	<span class="text-foreground/80 min-w-0 flex-1 truncate text-sm font-medium">
		{resourceType === 'file' ? (fileRecord?.filename ?? displayTitle) : displayTitle}
	</span>
{/snippet}

{#if resourceType === 'chat'}
	<a href={resolve('/c/[id]', { id: resourceId })} class={linkClass}>
		{@render resourceContent()}
	</a>
{:else if resourceType === 'note'}
	<a href={resolve('/notes/[id]', { id: resourceId })} class={linkClass}>
		{@render resourceContent()}
	</a>
{:else if resourceType === 'reminder_list'}
	<a href={resolve('/reminders/lists/[listId]', { listId: resourceId })} class={linkClass}>
		{@render resourceContent()}
	</a>
{:else if resourceType === 'reminder' && reminderListId}
	<a href={resolve('/reminders/lists/[listId]', { listId: reminderListId })} class={linkClass}>
		{@render resourceContent()}
	</a>
{:else if resourceType === 'project'}
	<a href={resolve('/projects/[id]', { id: resourceId })} class={linkClass}>
		{@render resourceContent()}
	</a>
{:else}
	<div class={frameClass}>
		{@render resourceContent()}
	</div>
{/if}
