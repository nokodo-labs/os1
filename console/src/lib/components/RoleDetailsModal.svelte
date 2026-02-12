<script lang="ts">
	import { browser } from '$app/environment'
	import {
		api,
		unwrap,
		type DefaultPermissions_Input,
		type DefaultPermissions_Output,
		type Role,
		type RoleUpdate,
		type User,
	} from '$lib/api'
	import DefaultPermissionsEditor from '$lib/components/DefaultPermissionsEditor.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Trash2, X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		roleId: string | null
		onUpdated?: () => void
		onDeleted?: () => void
		onClose?: () => void
	}

	let { open = $bindable(false), roleId, onUpdated, onDeleted, onClose }: Props = $props()

	let role = $state<Role | null>(null)
	let isLoading = $state(false)
	let isSaving = $state(false)
	let error = $state<string | null>(null)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	let name = $state('')
	let description = $state('')
	let defaultPermissions = $state<DefaultPermissions_Input>({
		resource_access: {},
		action_permissions: [],
	})

	// members management
	let members = $state<User[]>([])
	let isMembersLoading = $state(false)
	let membersError = $state<string | null>(null)
	let addUserEmail = $state('')
	let isAddingUser = $state(false)
	let addUserError = $state<string | null>(null)
	let allUsers = $state<User[]>([])
	let isUsersLoading = $state(false)

	function normalizePermissions(
		input: DefaultPermissions_Input | DefaultPermissions_Output
	): DefaultPermissions_Input {
		return {
			resource_access: {
				thread: input.resource_access?.thread ?? null,
				project: input.resource_access?.project ?? null,
				file: input.resource_access?.file ?? null,
				note: input.resource_access?.note ?? null,
				group: input.resource_access?.group ?? null,
				reminder_list: input.resource_access?.reminder_list ?? null,
			},
			action_permissions: [...(input.action_permissions ?? [])].sort(),
		}
	}

	function emptyPermissions(): DefaultPermissions_Input {
		return { resource_access: {}, action_permissions: [] }
	}

	function applyRole(r: Role) {
		name = r.name
		description = r.description ?? ''
		defaultPermissions = normalizePermissions(r.default_permissions ?? emptyPermissions())
		saveError = null
		saveSuccess = null
	}

	function close() {
		open = false
		onClose?.()
	}

	async function fetchMembers() {
		if (!roleId) return
		isMembersLoading = true
		membersError = null
		try {
			members = unwrap(
				await api.GET('/v1/roles/{role_id}/members', {
					params: { path: { role_id: roleId } },
				})
			)
		} catch (e) {
			membersError = e instanceof Error ? e.message : 'failed to load members'
		} finally {
			isMembersLoading = false
		}
	}

	async function fetchAllUsers() {
		isUsersLoading = true
		try {
			allUsers = unwrap(await api.GET('/v1/users', { params: { query: { limit: 200 } } }))
		} catch {
			allUsers = []
		} finally {
			isUsersLoading = false
		}
	}

	const availableUsers = $derived(allUsers.filter((u) => !members.some((m) => m.id === u.id)))

	const filteredUsers = $derived(
		addUserEmail.trim()
			? availableUsers.filter(
					(u) =>
						u.email.toLowerCase().includes(addUserEmail.toLowerCase()) ||
						(u.display_name ?? '').toLowerCase().includes(addUserEmail.toLowerCase())
				)
			: []
	)

	async function saveMemberList(nextIds: string[]) {
		if (!roleId) return
		isAddingUser = true
		addUserError = null
		try {
			members = unwrap(
				await api.PUT('/v1/roles/{role_id}/members', {
					params: { path: { role_id: roleId } },
					body: nextIds,
				})
			)
			addUserEmail = ''
		} catch (e) {
			addUserError = e instanceof Error ? e.message : 'failed to update members'
		} finally {
			isAddingUser = false
		}
	}

	function addMember(userId: string) {
		const nextIds = [...members.map((m) => m.id), userId]
		saveMemberList(nextIds)
	}

	function removeMember(userId: string) {
		const nextIds = members.filter((m) => m.id !== userId).map((m) => m.id)
		saveMemberList(nextIds)
	}

	function buildUpdatePayload(): RoleUpdate {
		return {
			name: name.trim() ? name.trim() : null,
			description: description.trim() ? description.trim() : null,
			default_permissions: normalizePermissions(defaultPermissions),
		}
	}

	async function saveRole() {
		if (!name.trim()) {
			saveError = 'name is required'
			return
		}
		if (!roleId) return

		isSaving = true
		saveError = null
		saveSuccess = null

		try {
			const updated = unwrap(
				await api.PATCH('/v1/roles/{role_id}', {
					params: { path: { role_id: roleId } },
					body: buildUpdatePayload(),
				})
			)
			saveSuccess = 'role updated'
			applyRole(updated)
			onUpdated?.()
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'failed to save role'
		} finally {
			isSaving = false
		}
	}

	async function deleteRole() {
		if (!roleId) return
		if (!confirm('delete this role?')) return

		isSaving = true
		saveError = null
		saveSuccess = null

		try {
			unwrap(
				await api.DELETE('/v1/roles/{role_id}', {
					params: { path: { role_id: roleId } },
				})
			)
			onDeleted?.()
			close()
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'failed to delete role'
		} finally {
			isSaving = false
		}
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!roleId) return

		isLoading = true
		error = null
		role = null
		saveError = null
		saveSuccess = null
		members = []
		addUserEmail = ''
		addUserError = null

		api.GET('/v1/roles/{role_id}', { params: { path: { role_id: roleId } } })
			.then((r) => unwrap(r))
			.then((r) => {
				role = r
				applyRole(r)
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load role'
			})
			.finally(() => {
				isLoading = false
			})

		fetchMembers()
		fetchAllUsers()
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
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[90vh] w-[min(768px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">role details</Dialog.Title>
					<p class="text-sm text-zinc-400">{roleId ?? ''}</p>
				</div>
				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8 rounded-lg"
					onclick={() => close()}
				>
					<X class="h-4 w-4" />
				</Button>
			</div>
			<div class="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-4">
				{#if isLoading}
					<div class="flex items-center justify-center py-10">
						<NokodoLoader />
					</div>
				{:else if error}
					<div
						class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				{:else if role}
					{#if saveError}
						<div
							class="rounded-lg border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200"
						>
							{saveError}
						</div>
					{/if}
					{#if saveSuccess}
						<div
							class="rounded-lg border border-emerald-900/40 bg-emerald-950/40 p-3 text-sm text-emerald-200"
						>
							{saveSuccess}
						</div>
					{/if}

					<div class="space-y-2">
						<Label for="role_name">name</Label>
						<Input
							id="role_name"
							bind:value={name}
							placeholder="role name"
							class="rounded-xl"
						/>
					</div>

					<div class="space-y-2">
						<Label for="role_description">description</Label>
						<textarea
							id="role_description"
							rows="3"
							class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600"
							placeholder="optional description"
							bind:value={description}
						></textarea>
					</div>

					<DefaultPermissionsEditor bind:value={defaultPermissions} />

					<!-- members section -->
					<div class="space-y-4">
						<div>
							<h3 class="text-sm font-semibold text-zinc-200">members</h3>
							<p class="text-sm text-zinc-500">users assigned to this role.</p>
						</div>

						{#if addUserError}
							<div
								class="rounded-lg border border-red-900/40 bg-red-950/40 p-2 text-xs text-red-200"
							>
								{addUserError}
							</div>
						{/if}

						<!-- add user search -->
						<div class="relative">
							<Input
								bind:value={addUserEmail}
								placeholder="search users by email or name..."
								class="rounded-xl"
								disabled={isAddingUser}
							/>
							{#if filteredUsers.length > 0}
								<div
									class="absolute top-full right-0 left-0 z-10 mt-1 max-h-48 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 shadow-lg"
								>
									{#each filteredUsers.slice(0, 8) as user (user.id)}
										<button
											class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-800"
											onclick={() => addMember(user.id)}
											disabled={isAddingUser}
										>
											<span class="truncate font-medium"
												>{user.display_name || user.email}</span
											>
											<span class="truncate text-xs text-zinc-500"
												>{user.email}</span
											>
										</button>
									{/each}
								</div>
							{/if}
						</div>

						<!-- current members -->
						{#if isMembersLoading}
							<div
								class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-6"
							>
								<NokodoLoader />
							</div>
						{:else if membersError}
							<div
								class="rounded-lg border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200"
							>
								{membersError}
							</div>
						{:else if members.length === 0}
							<div
								class="rounded-xl border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500"
							>
								no users assigned to this role
							</div>
						{:else}
							<div class="space-y-1">
								{#each members as member (member.id)}
									<div
										class="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
									>
										<div class="min-w-0">
											<div class="truncate text-sm text-zinc-200">
												{member.display_name || member.email}
											</div>
											<div class="truncate text-xs text-zinc-500">
												{member.email}
											</div>
										</div>
										<Button
											variant="ghost"
											class="h-7 w-7 shrink-0 rounded-lg p-0 text-zinc-500 hover:text-red-400"
											onclick={() => removeMember(member.id)}
											title="remove from role"
											aria-label="remove {member.email} from role"
										>
											<X class="h-3.5 w-3.5" />
										</Button>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
					>
						no role selected
					</div>
				{/if}
			</div>
			{#if role}
				<div class="flex shrink-0 justify-between gap-2 border-t border-zinc-800 px-6 py-4">
					<Button
						variant="outline"
						class="gap-2 rounded-xl text-red-400 hover:text-red-300"
						onclick={deleteRole}
						disabled={isSaving}
					>
						<Trash2 class="h-4 w-4" />
						delete
					</Button>
					<Button class="rounded-xl" onclick={saveRole} disabled={isSaving || isLoading}>
						{isSaving ? 'saving…' : 'save role'}
					</Button>
				</div>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
