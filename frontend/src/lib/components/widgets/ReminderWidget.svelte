<script lang="ts">
	import { resolve } from '$app/paths'
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

	const status = $derived((resource.meta?.status as string | null) ?? null)
	const dueAt = $derived((resource.meta?.due_at as string | null) ?? null)
	const remindAt = $derived((resource.meta?.remind_at as string | null) ?? null)
	const parentListId = $derived(
		resource.parent?.type === 'reminder_list' ? resource.parent.id : null
	)
	const parentLabel = $derived((resource.meta?.parent_label as string | null) ?? null)
	const parentIcon = $derived((resource.meta?.parent_icon as string | null) ?? null)
	const parentColor = $derived((resource.meta?.parent_color as string | null) ?? null)
	const color = $derived((resource.meta?.color as string) ?? null)
	const icon = $derived((resource.meta?.icon as string) ?? null)
	const sharing = resourceSharing(() => resource)
	const authorMeta = $derived(sharing.authorMeta)
	const reminderVisual = resourceVisual('reminder')
	const ReminderIcon = reminderVisual.icon
	const reminderAccentStyle = $derived(
		color
			? `--resource-accent: ${color}; --accent-primary: ${color}`
			: resourceAccentStyle('reminder')
	)
	const scheduleMeta = $derived(
		status ??
			(dueAt
				? `due ${new Date(dueAt).toLocaleDateString()}`
				: remindAt
					? `reminds ${new Date(remindAt).toLocaleDateString()}`
					: 'reminder')
	)
	const subtitle = $derived(metadataLine(authorMeta, scheduleMeta))

	/** route clicks through caller override when supplied. */
	function handleClick(event: MouseEvent): void {
		if (!onclick) return
		event.preventDefault()
		onclick()
	}
</script>

<a
	href={onclick
		? undefined
		: parentListId
			? resolve('/reminders/lists/[listId]', { listId: parentListId })
			: undefined}
	onclick={handleClick}
	class="group liquid-glass liquid-glass--frosted block cursor-pointer overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview
			tone={reminderVisual.tone}
			label={reminderVisual.label}
			caption={status ?? 'reminder'}
			showFallback={true}
			class="-mx-6 -mt-6"
		>
			{#snippet icon()}
				{#if icon}
					<span class="text-2xl">{icon}</span>
				{:else}
					<ReminderIcon variant="solid" class="size-6" />
				{/if}
			{/snippet}
		</ResourcePreview>
		<div class="mb-3 flex items-center gap-3">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
				style={reminderAccentStyle}
			>
				{#if icon}
					<span class="text-lg">{icon}</span>
				{:else}
					<ReminderIcon variant="solid" class="size-5" />
				{/if}
			</div>
			<div class="flex min-w-0 flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">reminder</span>
				{#if subtitle}
					<span class="text-foreground/40 truncate text-[11px]">{subtitle}</span>
				{/if}
			</div>
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled reminder'}
		</h3>
		{#if resource.subtitle}
			<p class="text-foreground/70 mb-2 text-sm">{resource.subtitle}</p>
		{/if}
		{#if authorMeta}
			<p class="text-foreground/55 mb-2 flex min-w-0 items-center gap-1 text-sm">
				<User class="size-3.5 shrink-0" />
				<span class="truncate">{authorMeta}</span>
			</p>
		{/if}
		{#if dueAt || remindAt}
			<p class="text-foreground/50 mb-2 truncate text-sm">
				{dueAt
					? `due ${new Date(dueAt).toLocaleString()}`
					: `reminds ${new Date(remindAt ?? '').toLocaleString()}`}
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
			style={reminderAccentStyle}
		>
			{#if icon}
				<span class="text-lg">{icon}</span>
			{:else}
				<ReminderIcon variant="solid" class="size-5" />
			{/if}
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled reminder'}
			</h3>
			<p class="text-foreground/65 flex min-w-0 items-center gap-1.5 text-sm">
				{#if parentLabel}
					<span class="text-foreground/55 inline-flex min-w-0 shrink items-center gap-1">
						{#if parentIcon}
							<span class="shrink-0">{parentIcon}</span>
						{:else if parentColor}
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
					{authorMeta ? metadataLine(authorMeta, scheduleMeta) : scheduleMeta}
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
