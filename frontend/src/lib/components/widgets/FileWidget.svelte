<script lang="ts">
	import Clip from '$lib/components/icons/Clip.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
	}

	let { resource, layout = 'grid', class: className = '' }: Props = $props()

	const fileType = $derived((resource.meta?.file_type as string) ?? 'file')
	const fileSize = $derived((resource.meta?.file_size as number) ?? 0)
	const uploadedBy = $derived((resource.meta?.uploaded_by as string) ?? '')

	function formatFileSize(bytes: number): string {
		if (bytes === 0) return ''
		if (bytes < 1024) return `${bytes} B`
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
	}
</script>

<a
	href={resource.href}
	class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<div class="mb-4 flex items-center gap-3">
			<div
				class="flex size-11 items-center justify-center rounded-xl bg-rose-500/15 text-rose-400"
			>
				<Clip class="size-5" />
			</div>
			<div class="flex flex-col">
				<span class="text-[13px] font-medium text-foreground/60">{fileType}</span>
				{#if fileSize}
					<span class="text-[11px] text-foreground/40">{formatFileSize(fileSize)}</span>
				{/if}
			</div>
		</div>
		<h3 class="mb-1.5 truncate text-xl font-semibold text-foreground">
			{resource.title || 'untitled file'}
		</h3>
		<div class="mt-auto flex items-center gap-2">
			{#if uploadedBy}
				<span class="text-xs text-foreground/50">by {uploadedBy}</span>
			{/if}
			<Timestamp
				timestamp={new Date(resource.updatedAt)}
				mode="relative"
				className="ml-auto shrink-0 text-xs text-foreground/45"
			/>
		</div>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-rose-500/15 text-rose-400"
		>
			<Clip class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="truncate text-base font-semibold text-foreground">
				{resource.title || 'untitled file'}
			</h3>
			<div class="flex items-center gap-2">
				{#if fileSize}
					<span class="text-sm text-foreground/60">{formatFileSize(fileSize)}</span>
				{/if}
				{#if uploadedBy}
					<span class="text-xs text-foreground/45">by {uploadedBy}</span>
				{/if}
			</div>
		</div>
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
</a>
