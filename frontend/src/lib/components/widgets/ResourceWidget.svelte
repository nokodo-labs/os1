<script lang="ts">
	import CalendarWidget from '$lib/components/widgets/CalendarWidget.svelte'
	import CalendarEventWidget from '$lib/components/widgets/CalendarEventWidget.svelte'
	import ChatWidget from '$lib/components/widgets/ChatWidget.svelte'
	import FileWidget from '$lib/components/widgets/FileWidget.svelte'
	import NoteWidget from '$lib/components/widgets/NoteWidget.svelte'
	import ProjectWidget from '$lib/components/widgets/ProjectWidget.svelte'
	import ReminderWidget from '$lib/components/widgets/ReminderWidget.svelte'
	import RemindersListWidget from '$lib/components/widgets/RemindersListWidget.svelte'
	import type { ResourceItem, ResourceLayoutMode } from '$lib/components/widgets/types'

	type ResourceWidgetLayout = ResourceLayoutMode | 'pill' | 'bare'

	interface Props {
		resource: ResourceItem
		layout?: ResourceWidgetLayout
		class?: string
		onclick?: () => void
	}

	let { resource, layout = 'grid', class: className = '', onclick }: Props = $props()
	const widgetLayout = $derived<ResourceLayoutMode>(layout === 'grid' ? 'grid' : 'list')
	const widgetClass = $derived(
		layout === 'pill'
			? `resource-pill-row ${className}`.trim()
			: layout === 'bare'
				? `resource-bare-row ${className}`.trim()
				: className
	)
</script>

{#if resource.type === 'thread'}
	<ChatWidget {resource} layout={widgetLayout} class={widgetClass} {onclick} />
{:else if resource.type === 'note'}
	<NoteWidget {resource} layout={widgetLayout} class={widgetClass} {onclick} />
{:else if resource.type === 'reminder'}
	<ReminderWidget {resource} layout={widgetLayout} class={widgetClass} {onclick} />
{:else if resource.type === 'reminder_list'}
	<RemindersListWidget {resource} layout={widgetLayout} class={widgetClass} {onclick} />
{:else if resource.type === 'project'}
	<ProjectWidget {resource} layout={widgetLayout} class={widgetClass} {onclick} />
{:else if resource.type === 'file'}
	<FileWidget {resource} layout={widgetLayout} class={widgetClass} {onclick} />
{:else if resource.type === 'calendar_event'}
	<CalendarEventWidget {resource} layout={widgetLayout} class={widgetClass} {onclick} />
{:else if resource.type === 'calendar'}
	<CalendarWidget {resource} layout={widgetLayout} class={widgetClass} {onclick} />
{/if}

<style>
	:global(.resource-pill-row) {
		border-radius: 9999px;
		overflow: hidden;
		isolation: isolate;
		clip-path: inset(0 round 9999px);
	}

	:global(.resource-pill-row.rounded-2xl) {
		border-radius: 9999px;
	}

	@media (max-width: 420px) {
		:global(.resource-pill-row) {
			gap: 0.75rem;
			padding-left: 0.875rem;
			padding-right: 0.875rem;
		}

		:global(.resource-pill-row > time),
		:global(.resource-pill-row > span.shrink-0) {
			display: none;
		}
	}

	:global(.resource-bare-row.liquid-glass) {
		--lg-bg: transparent;
		--lg-blur: 0px;
		--lg-border: transparent;
		background: transparent;
		box-shadow: none;
		backdrop-filter: none;
		-webkit-backdrop-filter: none;
		border-radius: 0;
	}

	:global(.resource-bare-row.liquid-glass::before),
	:global(.resource-bare-row.liquid-glass::after) {
		display: none;
	}
</style>
