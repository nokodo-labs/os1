<script lang="ts">
	import { resolve } from '$app/paths'
	import CalendarIcon from '$lib/components/icons/Calendar.svelte'
	import User from '$lib/components/icons/User.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { metadataLine } from '$lib/utils/resourceAuthors'
	import ResourcePreview from './ResourcePreview.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
		onclick?: () => void
	}

	let { resource, layout = 'grid', class: className = '', onclick }: Props = $props()

	const calendarVisual = resourceVisual('calendar')
	const CalendarVisualIcon = calendarVisual.icon
	const color = $derived((resource.meta?.color as string | null) ?? null)
	const timezone = $derived((resource.meta?.timezone as string | null) ?? null)
	const isShared = $derived(Boolean(resource.meta?.shared))
	const authorLabel = $derived((resource.meta?.author_label as string | null) ?? null)
	const authorMeta = $derived(isShared ? authorLabel : null)
	const calendarAccentStyle = $derived(
		color
			? `--resource-accent: ${color}; --accent-primary: ${color}`
			: resourceAccentStyle('calendar')
	)
	const subtitle = $derived(metadataLine(authorMeta, timezone ?? resource.subtitle ?? 'calendar'))

	function handleClick(event: MouseEvent): void {
		if (!onclick) return
		event.preventDefault()
		onclick()
	}
</script>

<a
	href={resolve('/calendar')}
	onclick={handleClick}
	class="group liquid-glass liquid-glass--frosted block cursor-pointer overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview
			tone={calendarVisual.tone}
			label={calendarVisual.label}
			caption={timezone ?? 'schedule'}
			showFallback={true}
			class="-mx-6 -mt-6"
		>
			{#snippet icon()}
				<CalendarVisualIcon variant="solid" class="size-6" />
			{/snippet}
		</ResourcePreview>
		<div class="mb-3 flex items-center gap-3">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
				style={calendarAccentStyle}
			>
				<CalendarVisualIcon variant="solid" class="size-5" />
			</div>
			<div class="flex min-w-0 flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">calendar</span>
				{#if subtitle}
					<span class="text-foreground/40 truncate text-[11px]">{subtitle}</span>
				{/if}
			</div>
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled calendar'}
		</h3>
		{#if resource.subtitle}
			<p class="text-foreground/70 mb-2 line-clamp-2 text-sm">{resource.subtitle}</p>
		{/if}
		<div class="mt-auto flex min-w-0 items-center gap-2">
			{#if authorMeta}
				<span class="text-foreground/50 flex min-w-0 items-center gap-1 text-xs">
					<User class="size-3.5 shrink-0" />
					<span class="truncate">{authorMeta}</span>
				</span>
			{:else if color}
				<span class="text-foreground/50 flex min-w-0 items-center gap-1.5 text-xs">
					<span class="size-2.5 shrink-0 rounded-full" style:background-color={color}
					></span>
					<span>calendar color</span>
				</span>
			{/if}
			<Timestamp
				timestamp={new Date(resource.updatedAt)}
				mode="relative"
				className="ml-auto shrink-0 text-xs text-foreground/45"
			/>
		</div>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
			style={calendarAccentStyle}
		>
			<CalendarIcon variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled calendar'}
			</h3>
			<p class="text-foreground/65 truncate text-sm">{subtitle}</p>
		</div>
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
</a>
