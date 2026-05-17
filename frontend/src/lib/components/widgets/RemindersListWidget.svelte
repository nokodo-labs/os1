<script lang="ts">
	import { resolve } from '$app/paths'
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

	const totalCount = $derived((resource.meta?.total_count as number) ?? 0)
	const pendingCount = $derived((resource.meta?.pending_count as number) ?? 0)
	const completedCount = $derived((resource.meta?.completed_count as number) ?? 0)
	const color = $derived((resource.meta?.color as string) ?? null)
	const icon = $derived((resource.meta?.icon as string) ?? null)
	const isShared = $derived(Boolean(resource.meta?.shared))
	const authorLabel = $derived((resource.meta?.author_label as string | null) ?? null)
	const authorMeta = $derived(isShared ? authorLabel : null)
	const reminderVisual = resourceVisual('reminder_list')
	const ReminderIcon = reminderVisual.icon
	const listAccentStyle = $derived(
		color
			? `--resource-accent: ${color}; --accent-primary: ${color}`
			: resourceAccentStyle('reminder_list')
	)
	const statusMeta = $derived(
		totalCount > 0
			? `${pendingCount} pending · ${completedCount}/${totalCount} done`
			: 'no reminders yet'
	)
	const progress = $derived(totalCount > 0 ? (completedCount / totalCount) * 100 : 0)

	function handleClick(event: MouseEvent): void {
		if (!onclick) return
		event.preventDefault()
		onclick()
	}
</script>

<a
	href={resolve(`/reminders/lists/${resource.id}`)}
	onclick={handleClick}
	class="group liquid-glass liquid-glass--frosted block cursor-pointer overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview
			tone={reminderVisual.tone}
			label={reminderVisual.pluralLabel}
			caption={totalCount > 0 ? `${pendingCount} pending` : 'empty list'}
			showFallback={totalCount === 0}
			class="-mx-6 -mt-6"
		>
			{#snippet icon()}
				{#if icon}
					<span class="text-2xl">{icon}</span>
				{:else}
					<ReminderIcon variant="solid" class="size-6" />
				{/if}
			{/snippet}
			{#if totalCount > 0}
				<div class="flex h-full w-full flex-col justify-end p-4">
					<div class="bg-background/65 rounded-2xl p-3 backdrop-blur-sm">
						<div class="bg-foreground/10 h-2 w-full overflow-hidden rounded-full">
							<div
								class="h-full rounded-full transition-all duration-300"
								style:width="{progress}%"
								style:background-color={color ?? 'rgb(14 165 233)'}
							></div>
						</div>
						<div class="text-foreground/60 mt-2 flex justify-between text-xs">
							<span>{completedCount}/{totalCount} done</span>
							<span>{Math.round(progress)}%</span>
						</div>
					</div>
				</div>
			{/if}
		</ResourcePreview>
		<div class="mb-3 flex items-center gap-3">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
				style={listAccentStyle}
			>
				{#if icon}
					<span class="text-lg">{icon}</span>
				{:else}
					<ReminderIcon variant="solid" class="size-5" />
				{/if}
			</div>
			<div class="flex min-w-0 flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">reminders</span>
				{#if authorMeta}
					<span
						class="text-foreground/40 flex min-w-0 items-center gap-1 truncate text-[11px]"
					>
						<User class="size-3 shrink-0" />
						<span class="truncate">{authorMeta}</span>
					</span>
				{:else if totalCount > 0}
					<span class="text-foreground/40 truncate text-[11px]"
						>{completedCount}/{totalCount} done</span
					>
				{/if}
			</div>
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled list'}
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
		{#if totalCount > 0}
			<div class="mb-2 space-y-1.5">
				<div class="bg-foreground/8 h-2 w-full overflow-hidden rounded-full">
					<div
						class="h-full rounded-full transition-all duration-300"
						style:width="{progress}%"
						style:background-color={color ?? 'rgb(14 165 233)'}
					></div>
				</div>
				<div class="text-foreground/50 flex justify-between text-xs">
					<span>{pendingCount} pending</span>
					<span>{Math.round(progress)}%</span>
				</div>
			</div>
		{:else}
			<p class="text-foreground/40 mb-2 text-sm italic">no reminders yet</p>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="mt-auto text-xs text-foreground/45"
		/>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
			style={listAccentStyle}
		>
			{#if icon}
				<span class="text-lg">{icon}</span>
			{:else}
				<ReminderIcon variant="solid" class="size-5" />
			{/if}
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled list'}
			</h3>
			{#if authorMeta}
				<p class="text-foreground/65 flex min-w-0 items-center gap-1 text-sm">
					<User class="size-3.5 shrink-0" />
					<span class="truncate">{metadataLine(authorMeta, statusMeta)}</span>
				</p>
			{:else}
				<p class="text-foreground/65 truncate text-sm">{statusMeta}</p>
			{/if}
		</div>
		{#if totalCount > 0}
			<div class="flex w-20 shrink-0 items-center">
				<div class="bg-foreground/8 h-2 w-full overflow-hidden rounded-full">
					<div
						class="h-full rounded-full"
						style:width="{progress}%"
						style:background-color={color ?? 'rgb(14 165 233)'}
					></div>
				</div>
			</div>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
</a>
