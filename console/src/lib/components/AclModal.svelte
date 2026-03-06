<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type AccessLevel = Schemas['AccessLevel']
	type AccessRuleCreate = Schemas['AccessRuleCreate']
	type AccessRuleResponse = Schemas['AccessRuleResponse']

	import PrincipalPicker from '$lib/components/PrincipalPicker.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Label } from '$lib/components/ui/label'
	import { generateUUID } from '$lib/utils/crypto'
	import { Globe, Shield, Users, UsersRound } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type PrincipalType = 'user' | 'group' | 'role'

	let {
		open = $bindable(false),
		resourceType,
		resourceId,
		title = 'permissions',
	}: {
		open?: boolean
		resourceType: 'thread' | 'project' | 'agent'
		resourceId: string
		title?: string
	} = $props()

	let isLoading = $state(false)
	let isSaving = $state(false)
	let error = $state<string | null>(null)

	let entries = $state<AccessRuleResponse[]>([])
	let entryLabels = $state<Record<string, string>>({})

	let newLevel = $state<AccessLevel>('reader')

	function principalType(entry: AccessRuleResponse): PrincipalType | null {
		if (entry.subject_user_id) return 'user'
		if (entry.subject_group_id) return 'group'
		if (entry.subject_role_id) return 'role'
		return null
	}

	function principalId(entry: AccessRuleResponse): string | null {
		return entry.subject_user_id ?? entry.subject_group_id ?? entry.subject_role_id ?? null
	}

	function principalKey(entry: AccessRuleResponse): string {
		if (entry.subject_user_id) return `user:${entry.subject_user_id}`
		if (entry.subject_group_id) return `group:${entry.subject_group_id}`
		if (entry.subject_role_id) return `role:${entry.subject_role_id}`
		return 'unknown'
	}

	function principalDisplayLabel(entry: AccessRuleResponse): string {
		const key = principalKey(entry)
		return entryLabels[key] ?? key
	}

	const existingPrincipalIds = $derived(
		entries.map((e) => principalId(e)).filter((id): id is string => id !== null)
	)

	function toCreate(entry: AccessRuleResponse, index: number): AccessRuleCreate {
		return {
			level: entry.level,
			subject_user_id: entry.subject_user_id,
			subject_group_id: entry.subject_group_id,
			subject_role_id: entry.subject_role_id,
			order_index: index,
			metadata_: entry.metadata_,
		}
	}

	async function loadAcl() {
		isLoading = true
		error = null
		try {
			if (resourceType === 'thread') {
				entries = unwrap(
					await api.GET('/v1/threads/{thread_id}/access-rules', {
						params: { path: { thread_id: resourceId } },
					})
				)
			} else if (resourceType === 'project') {
				entries = unwrap(
					await api.GET('/v1/projects/{project_id}/access-rules', {
						params: { path: { project_id: resourceId } },
					})
				)
			} else {
				entries = unwrap(
					await api.GET('/v1/agents/{agent_id}/access-rules', {
						params: { path: { agent_id: resourceId } },
					})
				)
			}
		} catch (e: unknown) {
			console.error('Failed to load acl', e)
			error = e instanceof Error ? e.message : String(e)
		} finally {
			isLoading = false
		}
	}

	$effect(() => {
		if (!open) return
		if (!resourceId) return
		loadAcl()
	})

	function addEntry(principal: { type: PrincipalType; id: string; label: string }) {
		error = null

		const next: AccessRuleResponse = {
			id: `draft:${generateUUID()}`,
			thread_id: resourceType === 'thread' ? resourceId : null,
			project_id: resourceType === 'project' ? resourceId : null,
			agent_id: resourceType === 'agent' ? resourceId : null,
			subject_user_id: null,
			subject_group_id: null,
			subject_role_id: null,
			level: newLevel,
			order_index: entries.length,
			created_at: new Date().toISOString(),
			updated_at: new Date().toISOString(),
		}

		if (principal.type === 'user') next.subject_user_id = principal.id
		if (principal.type === 'group') next.subject_group_id = principal.id
		if (principal.type === 'role') next.subject_role_id = principal.id

		const key = principalKey(next)
		if (entries.some((e) => principalKey(e) === key)) {
			error = 'that principal already has an entry'
			return
		}

		entryLabels = { ...entryLabels, [key]: principal.label }
		entries = [...entries, next]
		newLevel = 'reader'
	}

	function removeEntry(id: string) {
		entries = entries.filter((e) => e.id !== id)
	}

	function updateLevel(id: string, level: AccessLevel) {
		entries = entries.map((e) => (e.id === id ? { ...e, level } : e))
	}

	function parseAccessLevel(value: string): AccessLevel | null {
		if (value === 'reader') return 'reader'
		if (value === 'editor') return 'editor'
		if (value === 'admin') return 'admin'
		return null
	}

	function readSelectValue(event: Event): string | null {
		const target = event.currentTarget
		if (target instanceof HTMLSelectElement) return target.value
		return null
	}

	async function save() {
		isSaving = true
		error = null
		try {
			const body = entries.map((entry, index) => toCreate(entry, index))
			if (resourceType === 'thread') {
				entries = unwrap(
					await api.PUT('/v1/threads/{thread_id}/access-rules', {
						params: { path: { thread_id: resourceId } },
						body,
					})
				)
			} else if (resourceType === 'project') {
				entries = unwrap(
					await api.PUT('/v1/projects/{project_id}/access-rules', {
						params: { path: { project_id: resourceId } },
						body,
					})
				)
			} else {
				entries = unwrap(
					await api.PUT('/v1/agents/{agent_id}/access-rules', {
						params: { path: { agent_id: resourceId } },
						body,
					})
				)
			}
			open = false
		} catch (e: unknown) {
			console.error('Failed to save acl', e)
			error = e instanceof Error ? e.message : String(e)
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
						<div class="mb-3 flex items-center justify-between">
							<div class="text-sm font-medium">add principal</div>
							<div class="flex items-center gap-2">
								<Label class="text-xs text-zinc-500">level:</Label>
								<select
									bind:value={newLevel}
									class="h-8 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs"
								>
									<option value="reader">reader</option>
									<option value="editor">editor</option>
									<option value="admin">admin</option>
								</select>
							</div>
						</div>
						<PrincipalPicker
							exclude={existingPrincipalIds}
							onPick={(p) => addEntry(p)}
						/>
					</div>

					<div class="rounded-xl border border-zinc-800 bg-zinc-900/40">
						<div class="border-b border-zinc-800 px-4 py-3 text-sm font-medium">
							entries ({entries.length})
						</div>
						{#if entries.length === 0}
							<div class="px-4 py-8 text-center text-sm text-zinc-500">
								no entries yet. pick a user, group, or role above to add one.
							</div>
						{:else}
							<div class="divide-y divide-zinc-800">
								{#each entries as entry (entry.id)}
									<div class="flex items-center gap-3 px-4 py-3">
										<div class="flex items-center gap-2 text-zinc-500">
											{#if principalType(entry) === 'user'}
												<Users class="h-3.5 w-3.5" />
											{:else if principalType(entry) === 'group'}
												<UsersRound class="h-3.5 w-3.5" />
											{:else if principalType(entry) === 'role'}
												<Shield class="h-3.5 w-3.5" />
											{:else}
												<Globe class="h-3.5 w-3.5" />
											{/if}
										</div>
										<div class="min-w-0 flex-1 text-sm">
											<div class="truncate font-medium text-zinc-200">
												{principalDisplayLabel(entry)}
											</div>
											<div class="truncate font-mono text-xs text-zinc-500">
												{principalKey(entry)}
											</div>
										</div>
										<div class="shrink-0">
											<select
												value={entry.level}
												onchange={(e) => {
													const nextValue = readSelectValue(e)
													if (!nextValue) return
													const nextLevel = parseAccessLevel(nextValue)
													if (!nextLevel) return
													updateLevel(entry.id, nextLevel)
												}}
												class="h-8 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs"
												disabled={isSaving}
											>
												<option value="reader">reader</option>
												<option value="editor">editor</option>
												<option value="admin">admin</option>
											</select>
										</div>
										<div class="shrink-0">
											<Button
												variant="outline"
												class="h-8 rounded-xl px-2 text-xs"
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
