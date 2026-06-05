<script lang="ts">
	import { resolve } from '$app/paths'
	import Label from '$lib/components/icons/Label.svelte'
	import User from '$lib/components/icons/User.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
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

	const labels = $derived((resource.meta?.labels as string[]) ?? [])
	const wordCount = $derived((resource.meta?.word_count as number) ?? 0)
	const sharing = resourceSharing(() => resource)
	const authorMeta = $derived(sharing.authorMeta)
	const strippedPreview = $derived(resource.preview ? stripMarkdown(resource.preview) : '')
	const noteVisual = resourceVisual('note')
	const NoteIcon = noteVisual.icon
	const noteAccentStyle = resourceAccentStyle('note')

	function stripMarkdown(text: string): string {
		return text
			.replace(/#{1,6}\s/g, '')
			.replace(/[*_~`]/g, '')
			.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
			.replace(/\n+/g, ' ')
			.trim()
	}

	function handleClick(event: MouseEvent): void {
		if (!onclick) return
		event.preventDefault()
		onclick()
	}
</script>

<a
	href={onclick ? undefined : resolve(`/notes/${resource.id}`)}
	onclick={handleClick}
	class="group liquid-glass liquid-glass--frosted block cursor-pointer overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview
			tone={noteVisual.tone}
			label={noteVisual.label}
			caption={wordCount > 0 ? `${wordCount} words` : 'text note'}
			showFallback={!strippedPreview}
			class="-mx-6 -mt-6"
		>
			{#snippet icon()}
				<NoteIcon variant="solid" class="size-6" />
			{/snippet}
			{#if strippedPreview}
				<div
					class="bg-background/80 text-foreground/72 flex h-full w-full items-start overflow-hidden p-4 text-left text-xs leading-5"
				>
					<p class="line-clamp-6">{strippedPreview}</p>
				</div>
			{/if}
		</ResourcePreview>
		<div class="mb-3 flex items-center gap-3">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
				style={noteAccentStyle}
			>
				<NoteIcon variant="solid" class="size-5" />
			</div>
			<div class="flex flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">note</span>
				{#if wordCount > 0}
					<span class="text-foreground/40 text-[11px]">{wordCount} words</span>
				{/if}
			</div>
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled note'}
		</h3>
		{#if !strippedPreview}
			<p class="text-foreground/40 mb-3 text-sm italic">empty note</p>
		{/if}
		<div class="mt-auto flex items-center gap-2">
			{#if authorMeta}
				<span class="text-foreground/50 flex min-w-0 items-center gap-1 text-xs">
					<User class="size-3.5 shrink-0" />
					<span class="truncate">{authorMeta}</span>
				</span>
			{/if}
			{#if labels.length > 0}
				<div class="flex items-center gap-1 overflow-hidden">
					<Label class="text-foreground/45 size-3.5 shrink-0" />
					{#each labels.slice(0, 3) as label (label)}
						<span
							class="bg-foreground/8 text-foreground/50 truncate rounded-full px-2 py-0.5 text-[11px] font-medium"
						>
							{label}
						</span>
					{/each}
				</div>
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
			style={noteAccentStyle}
		>
			<NoteIcon variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled note'}
			</h3>
			{#if authorMeta}
				<p class="text-foreground/65 flex min-w-0 items-center gap-1 text-sm">
					<User class="size-3.5 shrink-0" />
					<span class="truncate">{authorMeta}</span>
				</p>
			{:else if resource.preview}
				<p class="text-foreground/65 truncate text-sm">{stripMarkdown(resource.preview)}</p>
			{:else}
				<p class="text-foreground/45 truncate text-sm italic">empty note</p>
			{/if}
		</div>
		{#if labels.length > 0}
			<div class="flex shrink-0 gap-1">
				{#each labels.slice(0, 2) as label (label)}
					<span
						class="bg-foreground/8 text-foreground/50 rounded-full px-2 py-0.5 text-[11px]"
					>
						{label}
					</span>
				{/each}
			</div>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
</a>
