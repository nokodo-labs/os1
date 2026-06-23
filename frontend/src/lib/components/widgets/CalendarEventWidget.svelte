<script lang="ts">
	import User from '$lib/components/icons/User.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { metadataLine } from '$lib/utils/resourceAuthors'
	import { resourceSharing } from '$lib/utils/resourceSharing.svelte'
	import ResourcePreview from './ResourcePreview.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
		onclick?: () => void
	}

	let { resource, layout = 'grid', class: className = '', onclick }: Props = $props()

	const eventVisual = resourceVisual('calendar_event')
	const EventIcon = eventVisual.icon
	const color = $derived((resource.meta?.color as string | null) ?? null)
	const parentLabel = $derived((resource.meta?.parent_label as string | null) ?? null)
	const parentColor = $derived((resource.meta?.parent_color as string | null) ?? null)
	const startAt = $derived((resource.meta?.start_at as string | null) ?? null)
	const endAt = $derived((resource.meta?.end_at as string | null) ?? null)
	const sharing = resourceSharing(() => resource)
	const authorMeta = $derived(sharing.authorMeta)
	const eventAccentStyle = $derived(
		color
			? `--resource-accent: ${color}; --accent-primary: ${color}`
			: resourceAccentStyle('calendar_event')
	)
	const timeMeta = $derived(
		startAt
			? endAt
				? `${new Date(startAt).toLocaleString()} - ${new Date(endAt).toLocaleString()}`
				: new Date(startAt).toLocaleString()
			: 'calendar event'
	)
	const subtitle = $derived(metadataLine(authorMeta, timeMeta))

	/** route clicks through caller override when supplied. */
	function handleClick(event: MouseEvent): void {
		if (!onclick) return
		event.preventDefault()
		onclick()
	}
</script>

<a
	href={undefined}
	onclick={handleClick}
	class="group liquid-glass liquid-glass--frosted block cursor-pointer overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview
			tone={eventVisual.tone}
			label={eventVisual.label}
			caption={timeMeta}
			showFallback={true}
			class="-mx-6 -mt-6"
		>
			{#snippet icon()}
				<EventIcon variant="solid" class="size-6" />
			{/snippet}
		</ResourcePreview>
		<div class="mb-3 flex items-center gap-3">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
				style={eventAccentStyle}
			>
				<EventIcon variant="solid" class="size-5" />
			</div>
			<div class="flex min-w-0 flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">calendar event</span>
				{#if subtitle}
					<span class="text-foreground/40 truncate text-[11px]">{subtitle}</span>
				{/if}
			</div>
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled event'}
		</h3>
		{#if resource.subtitle}
			<p class="text-foreground/70 mb-2 line-clamp-2 text-sm">{resource.subtitle}</p>
		{/if}
		{#if authorMeta}
			<p class="text-foreground/55 mb-2 flex min-w-0 items-center gap-1 text-sm">
				<User class="size-3.5 shrink-0" />
				<span class="truncate">{authorMeta}</span>
			</p>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="mt-auto text-xs text-foreground/45"
		/>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
			style={eventAccentStyle}
		>
			<EventIcon variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled event'}
			</h3>
			<p class="text-foreground/65 flex min-w-0 items-center gap-1.5 text-sm">
				{#if parentLabel}
					<span class="text-foreground/55 inline-flex min-w-0 shrink items-center gap-1">
						{#if parentColor}
							<span
								class="size-2 shrink-0 rounded-full"
								style="background-color: {parentColor}"
							></span>
						{/if}
						<span class="truncate">{parentLabel}</span>
					</span>
					<span class="text-foreground/30 shrink-0">&middot;</span>
				{/if}
				<span class="truncate">
					{authorMeta ? metadataLine(authorMeta, timeMeta) : timeMeta}
				</span>
			</p>
		</div>
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
</a>
