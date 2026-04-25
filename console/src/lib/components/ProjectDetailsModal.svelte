<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type Project = Schemas['Project']

	import AccessRulesButton from '$lib/components/AccessRulesButton.svelte'
	import AclModal from '$lib/components/AclModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Textarea } from '$lib/components/ui/textarea'
	import {
		Calendar,
		Clock,
		FolderKanban,
		Hash,
		MessageSquare,
		Pencil,
		Save,
		Trash2,
		User,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		projectId: string | null
		onViewUser?: (userId: string) => void
		onUpdated?: (project: Project) => void
		onDeleted?: (projectId: string) => void
	}

	let { open = $bindable(false), projectId, onViewUser, onUpdated, onDeleted }: Props = $props()

	let project = $state<Project | null>(null)
	let isLoading = $state(false)
	let error = $state<string | null>(null)

	let isEditing = $state(false)
	let editName = $state('')
	let editDescription = $state('')
	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)
	let confirmDelete = $state(false)
	let showAclModal = $state(false)

	function close() {
		open = false
		isEditing = false
		confirmDelete = false
		saveError = null
		deleteError = null
	}

	function startEdit() {
		if (!project) return
		editName = project.name
		editDescription = project.description ?? ''
		isEditing = true
		saveError = null
	}

	function cancelEdit() {
		isEditing = false
		saveError = null
	}

	async function saveProject() {
		if (!project) return
		isSaving = true
		saveError = null
		try {
			const r = await api.PATCH('/v1/projects/{project_id}', {
				params: { path: { project_id: project.id } },
				body: {
					name: editName.trim(),
					description: editDescription.trim() || null,
				},
			})
			const updated = unwrap(r)
			project = updated
			isEditing = false
			onUpdated?.(updated)
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'failed to save'
		} finally {
			isSaving = false
		}
	}

	async function deleteProject() {
		if (!project) return
		isDeleting = true
		deleteError = null
		try {
			await api.DELETE('/v1/projects/{project_id}', {
				params: { path: { project_id: project.id } },
			})
			onDeleted?.(project.id)
			close()
		} catch (e) {
			deleteError = e instanceof Error ? e.message : 'failed to delete'
		} finally {
			isDeleting = false
		}
	}

	$effect(() => {
		if (!open || !projectId) {
			project = null
			return
		}
		isLoading = true
		error = null
		api.GET('/v1/projects/{project_id}', {
			params: { path: { project_id: projectId } },
		})
			.then((r) => {
				project = unwrap(r)
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load project'
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

<Dialog.Root
	bind:open
	onOpenChange={(v) => {
		if (!v) close()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col overflow-auto rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div class="min-w-0 flex-1">
					<Dialog.Title class="truncate text-base font-semibold">
						{project?.name ?? 'project'}
					</Dialog.Title>
					<Dialog.Description class="text-xs text-zinc-500"
						>project details</Dialog.Description
					>
				</div>
				<div class="flex shrink-0 items-center gap-1">
					{#if project && !isEditing}
						<AccessRulesButton
							variant="ghost"
							size="sm"
							class="h-7 rounded-lg px-2 text-xs text-zinc-400 hover:text-zinc-200"
							onclick={() => (showAclModal = true)}
						/>
						<Button
							variant="ghost"
							size="sm"
							class="h-7 rounded-lg px-2 text-xs text-zinc-400 hover:text-zinc-200"
							onclick={startEdit}
						>
							<Pencil class="mr-1 h-3 w-3" />
							edit
						</Button>
						{#if !confirmDelete}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-red-400 hover:text-red-300"
								onclick={() => (confirmDelete = true)}
							>
								<Trash2 class="mr-1 h-3 w-3" />
								delete
							</Button>
						{:else}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-red-400 hover:text-red-300"
								onclick={deleteProject}
								disabled={isDeleting}
							>
								{isDeleting ? 'deleting...' : 'confirm?'}
							</Button>
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-zinc-400"
								onclick={() => (confirmDelete = false)}
							>
								<X class="mr-1 h-3 w-3" />
								cancel
							</Button>
						{/if}
					{/if}
					<Button variant="ghost" size="icon" class="shrink-0 rounded-xl" onclick={close}>
						<X class="h-4 w-4" />
					</Button>
				</div>
			</div>

			{#if isLoading}
				<div class="flex items-center justify-center p-10">
					<div
						class="h-6 w-6 animate-spin rounded-full border-2 border-zinc-700 border-t-zinc-300"
					></div>
				</div>
			{:else if error}
				<div class="p-6 text-sm text-red-300">{error}</div>
			{:else if project}
				<div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-4">
					{#if deleteError}
						<div
							class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
						>
							{deleteError}
						</div>
					{/if}

					{#if isEditing}
						<div class="space-y-4">
							{#if saveError}
								<div
									class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
								>
									{saveError}
								</div>
							{/if}
							<div class="space-y-1.5">
								<Label for="edit-name" class="text-xs text-zinc-400">name</Label>
								<Input id="edit-name" bind:value={editName} class="rounded-xl" />
							</div>
							<div class="space-y-1.5">
								<Label for="edit-desc" class="text-xs text-zinc-400"
									>description</Label
								>
								<Textarea
									id="edit-desc"
									bind:value={editDescription}
									rows={3}
									class="rounded-xl"
								/>
							</div>
							<div class="flex justify-end gap-2">
								<Button
									variant="outline"
									size="sm"
									class="rounded-xl"
									onclick={cancelEdit}
								>
									cancel
								</Button>
								<Button
									size="sm"
									class="rounded-xl"
									onclick={saveProject}
									disabled={isSaving || !editName.trim()}
								>
									<Save class="mr-1.5 h-3.5 w-3.5" />
									{isSaving ? 'saving...' : 'save'}
								</Button>
							</div>
						</div>
					{:else}
						<!-- metadata -->
						<div class="space-y-1.5">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								identity
							</p>
							<div
								class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
							>
								<div class="flex items-center gap-3 px-4 py-2.5">
									<Hash class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="font-mono text-xs text-zinc-300">{project.id}</span
									>
								</div>
								<div class="flex items-center gap-3 px-4 py-2.5">
									<FolderKanban class="h-3.5 w-3.5 shrink-0 text-yellow-400" />
									<span class="text-sm text-zinc-100">{project.name}</span>
								</div>
								{#if project.description}
									<div class="px-4 py-2.5 text-sm text-zinc-300">
										{project.description}
									</div>
								{/if}
							</div>
						</div>

						<div class="space-y-1.5">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								owner
							</p>
							<div
								class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
							>
								<div class="flex items-center gap-3 px-4 py-2.5">
									<User class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<button
										type="button"
										class="text-sm underline underline-offset-4 hover:text-zinc-200"
										onclick={() => onViewUser?.(project!.owner_id)}
									>
										{project.owner_id}
									</button>
								</div>
							</div>
						</div>

						<!-- threads -->
						<div class="space-y-1.5">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								threads ({project.thread_ids?.length ?? 0})
							</p>
							{#if (project.thread_ids ?? []).length > 0}
								<div
									class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
								>
									{#each project.thread_ids ?? [] as tid (tid)}
										<div class="flex items-center gap-3 px-4 py-2.5">
											<MessageSquare
												class="h-3.5 w-3.5 shrink-0 text-emerald-400"
											/>
											<span class="font-mono text-xs text-zinc-300"
												>{tid}</span
											>
										</div>
									{/each}
								</div>
							{:else}
								<div
									class="rounded-xl border border-dashed border-zinc-800 py-4 text-center text-xs text-zinc-500"
								>
									no threads
								</div>
							{/if}
						</div>

						<!-- timestamps -->
						<div class="space-y-1.5">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								timestamps
							</p>
							<div
								class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
							>
								<div class="flex items-center gap-3 px-4 py-2.5">
									<Calendar class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="text-xs text-zinc-400">created</span>
									<span class="ml-auto font-mono text-xs text-zinc-300">
										{new Date(project.created_at).toLocaleString()}
									</span>
								</div>
								<div class="flex items-center gap-3 px-4 py-2.5">
									<Clock class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="text-xs text-zinc-400">updated</span>
									<span class="ml-auto font-mono text-xs text-zinc-300">
										{new Date(project.updated_at).toLocaleString()}
									</span>
								</div>
							</div>
						</div>
					{/if}
				</div>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

{#if project}
	<AclModal
		bind:open={showAclModal}
		resourceType="project"
		resourceId={project.id}
		title="project access rules"
	/>
{/if}
