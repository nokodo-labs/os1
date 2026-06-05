<script lang="ts">
	import { resolve } from '$app/paths'
	import Bell from '$lib/components/icons/Bell.svelte'
	import CalendarIcon from '$lib/components/icons/Calendar.svelte'
	import type { ToolExecution } from '$lib/tools'
	import {
		parseJsonRecord,
		readNonEmptyString,
		readRecordArray,
		readRecordField,
		readStringField,
	} from '$lib/utils/records'

	interface Props {
		execution: ToolExecution
	}

	type CalendarToolItem = {
		key: string
		type: 'calendar_event' | 'reminder'
		title: string
		subtitle: string | null
		href: '/calendar' | '/reminders'
	}

	let { execution }: Props = $props()

	function parseOutput(): Record<string, unknown> | null {
		if (!execution.result || execution.result.isError) return null
		return parseJsonRecord(execution.result.output)
	}

	function formatWhen(value: string | null): string | null {
		if (!value) return null
		const date = new Date(value)
		if (Number.isNaN(date.getTime())) return value
		return date.toLocaleString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		})
	}

	function calendarItem(record: Record<string, unknown>, index: number): CalendarToolItem {
		const rawType = readStringField(record, 'type')
		const type = rawType === 'reminder' ? 'reminder' : 'calendar_event'
		const id =
			type === 'reminder'
				? (readStringField(record, 'reminder_id') ??
					readStringField(record, 'parent_id') ??
					readStringField(record, 'id'))
				: (readStringField(record, 'calendar_event_id') ??
					readStringField(record, 'parent_id') ??
					readStringField(record, 'id'))
		const title =
			readNonEmptyString(record.title) ??
			readNonEmptyString(record.name) ??
			(type === 'reminder' ? 'reminder' : 'calendar event')
		const when =
			formatWhen(readStringField(record, 'effective_start_at')) ??
			formatWhen(readStringField(record, 'start_at')) ??
			formatWhen(readStringField(record, 'due_at'))
		const calendarName = readStringField(record, 'calendar_name')
		const subtitle = [when, calendarName].filter(Boolean).join(' - ') || null

		return {
			key: id ?? `${type}-${index}`,
			type,
			title,
			subtitle,
			href: type === 'reminder' ? '/reminders' : '/calendar',
		}
	}

	const parsedOutput = $derived(parseOutput())
	const items = $derived.by(() => {
		const results = readRecordArray(parsedOutput?.results)
		if (results.length > 0) return results.map(calendarItem)

		const event = readRecordField(parsedOutput, 'event')
		return event ? [calendarItem(event, 0)] : []
	})
</script>

{#if items.length > 0}
	<div class="liquid-glass liquid-glass--frosted mt-1.5 overflow-hidden rounded-xl">
		{#each items as item (item.key)}
			<a
				href={resolve(item.href)}
				class="hover:bg-foreground/8 flex items-center gap-3 px-3 py-2.5 transition-colors"
			>
				<div
					class="flex size-8 shrink-0 items-center justify-center rounded-lg {item.type ===
					'reminder'
						? 'bg-violet-500/15 text-violet-400'
						: 'bg-emerald-500/15 text-emerald-400'}"
				>
					{#if item.type === 'reminder'}
						<Bell class="size-4" />
					{:else}
						<CalendarIcon class="size-4" />
					{/if}
				</div>
				<div class="min-w-0 flex-1">
					<div class="text-foreground/80 truncate text-sm font-medium">{item.title}</div>
					{#if item.subtitle}
						<div class="text-foreground/45 truncate text-xs">{item.subtitle}</div>
					{/if}
				</div>
			</a>
		{/each}
	</div>
{/if}
