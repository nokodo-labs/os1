<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type Group = Schemas['Group']
	type GroupMemberRole = Schemas['GroupMemberRole']
	type UserRecord = Schemas['User']

	import AccessRulesButton from '$lib/components/AccessRulesButton.svelte'
	import AclModal from '$lib/components/AclModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import UserDetailsModal from '$lib/components/UserDetailsModal.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Textarea } from '$lib/components/ui/textarea'
	import {
		Calendar,
		Hash,
		Pencil,
		Plus,
		Save,
		Search,
		Trash2,
		User,
		Users,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		groupId: string | null
		onDeleted?: (groupId: string) => void
		onUpdated?: (group: Group) => void
	}

	let { open = $bindable(false), groupId, onDeleted, onUpdated }: Props = $props()

	let group = $state<Group | null>(null)
	let isLoading = $state(false)
	let loadError = $state<string | null>(null)

	// edit fields
	let editName = $state('')
	let editDescription = $state('')
	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state(false)

	// user search for adding members
	const USER_SEARCH_LIMIT = 20
	let userResults = $state<UserRecord[]>([])
	let userQuery = $state('')
	let isLoadingUsers = $state(false)
	let userSearchSkip = $state(0)
	let hasMoreUserResults = $state(false)
	let userSearchRequestId = 0
	let userSearchTimer: ReturnType<typeof setTimeout> | null = null

	let availableUserResults = $derived(
		userResults.filter((u: UserRecord) => !group?.memberships.some((m) => m.user_id === u.id))
	)

	// add member
	let newMemberRole = $state<GroupMemberRole>('member')
	let isAddingMember = $state(false)
	let addMemberError = $state<string | null>(null)

	// remove member
	let removingMemberId = $state<string | null>(null)
	let removeMemberError = $state<string | null>(null)

	// update member role
	let updatingMemberRoleId = $state<string | null>(null)
	let updateMemberRoleError = $state<string | null>(null)

	// delete
	let confirmDelete = $state(false)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)

	// user modal
	let isUserModalOpen = $state(false)
	let selectedUserId = $state<string | null>(null)
	let showAclModal = $state(false)

	function openUser(userId: string) {
		selectedUserId = userId
		isUserModalOpen = true
	}

	function close() {
		open = false
		group = null
		confirmDelete = false
		saveError = null
		addMemberError = null
		removeMemberError = null
		updateMemberRoleError = null
		deleteError = null
		saveSuccess = false
		userQuery = ''
		userResults = []
		userSearchSkip = 0
		hasMoreUserResults = false
	}

	function errMsg(e: unknown): string {
		return e instanceof Error ? e.message : String(e)
	}

	async function searchUsers(reset = false) {
		const q = userQuery.trim()
		if (!q) {
			userResults = []
			userSearchSkip = 0
			hasMoreUserResults = false
			return
		}
		isLoadingUsers = true
		const requestId = ++userSearchRequestId
		const skip = reset ? 0 : userSearchSkip
		try {
			const r = await api.GET('/v1/users', {
				params: {
					query: {
						q,
						limit: USER_SEARCH_LIMIT,
						skip,
						sort_by: 'display_name',
						sort_dir: 'asc',
					},
				},
			})
			const result = unwrap(r)
			if (requestId !== userSearchRequestId) return
			userResults = reset ? result : [...userResults, ...result]
			userSearchSkip = skip + result.length
			hasMoreUserResults = result.length === USER_SEARCH_LIMIT
		} catch {
			if (requestId === userSearchRequestId) {
				userResults = reset ? [] : userResults
				hasMoreUserResults = false
			}
		} finally {
			if (requestId === userSearchRequestId) isLoadingUsers = false
		}
	}

	function scheduleUserSearch() {
		if (userSearchTimer) clearTimeout(userSearchTimer)
		userSearchTimer = setTimeout(() => {
			void searchUsers(true)
		}, 250)
	}

	function handleUserSearchScroll(event: Event) {
		if (!(event.currentTarget instanceof HTMLElement)) return
		const target = event.currentTarget
		if (target.scrollTop + target.clientHeight < target.scrollHeight - 24) return
		if (!hasMoreUserResults || isLoadingUsers) return
		void searchUsers(false)
	}

	$effect(() => {
		if (!open || !groupId) return
		isLoading = true
		loadError = null
		group = null
		api.GET('/v1/groups/{group_id}', { params: { path: { group_id: groupId } } })
			.then((r) => unwrap(r))
			.then((g) => {
				group = g
				editName = g.name
				editDescription = g.description ?? ''
			})
			.catch((e: unknown) => {
				loadError = errMsg(e)
			})
			.finally(() => {
				isLoading = false
			})
	})

	async function save() {
		if (!group) return
		isSaving = true
		saveError = null
		saveSuccess = false
		try {
			const r = await api.PATCH('/v1/groups/{group_id}', {
				params: { path: { group_id: group.id } },
				body: {
					name: editName.trim() || undefined,
					description: editDescription.trim() || null,
				},
			})
			const updated = unwrap(r)
			group = updated
			editName = updated.name
			editDescription = updated.description ?? ''
			onUpdated?.(updated)
			saveSuccess = true
			setTimeout(() => (saveSuccess = false), 2000)
		} catch (e) {
			saveError = errMsg(e)
		} finally {
			isSaving = false
		}
	}

	async function addMember(userId: string) {
		if (!group) return
		isAddingMember = true
		addMemberError = null
		try {
			await api.POST('/v1/groups/{group_id}/members', {
				params: { path: { group_id: group.id } },
				body: { user_id: userId, role: newMemberRole },
			})
			// reload group
			const r = await api.GET('/v1/groups/{group_id}', {
				params: { path: { group_id: group.id } },
			})
			group = unwrap(r)
			userQuery = ''
			userResults = []
			userSearchSkip = 0
			hasMoreUserResults = false
			newMemberRole = 'member'
		} catch (e) {
			addMemberError = errMsg(e)
		} finally {
			isAddingMember = false
		}
	}

	async function removeMember(userId: string) {
		if (!group) return
		removingMemberId = userId
		removeMemberError = null
		try {
			await api.DELETE('/v1/groups/{group_id}/members/{user_id}', {
				params: { path: { group_id: group.id, user_id: userId } },
			})
			group = { ...group, memberships: group.memberships.filter((m) => m.user_id !== userId) }
		} catch (e) {
			removeMemberError = errMsg(e)
		} finally {
			removingMemberId = null
		}
	}

	async function updateMemberRole(userId: string, newRole: GroupMemberRole) {
		if (!group) return
		updatingMemberRoleId = userId
		updateMemberRoleError = null
		try {
			// no PATCH endpoint - remove then re-add with new role
			await api.DELETE('/v1/groups/{group_id}/members/{user_id}', {
				params: { path: { group_id: group.id, user_id: userId } },
			})
			await api.POST('/v1/groups/{group_id}/members', {
				params: { path: { group_id: group.id } },
				body: { user_id: userId, role: newRole },
			})
			const r = await api.GET('/v1/groups/{group_id}', {
				params: { path: { group_id: group.id } },
			})
			group = unwrap(r)
		} catch (e) {
			updateMemberRoleError = errMsg(e)
		} finally {
			updatingMemberRoleId = null
		}
	}

	async function deleteGroup() {
		if (!group) return
		isDeleting = true
		deleteError = null
		try {
			await api.DELETE('/v1/groups/{group_id}', {
				params: { path: { group_id: group.id } },
			})
			onDeleted?.(group.id)
			close()
		} catch (e) {
			deleteError = errMsg(e)
		} finally {
			isDeleting = false
		}
	}

	const roleColors: Record<GroupMemberRole, string> = {
		owner: 'text-amber-400',
		admin: 'text-sky-400',
		member: 'text-zinc-400',
	}
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
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2rem)] min-w-80 -translate-x-1/2 -translate-y-1/2 flex-col overflow-auto rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-xl"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div class="flex min-w-0 flex-1 items-center gap-3">
					<div
						class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-zinc-800"
					>
						<Users class="h-4 w-4 text-zinc-400" />
					</div>
					<div class="min-w-0">
						<Dialog.Title class="truncate text-base font-semibold">
							{group?.name ?? 'group details'}
						</Dialog.Title>
						<Dialog.Description class="text-xs text-zinc-500"
							>group management</Dialog.Description
						>
					</div>
				</div>
				<div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
					{#if groupId}
						<AccessRulesButton
							type="button"
							variant="outline"
							size="sm"
							onclick={() => (showAclModal = true)}
						/>
					{/if}
					<Button variant="ghost" size="icon" class="shrink-0 rounded-xl" onclick={close}>
						<X class="h-4 w-4" />
					</Button>
				</div>
			</div>

			<div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-5">
				{#if isLoading}
					<div class="flex items-center justify-center py-12">
						<NokodoLoader />
					</div>
				{:else if loadError}
					<div
						class="rounded-xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{loadError}
					</div>
				{:else if group}
					<!-- identity -->
					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							identity
						</p>
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<Hash class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">id</span>
								<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
									>{group.id}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<User class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">owner</span>
								<button
									type="button"
									class="min-w-0 truncate font-mono text-xs text-zinc-300 underline underline-offset-4 hover:text-zinc-100"
									onclick={() => openUser(group!.owner_id)}
								>
									{group.owner_id}
								</button>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<Calendar class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">created</span>
								<span class="text-xs text-zinc-300"
									>{new Date(group.created_at).toLocaleString()}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5 text-sm">
								<Pencil class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">updated</span>
								<span class="text-xs text-zinc-300"
									>{new Date(group.updated_at).toLocaleString()}</span
								>
							</div>
						</div>
					</div>

					<!-- edit fields -->
					<div class="space-y-3">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							details
						</p>
						<div class="space-y-2">
							<Label class="text-xs text-zinc-400">name</Label>
							<Input
								bind:value={editName}
								placeholder="group name"
								class="rounded-xl border-zinc-700 bg-zinc-900 text-zinc-100 placeholder-zinc-600"
							/>
						</div>
						<div class="space-y-2">
							<Label class="text-xs text-zinc-400">description</Label>
							<Textarea
								bind:value={editDescription}
								placeholder="group description (optional)"
								rows={2}
								class="rounded-xl border-zinc-700 bg-zinc-900 text-zinc-100 placeholder-zinc-600"
							/>
						</div>
						{#if saveError}
							<div
								class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
							>
								{saveError}
							</div>
						{/if}
						{#if saveSuccess}
							<div
								class="rounded-lg border border-emerald-900/50 bg-emerald-900/10 px-3 py-2 text-xs text-emerald-300"
							>
								saved
							</div>
						{/if}
						<Button
							variant="outline"
							size="sm"
							class="rounded-xl"
							onclick={save}
							disabled={isSaving}
						>
							<Save class="mr-1.5 h-3.5 w-3.5" />
							{isSaving ? 'saving…' : 'save changes'}
						</Button>
					</div>

					<!-- members -->
					<div class="space-y-3">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							members
							<span
								class="ml-1 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-normal text-zinc-400 normal-case"
							>
								{group.memberships.length}
							</span>
						</p>
						{#if removeMemberError}
							<div
								class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
							>
								{removeMemberError}
							</div>
						{/if}
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							{#if group.memberships.length === 0}
								<div class="px-4 py-4 text-center text-sm text-zinc-500">
									no members yet
								</div>
							{:else}
								{#each group.memberships as m (m.user_id)}
									<div class="flex items-center gap-3 px-4 py-2.5">
										<User class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
										<button
											type="button"
											class="min-w-0 flex-1 truncate text-left font-mono text-xs text-zinc-300 underline underline-offset-4 hover:text-zinc-100"
											onclick={() => openUser(m.user_id)}
										>
											{m.user_id}
										</button>
										<Select
											value={m.role}
											onValueChange={(v: string) =>
												updateMemberRole(m.user_id, v as GroupMemberRole)}
											disabled={updatingMemberRoleId === m.user_id}
										>
											<SelectTrigger
												class="h-6 w-24 rounded-lg border-zinc-700 bg-zinc-800 px-2 text-xs capitalize {roleColors[
													m.role
												] ?? 'text-zinc-400'}"
											>
												{#if updatingMemberRoleId === m.user_id}
													<span class="text-zinc-500">…</span>
												{:else}
													<span class="capitalize">{m.role}</span>
												{/if}
											</SelectTrigger>
											<SelectContent>
												<SelectItem value="member">member</SelectItem>
												<SelectItem value="admin">admin</SelectItem>
												<SelectItem value="owner">owner</SelectItem>
											</SelectContent>
										</Select>
										<Button
											variant="ghost"
											size="icon"
											class="h-6 w-6 rounded-lg text-zinc-600 hover:text-red-400"
											disabled={removingMemberId === m.user_id}
											onclick={() => removeMember(m.user_id)}
											title="remove member"
										>
											<X class="h-3.5 w-3.5" />
										</Button>
									</div>
								{/each}
							{/if}
						</div>

						<!-- add member -->
						<div class="space-y-2">
							<p class="text-xs text-zinc-500">add member</p>
							{#if addMemberError}
								<div
									class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
								>
									{addMemberError}
								</div>
							{/if}
							{#if updateMemberRoleError}
								<div
									class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
								>
									{updateMemberRoleError}
								</div>
							{/if}
							<div class="flex gap-2">
								<div class="relative min-w-0 flex-1">
									<Search
										class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
									/>
									<Input
										bind:value={userQuery}
										placeholder="search by name or email…"
										class="w-full min-w-0 rounded-xl border-zinc-700 bg-zinc-900 pl-8 text-xs text-zinc-100 placeholder-zinc-600"
										oninput={scheduleUserSearch}
									/>
								</div>
								<Select
									value={newMemberRole}
									onValueChange={(v: string) =>
										(newMemberRole = v as GroupMemberRole)}
								>
									<SelectTrigger class="w-28 rounded-xl">
										<span class="capitalize">{newMemberRole}</span>
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="member">member</SelectItem>
										<SelectItem value="admin">admin</SelectItem>
										<SelectItem value="owner">owner</SelectItem>
									</SelectContent>
								</Select>
							</div>
							{#if availableUserResults.length > 0}
								<div
									class="max-h-40 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900"
									onscroll={handleUserSearchScroll}
								>
									{#each availableUserResults as u (u.id)}
										<button
											type="button"
											class="flex w-full items-center gap-3 px-4 py-2.5 text-left text-xs hover:bg-zinc-800 disabled:opacity-50"
											disabled={isAddingMember}
											onclick={() => addMember(u.id)}
										>
											<User class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
											<span class="min-w-0 flex-1 truncate text-zinc-200">
												{u.display_name ?? u.username}
											</span>
											<span class="shrink-0 text-zinc-500">{u.email}</span>
											<Plus class="h-3 w-3 shrink-0 text-zinc-500" />
										</button>
									{/each}
									{#if isLoadingUsers && hasMoreUserResults}
										<div class="px-4 py-2 text-center text-xs text-zinc-500">
											loading more...
										</div>
									{:else if hasMoreUserResults}
										<button
											type="button"
											class="w-full border-t border-zinc-800 px-4 py-2 text-center text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
											onclick={() => searchUsers(false)}
										>
											load more
										</button>
									{/if}
								</div>
							{:else if userQuery.trim() && isLoadingUsers}
								<p class="px-1 text-xs text-zinc-600">loading users...</p>
							{:else if userQuery.trim() && !isLoadingUsers}
								<p class="px-1 text-xs text-zinc-600">no matching users found</p>
							{/if}
						</div>
					</div>

					<!-- metadata -->
					{#if group.metadata_ && Object.keys(group.metadata_).length > 0}
						<div class="space-y-1.5">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								metadata
							</p>
							<pre
								class="max-h-48 overflow-auto rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-xs text-zinc-300">{JSON.stringify(
									group.metadata_,
									null,
									2
								)}</pre>
						</div>
					{/if}

					<!-- danger zone -->
					<div class="space-y-2 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
						<p class="text-xs font-medium text-zinc-400">danger zone</p>
						{#if deleteError}
							<div
								class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
							>
								{deleteError}
							</div>
						{/if}
						{#if confirmDelete}
							<div class="flex items-center gap-3">
								<span class="text-sm text-zinc-300"
									>permanently delete this group?</span
								>
								<Button
									variant="destructive"
									size="sm"
									class="rounded-lg"
									disabled={isDeleting}
									onclick={deleteGroup}
								>
									{isDeleting ? 'deleting…' : 'yes, delete'}
								</Button>
								<Button
									variant="outline"
									size="sm"
									class="rounded-lg"
									onclick={() => (confirmDelete = false)}
								>
									cancel
								</Button>
							</div>
						{:else}
							<Button
								variant="outline"
								size="sm"
								class="rounded-xl border-red-900/40 text-red-400 hover:bg-red-900/20 hover:text-red-300"
								onclick={() => (confirmDelete = true)}
							>
								<Trash2 class="mr-1.5 h-3.5 w-3.5" />
								delete group
							</Button>
						{/if}
					</div>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<UserDetailsModal bind:open={isUserModalOpen} userId={selectedUserId} />

{#if groupId}
	<AclModal
		bind:open={showAclModal}
		resourceType="group"
		resourceId={groupId}
		title="group access rules"
	/>
{/if}
