<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Info from '$lib/components/icons/Info.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import {
		resourceAccentStyle,
		resourceVisual,
		type ResourceVisualType,
	} from '$lib/resources/resourceVisuals'
	import { modals } from '$lib/stores/modals.svelte'
	import { projects, type Project } from '$lib/stores/projects.svelte'
	import { canEditAccessLevel, resourceAccess } from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { metadataLine } from '$lib/utils/resourceAuthors'

	interface Props {
		open: boolean
		project: Project | null
		onClose: () => void
	}

	let { open, project, onClose }: Props = $props()

	let name = $state('')
	let description = $state('')
	let saving = $state(false)

	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const fieldClass = `${panelClass} grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 rounded-[16px] border p-3`
	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6 disabled:cursor-not-allowed disabled:opacity-55'
	const iconClass = 'h-4 w-4 text-(--accent-primary)'
	const labelClass = 'text-foreground/60 text-[0.78rem] font-semibold'
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const previewTitle = $derived(name.trim() || project?.name || 'untitled project')
	const projectAccessLevel = $derived(
		project ? resourceAccess.level('project', project.id, project.owner_id) : null
	)
	const canEditProject = $derived(canEditAccessLevel(projectAccessLevel))
	const authorLabel = $derived(project ? session.authorLabel(project.owner_id) : null)
	const previewDescription = $derived(metadataLine(authorLabel, description.trim() || 'project'))
	const resourceCounts = $derived(project ? projects.resourceCounts(project.id) : null)
	const projectVisual = resourceVisual('project')
	const ProjectIcon = projectVisual.icon
	const projectAccentStyle = resourceAccentStyle('project')
	const countItems: {
		label: string
		value: number
		type: ResourceVisualType
	}[] = $derived([
		{ label: 'resources', value: resourceCounts?.resource_count ?? 0, type: 'project' },
		{
			label: resourceVisual('thread').pluralLabel,
			value: resourceCounts?.thread_count ?? 0,
			type: 'thread',
		},
		{
			label: resourceVisual('note').pluralLabel,
			value: resourceCounts?.note_count ?? 0,
			type: 'note',
		},
		{
			label: resourceVisual('file').pluralLabel,
			value: resourceCounts?.file_count ?? 0,
			type: 'file',
		},
		{
			label: resourceVisual('reminder_list').pluralLabel,
			value: resourceCounts?.reminder_list_count ?? 0,
			type: 'reminder_list',
		},
		{
			label: resourceVisual('calendar').pluralLabel,
			value: resourceCounts?.calendar_count ?? 0,
			type: 'calendar',
		},
	])

	$effect(() => {
		const accessKey = open && project ? `${project.id}:${resourceAccess.version}` : ''
		if (!open || !project) return
		if (open && project.owner_id !== session.currentUserId) {
			void session.ensureUsers([project.owner_id])
		}
		if (accessKey) void resourceAccess.ensure('project', project.id, project.owner_id)
		void projects.loadResourceCounts(project.id)
	})

	$effect(() => {
		if (open && project) {
			name = project.name
			description = project.description ?? ''
			saving = false
		}
	})

	async function save(): Promise<void> {
		if (!project) return
		if (saving || !canEditProject) return
		if (!name.trim()) return
		saving = true
		try {
			const saved = await projects.update(project.id, {
				name: name.trim(),
				description: description.trim() || undefined,
			})
			if (!saved) return
			onClose()
		} finally {
			saving = false
		}
	}

	function shareProject(): void {
		if (!project) return
		if (saving) return
		onClose()
		modals.open('resource-access', {
			resourceType: 'project',
			resourceId: project.id,
			title: project.name,
		})
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
			event.preventDefault()
			void save()
		}
	}

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault()
		void save()
	}
</script>

<BaseModal
	{open}
	title="project properties"
	onClose={() => !saving && onClose()}
	widthClassName="max-w-md"
>
	{#if project}
		<form class="grid gap-3" style={projectAccentStyle} onsubmit={handleSubmit}>
			<section class="{panelClass} flex min-w-0 items-center gap-4 rounded-[18px] border p-4">
				<div
					class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
				>
					<ProjectIcon variant="solid" class="h-5 w-5" />
				</div>
				<div class="min-w-0 flex-1">
					<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
						project
					</p>
					<h3 class="text-foreground min-w-0 truncate text-lg font-semibold">
						{previewTitle}
					</h3>
					<p class="text-foreground/55 mt-0.5 min-w-0 truncate text-xs">
						{previewDescription}
					</p>
				</div>
			</section>

			<div class={fieldClass}>
				<ProjectIcon variant="solid" class={iconClass} />
				<label class={labelClass} for="project-name">name</label>
				<input
					id="project-name"
					type="text"
					bind:value={name}
					class="{inputClass} col-span-full text-base"
					placeholder="project name"
					disabled={saving || !canEditProject}
					onkeydown={handleKeyDown}
				/>
			</div>
			<div class={fieldClass}>
				<Info class={iconClass} />
				<label class={labelClass} for="project-desc">description</label>
				<textarea
					id="project-desc"
					bind:value={description}
					class="{inputClass} col-span-full min-h-24 resize-y text-sm"
					placeholder="describe this project"
					disabled={saving || !canEditProject}
					onkeydown={handleKeyDown}
				></textarea>
			</div>
			<section class="{panelClass} rounded-2xl border p-3">
				<div class="mb-3 flex items-center gap-2">
					<Info class={iconClass} />
					<p class={labelClass}>resource counts</p>
				</div>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
					{#each countItems as item (item.label)}
						{@const visual = resourceVisual(item.type)}
						{@const Icon = visual.icon}
						<div
							class="rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_10%,transparent)] px-3 py-2"
							style={resourceAccentStyle(item.type)}
						>
							<div class="flex items-center gap-2 text-(--accent-primary)">
								<Icon variant="solid" class="size-4 shrink-0" />
								<div
									class="text-foreground/85 text-base font-semibold tabular-nums"
								>
									{item.value}
								</div>
							</div>
							<div
								class="text-foreground/50 mt-0.5 text-[11px] font-semibold uppercase"
							>
								{item.label}
							</div>
						</div>
					{/each}
				</div>
			</section>
			<div class="flex items-center gap-2 pt-1 max-[520px]:flex-wrap">
				{#if project}
					<button
						type="button"
						class="{actionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent"
						disabled={saving}
						onclick={shareProject}
					>
						<Share class="h-4 w-4" />
						<span>share</span>
					</button>
				{/if}
				<div class="flex-1"></div>
				{#if canEditProject}
					<button
						type="submit"
						class="{actionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]"
						disabled={saving || !name.trim()}
					>
						<Check class="h-4 w-4" />
						{#if saving}<ShimmerText className="inline-block">saving</ShimmerText
							>{:else}<span>save</span>{/if}
					</button>
				{/if}
			</div>
		</form>
	{/if}
</BaseModal>
