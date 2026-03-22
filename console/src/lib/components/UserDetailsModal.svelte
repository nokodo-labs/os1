<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { api, unwrap, type Schemas } from '$lib/api'

	type User = Schemas['User']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Textarea } from '$lib/components/ui/textarea'
	import {
		Brain,
		CheckCircle,
		Circle,
		Clock,
		Hash,
		Mail,
		MessageSquare,
		Pencil,
		Save,
		Shield,
		User as UserIcon,
		UserX,
		Wifi,
		X,
		XCircle,
		FileIcon,
		FileText,
		Users,
		ListChecks,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		userId: string | null
		onClose?: () => void
		onUpdated?: (user: User) => void
		onDeleted?: (userId: string) => void
	}

	let { open = $bindable(false), userId, onClose, onUpdated, onDeleted }: Props = $props()

	let user = $state<User | null>(null)
	let counts = $state<Record<string, number>>({})
	let isLoading = $state(false)
	let loadError = $state<string | null>(null)

	let isEditing = $state(false)
	let editDisplayName = $state('')
	let editUsername = $state('')
	let editEmail = $state('')
	let editBio = $state('')
	let editAvatarUrl = $state('')
	let editIsActive = $state(true)
	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state(false)

	let prefsExpanded = $state(false)
	let prefsText = $state('')
	let prefsError = $state<string | null>(null)
	let isSavingPrefs = $state(false)
	let prefsSaveSuccess = $state(false)

	let isDeactivating = $state(false)
	let deactivateError = $state<string | null>(null)
	let confirmDeactivate = $state(false)

	function close() {
		open = false
		isEditing = false
		prefsExpanded = false
		saveError = null
		onClose?.()
	}

	function openResource(route: string, uid: string) {
		void goto(resolve(route), { state: { user: uid } })
		close()
	}

	function startEdit() {
		if (!user) return
		editDisplayName = user.display_name ?? ''
		editUsername = ((user as Record<string, unknown>).username as string) ?? ''
		editEmail = user.email
		editBio = ((user as Record<string, unknown>).bio as string) ?? ''
		editAvatarUrl = ((user as Record<string, unknown>).avatar_url as string) ?? ''
		editIsActive = user.is_active !== false
		isEditing = true
		saveError = null
	}

	function cancelEdit() {
		isEditing = false
		saveError = null
	}

	async function saveUser() {
		if (!user) return
		isSaving = true
		saveError = null
		saveSuccess = false
		try {
			const r = await api.PATCH('/v1/users/{user_id}', {
				params: { path: { user_id: user.id } },
				body: {
					display_name: editDisplayName.trim() || null,
					username: editUsername.trim() || null,
					email: editEmail.trim() || undefined,
					bio: editBio.trim() || null,
					avatar_url: editAvatarUrl.trim() || null,
					is_active: editIsActive,
				},
			})
			const updated = unwrap(r)
			user = updated
			isEditing = false
			saveSuccess = true
			onUpdated?.(updated)
			setTimeout(() => (saveSuccess = false), 2000)
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'failed to save'
		} finally {
			isSaving = false
		}
	}
	async function toggleActive() {
		if (!user) return
		isDeactivating = true
		deactivateError = null
		try {
			const r = await api.PATCH('/v1/users/{user_id}', {
				params: { path: { user_id: user.id } },
				body: { is_active: !user.is_active },
			})
			const updated = unwrap(r)
			user = updated
			confirmDeactivate = false
			onUpdated?.(updated)
			if (!updated.is_active) onDeleted?.(updated.id)
		} catch (e) {
			deactivateError = e instanceof Error ? e.message : 'failed'
		} finally {
			isDeactivating = false
		}
	}
	function openPrefs() {
		if (!user) return
		prefsText = user.preferences ? JSON.stringify(user.preferences, null, 2) : '{}'
		prefsExpanded = true
		prefsError = null
	}

	async function savePrefs() {
		if (!user) return
		let parsed: unknown
		try {
			parsed = JSON.parse(prefsText)
		} catch {
			prefsError = 'invalid JSON'
			return
		}
		isSavingPrefs = true
		prefsError = null
		prefsSaveSuccess = false
		try {
			const r = await api.PATCH('/v1/users/{user_id}', {
				params: { path: { user_id: user.id } },
				body: { preferences: parsed as Schemas['UserPreferences'] },
			})
			const updated = unwrap(r)
			user = updated
			prefsSaveSuccess = true
			onUpdated?.(updated)
			setTimeout(() => (prefsSaveSuccess = false), 2000)
		} catch (e) {
			prefsError = e instanceof Error ? e.message : 'failed to save preferences'
		} finally {
			isSavingPrefs = false
		}
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!userId) return
		isLoading = true
		loadError = null
		user = null
		isEditing = false
		prefsExpanded = false
		Promise.all([
			api.GET('/v1/users/{user_id}', { params: { path: { user_id: userId } } }).then((r) => unwrap(r)),
			api.GET('/v1/users/{user_id}/counts', { params: { path: { user_id: userId } } })
				.then((r) => r.data ?? {})
				.catch(() => ({}))
		])
			.then(([u, c]) => {
				user = u
				counts = c as Record<string, number>
			})
			.catch((e: unknown) => {
				loadError = e instanceof Error ? e.message : 'failed to load user'
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
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2rem)] min-w-80 -translate-x-1/2 -translate-y-1/2 flex-col overflow-auto rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-xl"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-base font-semibold">user details</Dialog.Title>
					<Dialog.Description class="text-xs text-zinc-500"
						>{userId ?? ''}</Dialog.Description
					>
				</div>
				<Button variant="ghost" size="icon" class="rounded-xl" onclick={close}>
					<X class="h-4 w-4" />
				</Button>
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
				{:else if user}
					<div class="flex flex-wrap gap-2">
						{#each [
							{ key: 'threads', label: 'threads', icon: MessageSquare, route: '/threads' },
							{ key: 'memories', label: 'memories', icon: Brain, route: '/memories' },
							{ key: 'notes', label: 'notes', icon: FileText, route: '/notes' },
							{ key: 'files', label: 'files', icon: FileIcon, route: '/files' },
							{ key: 'groups', label: 'groups', icon: Users, route: '/groups' },
							{ key: 'reminders', label: 'reminders', icon: ListChecks, route: '/reminders' },
						] as resource (resource.key)}
							<Button
								variant="outline"
								class="rounded-xl"
								onclick={() => user && openResource(resource.route, user.id)}
							>
								<resource.icon class="mr-1.5 h-3.5 w-3.5" />
								{resource.label}
								{#if counts[resource.key] !== undefined}
									<span class="ml-1 rounded-md bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
										{counts[resource.key]}
									</span>
								{/if}
							</Button>
						{/each}
					</div>

					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							identity
						</p>
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Hash class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-28 shrink-0 text-xs text-zinc-500">id</span>
								<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
									>{user.id}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								{#if user.is_active !== false}
									<CheckCircle class="h-3.5 w-3.5 shrink-0 text-emerald-400" />
								{:else}
									<XCircle class="h-3.5 w-3.5 shrink-0 text-red-400" />
								{/if}
								<span class="w-28 shrink-0 text-xs text-zinc-500">active</span>
								<span
									class="text-xs {user.is_active !== false
										? 'text-emerald-400'
										: 'text-red-400'}"
								>
									{user.is_active !== false ? 'yes' : 'no'}
								</span>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Shield class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-28 shrink-0 text-xs text-zinc-500">superuser</span>
								<span
									class="text-xs {user.is_superuser
										? 'text-amber-400'
										: 'text-zinc-400'}"
								>
									{user.is_superuser ? 'yes' : 'no'}
								</span>
							</div>
							{#if (user as Record<string, unknown>).is_online}
								<div class="flex items-center gap-3 px-4 py-2.5">
									<Circle
										class="h-3.5 w-3.5 shrink-0 fill-emerald-400 text-emerald-400"
									/>
									<span class="w-28 shrink-0 text-xs text-zinc-500">status</span>
									<span class="text-xs text-emerald-400">online</span>
								</div>
							{:else if (user as Record<string, unknown>).last_active_at}
								<div class="flex items-center gap-3 px-4 py-2.5">
									<Wifi class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="w-28 shrink-0 text-xs text-zinc-500"
										>last active</span
									>
									<span class="text-xs text-zinc-300">
										{new Date(
											(user as Record<string, unknown>)
												.last_active_at as string
										).toLocaleString()}
									</span>
								</div>
							{/if}
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Clock class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-28 shrink-0 text-xs text-zinc-500">created</span>
								<span class="text-xs text-zinc-300"
									>{new Date(user.created_at).toLocaleString()}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Clock class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-28 shrink-0 text-xs text-zinc-500">updated</span>
								<span class="text-xs text-zinc-300"
									>{new Date(user.updated_at).toLocaleString()}</span
								>
							</div>
						</div>
					</div>

					<div class="space-y-3">
						<div class="flex items-center justify-between">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								profile
							</p>
							{#if !isEditing}
								<Button
									variant="ghost"
									size="sm"
									class="h-7 rounded-lg px-2 text-xs text-zinc-400 hover:text-zinc-200"
									onclick={startEdit}
								>
									<Pencil class="mr-1 h-3 w-3" />
									edit
								</Button>
							{/if}
						</div>
						{#if isEditing}
							<div class="space-y-3">
								<div class="grid grid-cols-2 gap-3">
									<div class="space-y-1.5">
										<Label class="text-xs text-zinc-400">display name</Label>
										<Input
											bind:value={editDisplayName}
											placeholder="display name"
											class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
										/>
									</div>
									<div class="space-y-1.5">
										<Label class="text-xs text-zinc-400">username</Label>
										<Input
											bind:value={editUsername}
											placeholder="username"
											class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
										/>
									</div>
								</div>
								<div class="space-y-1.5">
									<Label class="text-xs text-zinc-400">email</Label>
									<Input
										bind:value={editEmail}
										type="email"
										placeholder="email"
										class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
									/>
								</div>
								<div class="space-y-1.5">
									<Label class="text-xs text-zinc-400">bio</Label>
									<Textarea
										bind:value={editBio}
										placeholder="bio"
										rows={2}
										class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
									/>
								</div>
								<div class="space-y-1.5">
									<Label class="text-xs text-zinc-400">avatar URL</Label>
									<Input
										bind:value={editAvatarUrl}
										placeholder="https://..."
										class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
									/>
								</div>
								<div class="flex items-center gap-3">
									<Label class="text-xs text-zinc-400">active</Label>
									<button
										type="button"
										aria-label="toggle active status"
										class="flex h-5 w-9 items-center rounded-full transition-colors {editIsActive
											? 'bg-emerald-600'
											: 'bg-zinc-700'}"
										onclick={() => (editIsActive = !editIsActive)}
									>
										<span
											class="ml-0.5 h-4 w-4 rounded-full bg-white transition-transform {editIsActive
												? 'translate-x-4'
												: 'translate-x-0'}"
										></span>
									</button>
									<span
										class="text-xs {editIsActive
											? 'text-emerald-400'
											: 'text-zinc-500'}"
										>{editIsActive ? 'active' : 'inactive'}</span
									>
								</div>
								{#if saveError}
									<div
										class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
									>
										{saveError}
									</div>
								{/if}
								<div class="flex gap-2">
									<Button
										variant="outline"
										size="sm"
										class="rounded-xl"
										onclick={saveUser}
										disabled={isSaving}
									>
										<Save class="mr-1.5 h-3.5 w-3.5" />
										{isSaving ? 'saving…' : 'save'}
									</Button>
									<Button
										variant="ghost"
										size="sm"
										class="rounded-xl"
										onclick={cancelEdit}
									>
										<X class="mr-1.5 h-3.5 w-3.5" />
										cancel
									</Button>
								</div>
							</div>
						{:else}
							<div
								class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
							>
								<div class="flex items-center gap-3 px-4 py-2.5">
									<UserIcon class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="w-28 shrink-0 text-xs text-zinc-500"
										>display name</span
									>
									<span class="min-w-0 truncate text-xs text-zinc-300"
										>{user.display_name ?? '—'}</span
									>
								</div>
								<div class="flex items-center gap-3 px-4 py-2.5">
									<UserIcon class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="w-28 shrink-0 text-xs text-zinc-500">username</span
									>
									<span class="min-w-0 truncate text-xs text-zinc-300">
										{(user as Record<string, unknown>).username
											? `@${(user as Record<string, unknown>).username}`
											: '—'}
									</span>
								</div>
								<div class="flex items-center gap-3 px-4 py-2.5">
									<Mail class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
									<span class="w-28 shrink-0 text-xs text-zinc-500">email</span>
									<span class="min-w-0 truncate text-xs text-zinc-300"
										>{user.email}</span
									>
								</div>
							</div>
							{#if saveSuccess}
								<div
									class="rounded-lg border border-emerald-900/50 bg-emerald-900/10 px-3 py-2 text-xs text-emerald-300"
								>
									saved
								</div>
							{/if}
						{/if}
					</div>

					<div class="space-y-2">
						<div class="flex items-center justify-between">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								preferences
							</p>
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-zinc-400 hover:text-zinc-200"
								onclick={() => {
									if (prefsExpanded) {
										prefsExpanded = false
									} else {
										openPrefs()
									}
								}}
							>
								{prefsExpanded ? 'collapse' : 'edit'}
							</Button>
						</div>
						{#if prefsExpanded}
							<Textarea
								bind:value={prefsText}
								rows={8}
								spellcheck={false}
								class="rounded-xl border-zinc-700 bg-zinc-900 font-mono text-xs text-zinc-300"
							/>
							{#if prefsError}
								<div
									class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
								>
									{prefsError}
								</div>
							{/if}
							{#if prefsSaveSuccess}
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
								onclick={savePrefs}
								disabled={isSavingPrefs}
							>
								<Save class="mr-1.5 h-3.5 w-3.5" />
								{isSavingPrefs ? 'saving…' : 'save preferences'}
							</Button>
						{:else}
							<div
								class="rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-xs text-zinc-500"
							>
								{user.preferences
									? JSON.stringify(user.preferences).substring(0, 120) +
										(JSON.stringify(user.preferences).length > 120 ? '…' : '')
									: 'no preferences set'}
							</div>
						{/if}
					</div>
					<!-- danger zone -->
					<div
						class="flex flex-col gap-2 rounded-xl border border-red-900/30 bg-red-950/10 p-4"
					>
						<p class="text-xs font-medium text-red-400">danger zone</p>
						{#if deactivateError}
							<div
								class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
							>
								{deactivateError}
							</div>
						{/if}
						{#if confirmDeactivate}
							<p class="text-xs text-zinc-400">
								{user.is_active !== false
									? 'deactivate this account? they will no longer be able to sign in.'
									: 'reactivate this account?'}
							</p>
							<div class="flex gap-2">
								<Button
									variant="outline"
									size="sm"
									class="rounded-xl border-red-800 text-red-400 hover:bg-red-950 hover:text-red-300"
									onclick={toggleActive}
									disabled={isDeactivating}
								>
									<UserX class="mr-1.5 h-3.5 w-3.5" />
									{isDeactivating ? 'saving…' : 'confirm'}
								</Button>
								<Button
									variant="ghost"
									size="sm"
									class="rounded-xl text-xs text-zinc-400"
									onclick={() => (confirmDeactivate = false)}
								>
									<X class="mr-1.5 h-3.5 w-3.5" />
									cancel
								</Button>
							</div>
						{:else}
							<Button
								variant="outline"
								size="sm"
								class="w-fit rounded-xl border-red-800 text-red-400 hover:bg-red-950 hover:text-red-300"
								onclick={() => (confirmDeactivate = true)}
							>
								<UserX class="mr-1.5 h-3.5 w-3.5" />
								{user.is_active !== false
									? 'deactivate account'
									: 'reactivate account'}
							</Button>
						{/if}
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
					>
						no user selected
					</div>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
