<script lang="ts">
	import { resolve } from '$app/paths'
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
	}

	let { resource, layout = 'grid', class: className = '' }: Props = $props()

	const totalCount = $derived((resource.meta?.total_count as number) ?? 0)
	const pendingCount = $derived((resource.meta?.pending_count as number) ?? 0)
	const completedCount = $derived((resource.meta?.completed_count as number) ?? 0)
	const color = $derived((resource.meta?.color as string) ?? null)
	const icon = $derived((resource.meta?.icon as string) ?? null)
	const progress = $derived(totalCount > 0 ? (completedCount / totalCount) * 100 : 0)
</script>

<a
	href={resolve(`/reminders/lists/${resource.id}`)}
	class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<div class="mb-4 flex items-center gap-3">
			<div
				class="flex size-11 items-center justify-center rounded-xl text-sky-400"
				style:background-color={color ? `${color}20` : 'rgb(14 165 233 / 0.15)'}
				style:color={color ?? undefined}
			>
				{#if icon}
					<span class="text-lg">{icon}</span>
				{:else}
					<CheckBox variant="solid" class="size-5" />
				{/if}
			</div>
			<div class="flex flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">reminders</span>
				{#if totalCount > 0}
					<span class="text-foreground/40 text-[11px]"
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
			class="flex size-10 shrink-0 items-center justify-center rounded-xl text-sky-400"
			style:background-color={color ? `${color}20` : 'rgb(14 165 233 / 0.15)'}
			style:color={color ?? undefined}
		>
			{#if icon}
				<span class="text-lg">{icon}</span>
			{:else}
				<CheckBox variant="solid" class="size-5" />
			{/if}
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled list'}
			</h3>
			<p class="text-foreground/65 text-sm">
				{#if totalCount > 0}
					{pendingCount} pending - {completedCount}/{totalCount} done
				{:else}
					no reminders yet
				{/if}
			</p>
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
