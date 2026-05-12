<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import { MenuItem, SidePopupMenu } from '$lib/components/primitives'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { device } from '$lib/stores/device.svelte'

	export type ResourceProjectOption = {
		id: string
		name: string
		owner_id: string
	}

	interface Props {
		projectOptions?: ResourceProjectOption[]
		selectedProjectIds?: string[]
		onProjectToggle?: (projectId: string, selected: boolean) => Promise<void> | void
		label?: string
		emptyLabel?: string
	}

	let {
		projectOptions = [],
		selectedProjectIds = [],
		onProjectToggle,
		label = 'projects',
		emptyLabel = 'no projects',
	}: Props = $props()

	let projectsOpen = $state(false)
	let projectsButtonEl = $state<HTMLElement | null>(null)

	const selectedProjectSet = $derived(new Set(selectedProjectIds))
	const projectVisual = resourceVisual('project')
	const ProjectIcon = projectVisual.icon
	const projectAccentStyle = resourceAccentStyle('project')

	function toggleProject(projectId: string): void {
		if (!onProjectToggle) return
		const selected = !selectedProjectSet.has(projectId)
		void onProjectToggle(projectId, selected)
	}

	function openProjectsOnHover(): void {
		if (device.isTouch || !device.hasHover) return
		projectsOpen = true
	}
</script>

<div bind:this={projectsButtonEl} style={projectAccentStyle}>
	<MenuItem
		class={projectsOpen
			? 'bg-foreground/10 text-foreground shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]'
			: ''}
		onpointerenter={openProjectsOnHover}
		onclick={(event) => {
			event.stopPropagation()
			projectsOpen = !projectsOpen
		}}
	>
		{#snippet icon()}
			<ProjectIcon variant="solid" class="size-full text-(--accent-primary)" />
		{/snippet}
		{label}
		{#snippet trailing()}<ChevronRight class="text-foreground/45 size-4" />{/snippet}
	</MenuItem>
</div>

<SidePopupMenu
	open={projectsOpen}
	anchorEl={projectsButtonEl}
	onClose={() => (projectsOpen = false)}
	class="min-w-64"
>
	<div style={projectAccentStyle}>
		<div
			class="text-foreground/50 flex items-center gap-2 px-3 pt-1 pb-2 text-xs font-semibold tracking-[0.08em] uppercase"
		>
			<ProjectIcon variant="solid" class="size-4 text-(--accent-primary)" />
			{label}
		</div>
		{#if projectOptions.length === 0}
			<div
				data-empty-state
				data-empty-state-label={emptyLabel}
				class="text-foreground/45 px-3 py-2 text-sm font-semibold"
			>
				{emptyLabel}
			</div>
		{:else}
			{#each projectOptions as project (project.id)}
				<button
					type="button"
					class="rounded-pill text-foreground/85 hover:bg-foreground/10 flex w-full cursor-pointer items-center gap-3 border-none bg-transparent px-3 py-2.5 text-left text-sm font-semibold transition-colors duration-150"
					onclick={() => toggleProject(project.id)}
					aria-pressed={selectedProjectSet.has(project.id)}
				>
					<span
						class="border-foreground/18 flex size-6 shrink-0 items-center justify-center rounded-full border transition-colors {selectedProjectSet.has(
							project.id
						)
							? 'bg-(--accent-primary) text-white'
							: 'bg-foreground/6 text-transparent'}"
					>
						<Check class="size-3.5" />
					</span>
					<span class="min-w-0 flex-1 truncate">{project.name || 'untitled project'}</span
					>
				</button>
			{/each}
		{/if}
	</div>
</SidePopupMenu>
