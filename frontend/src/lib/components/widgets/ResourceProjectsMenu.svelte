<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import { MenuItem, MenuSectionHeader, SidePopupMenu } from '$lib/components/primitives'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'

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
</script>

<div bind:this={projectsButtonEl} style={projectAccentStyle}>
	<MenuItem
		submenuOpen={projectsOpen}
		onclick={(event) => {
			event.stopPropagation()
			projectsOpen = !projectsOpen
		}}
	>
		{#snippet iconSnippet()}
			<ProjectIcon class="size-full text-(--accent-primary)" />
		{/snippet}
		{label}
	</MenuItem>
</div>

<SidePopupMenu
	open={projectsOpen}
	anchorEl={projectsButtonEl}
	openOnHover
	onOpen={() => (projectsOpen = true)}
	onClose={() => (projectsOpen = false)}
	class="min-w-64"
>
	<div class="flex min-w-0 flex-col" style={projectAccentStyle}>
		<MenuSectionHeader icon={ProjectIcon}>{label}</MenuSectionHeader>
		{#if projectOptions.length === 0}
			<EmptyState label={emptyLabel} compact />
		{:else}
			{#each projectOptions as project (project.id)}
				<MenuItem
					onclick={() => toggleProject(project.id)}
					aria-pressed={selectedProjectSet.has(project.id)}
				>
					{#snippet iconSnippet()}
						<span
							class="border-foreground/18 flex items-center justify-center rounded-full border transition-colors {selectedProjectSet.has(
								project.id
							)
								? 'bg-(--accent-primary) text-white'
								: 'bg-foreground/6 text-transparent'}"
						>
							<Check class="size-3.5" />
						</span>
					{/snippet}
					{project.name || 'untitled project'}
				</MenuItem>
			{/each}
		{/if}
	</div>
</SidePopupMenu>
