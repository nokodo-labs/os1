<script lang="ts">
	import {
		ProjectsService,
		ThreadsService,
		type AccessControlEntry,
		type AccessControlEntryCreate,
	} from '$lib/api'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Dialog } from 'bits-ui'

	type PrincipalType = 'user' | 'group' | 'agent'
	type Role = AccessControlEntry['role']

	let {
		open = $bindable(false),
		resourceType,
		resourceId,
		title = 'permissions',
	}: {
		open?: boolean
		resourceType: 'thread' | 'project'
		resourceId: string
		title?: string
	} = $props()

	let isLoading = $state(false)
	let isSaving = $state(false)
	let error = $state<string | null>(null)

	let entries = $state<AccessControlEntry[]>([])

	let newPrincipalType = $state<PrincipalType>('user')
	let newPrincipalId = $state<string>('')
	let newRole = $state<Role>('viewer')

	function principalLabel(entry: AccessControlEntry) {
		if (entry.user_id) return `user:${entry.user_id}`
		if (entry.group_id) return `group:${entry.group_id}`
		if (entry.agent_id) return `agent:${entry.agent_id}`
		return 'unknown'
	}

	function toCreate(entry: AccessControlEntry): AccessControlEntryCreate {
		return {
			role: entry.role,
			user_id: entry.user_id,
			group_id: entry.group_id,
			agent_id: entry.agent_id,
			metadata_: entry.metadata_,
		}
	}

	async function loadAcl() {
		isLoading = true
		error = null
		try {
			entries =
				resourceType === 'thread'
					? await ThreadsService.listThreadAclThreadsThreadIdAclGet(resourceId)
					: await ProjectsService.listProjectAclProjectsProjectIdAclGet(resourceId)
		} catch (e: any) {
			console.error('Failed to load acl', e)
			error = e?.message || 'Failed to load permissions'
		} finally {
			isLoading = false
		}
	}

	$effect(() => {
		if (!open) return
		if (!resourceId) return
		loadAcl()
	})

	function addEntry() {
		error = null
		const principalId = newPrincipalId.trim()
		if (!principalId) {
			error = 'principal id is required'
			return
		}

		const next: AccessControlEntry = {
			id: `draft:${crypto.randomUUID()}`,
			thread_id: resourceType === 'thread' ? resourceId : null,
			project_id: resourceType === 'project' ? resourceId : null,
			user_id: null,
			group_id: null,
			agent_id: null,
			role: newRole,
			created_at: new Date().toISOString(),
			updated_at: new Date().toISOString(),
		}

		if (newPrincipalType === 'user') {
			next.user_id = principalId
		}
		if (newPrincipalType === 'group') next.group_id = principalId
		if (newPrincipalType === 'agent') next.agent_id = principalId

		const key = principalLabel(next)
		if (entries.some((e) => principalLabel(e) === key)) {
			error = 'that principal already has an entry'
			return
		}

		entries = [...entries, next]
		newPrincipalId = ''
		newRole = 'viewer'
	}

	function removeEntry(id: string) {
		entries = entries.filter((e) => e.id !== id)
	}

	function updateRole(id: string, role: Role) {
		entries = entries.map((e) => (e.id === id ? { ...e, role } : e))
	}

	async function save() {
		isSaving = true
		error = null
		try {
			entries =
				resourceType === 'thread'
					? await ThreadsService.setThreadAclThreadsThreadIdAclPut(
							resourceId,
							entries.map(toCreate)
						)
					: await ProjectsService.setProjectAclProjectsProjectIdAclPut(
							resourceId,
							entries.map(toCreate)
						)
			open = false
		} catch (e: any) {
			console.error('Failed to save acl', e)
			error = e?.message || 'Failed to save permissions'
		} finally {
			isSaving = false
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/50" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 w-[min(720px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-lg"
		>
			<div class="mb-6">
				<Dialog.Title class="text-lg font-semibold">{title}</Dialog.Title>
				<Dialog.Description class="text-sm text-zinc-400">
					manage who can access this {resourceType}.
				</Dialog.Description>
			</div>

			{#if error}
				<div
					class="mb-4 rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-sm text-red-400"
				>
					{error}
				</div>
			{/if}

			{#if isLoading}
				<div
					class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 text-sm text-zinc-400"
				>
					loading permissions...
				</div>
			{:else}
				<div class="space-y-4">
					<div class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
						<div class="mb-3 text-sm font-medium">add principal</div>
						<div class="grid gap-3 sm:grid-cols-3">
							<div class="space-y-2">
								<Label>type</Label>
								<select
									bind:value={newPrincipalType}
									class="h-10 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm"
								>
									<option value="user">user</option>
									<option value="group">group</option>
									<option value="agent">agent</option>
								</select>
							</div>
							<div class="space-y-2">
								<Label>id</Label>
								<Input
									bind:value={newPrincipalId}
									class="rounded-xl"
									placeholder="e.g. 123 or uuid"
								/>
							</div>
							<div class="space-y-2">
								<Label>role</Label>
								<select
									bind:value={newRole}
									class="h-10 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm"
								>
									<option value="viewer">viewer</option>
									<option value="editor">editor</option>
									<option value="admin">admin</option>
								</select>
							</div>
						</div>
						<div class="mt-3 flex justify-end">
							<Button class="rounded-xl" onclick={addEntry} disabled={isSaving}
								>add</Button
							>
						</div>
					</div>

					<div class="rounded-xl border border-zinc-800 bg-zinc-900/40">
						<div class="border-b border-zinc-800 px-4 py-3 text-sm font-medium">
							entries
						</div>
						{#if entries.length === 0}
							<div class="px-4 py-8 text-center text-sm text-zinc-500">
								no entries yet.
							</div>
						{:else}
							<div class="divide-y divide-zinc-800">
								{#each entries as entry (entry.id)}
									<div
										class="grid items-center gap-3 px-4 py-3 sm:grid-cols-[1fr,140px,80px]"
									>
										<div class="text-sm">
											<div class="font-mono text-xs text-zinc-400">
												{principalLabel(entry)}
											</div>
										</div>
										<div>
											<select
												value={entry.role}
												onchange={(e) =>
													updateRole(
														entry.id,
														(e.currentTarget as HTMLSelectElement)
															.value as Role
													)}
												class="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm"
												disabled={isSaving}
											>
												<option value="viewer">viewer</option>
												<option value="editor">editor</option>
												<option value="admin">admin</option>
											</select>
										</div>
										<div class="flex justify-end">
											<Button
												variant="outline"
												class="rounded-xl"
												onclick={() => removeEntry(entry.id)}
												disabled={isSaving}
											>
												remove
											</Button>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				</div>
			{/if}

			<div class="mt-6 flex justify-end gap-2">
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => (open = false)}
					disabled={isSaving}
				>
					cancel
				</Button>
				<Button class="rounded-xl" onclick={save} disabled={isSaving || isLoading}>
					{isSaving ? 'saving...' : 'save'}
				</Button>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
