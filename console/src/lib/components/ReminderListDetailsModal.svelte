<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'

	type ReminderList = Schemas['ReminderList']
	type Reminder = Schemas['ReminderWithSubtasks']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Textarea } from '$lib/components/ui/textarea'
	import {
		Calendar,
		ChevronLeft,
		ChevronRight,
		Circle,
		CircleCheck,
		Clock,
		Hash,
		ListChecks,
		Pencil,
		Save,
		Trash2,
		User,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		listId: string | null
		onViewUser?: (userId: string) => void
		onUpdated?: (list: ReminderList) => void
		onDeleted?: (listId: string) => void
	}

	let { open = $bindable(false), listId, onViewUser, onUpdated, onDeleted }: Props = $props()

	const REMINDERS_PAGE_LIMIT = 20

	let list = $state<ReminderList | null>(null)
	let isLoading = $state(false)
	let loadError = $state<string | null>(null)

	let isEditing = $state(false)
	let editName = $state('')
	let editDescription = $state('')
	let editColor = $state('')
	let editIcon = $state('')
	let editPosition = $state<number | null>(null)
	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state(false)

	let confirmDelete = $state(false)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)

	// reminders in this list
	let reminders = $state<Reminder[]>([])
	let remindersPageIndex = $state(0)
	let isLoadingReminders = $state(false)
	let remindersError = $state<string | null>(null)
	let remindersRequestId = 0

	function close() {
		open = false
		isEditing = false
		confirmDelete = false
		saveError = null
		deleteError = null
		reminders = []
		remindersPageIndex = 0
		remindersError = null
	}

	function startEdit() {
		if (!list) return
		editName = list.name
		editDescription = list.description ?? ''
		editColor = list.color ?? ''
		editIcon = list.icon ?? ''
		editPosition = list.position ?? null
		isEditing = true
		saveError = null
	}

	function cancelEdit() {
		isEditing = false
		saveError = null
	}

	async function saveList() {
		if (!list) return
		isSaving = true
		saveError = null
		saveSuccess = false
		try {
			const r = await api.PATCH('/v1/reminder-lists/{list_id}', {
				params: { path: { list_id: list.id } },
				body: {
					name: editName.trim() || undefined,
					description: editDescription.trim() || null,
					color: editColor.trim() || null,
					icon: editIcon.trim() || null,
					position: editPosition ?? undefined,
				},
			})
			const updated = unwrap(r)
			list = updated
			isEditing = false
			saveSuccess = true
			onUpdated?.(list)
			setTimeout(() => (saveSuccess = false), 2000)
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'failed to save'
		} finally {
			isSaving = false
		}
	}

	async function deleteList() {
		if (!list) return
		isDeleting = true
		deleteError = null
		try {
			const r = await api.DELETE('/v1/reminder-lists/{list_id}', {
				params: { path: { list_id: list.id } },
			})
			unwrap(r)
			onDeleted?.(list.id)
			close()
		} catch (e) {
			deleteError = e instanceof Error ? e.message : 'failed to delete'
		} finally {
			isDeleting = false
		}
	}

	function remindersPageOffset(index: number): number {
		return Math.max(0, Math.trunc(index)) * REMINDERS_PAGE_LIMIT
	}

	function previousRemindersPage() {
		remindersPageIndex = Math.max(0, remindersPageIndex - 1)
	}

	function nextRemindersPage() {
		if (reminders.length < REMINDERS_PAGE_LIMIT) return
		remindersPageIndex += 1
	}

	async function loadReminders(sourceListId: string, pageIndex: number) {
		const requestId = ++remindersRequestId
		isLoadingReminders = true
		remindersError = null
		reminders = []
		try {
			const items = unwrap(
				await api.GET('/v1/reminder-lists/{list_id}/reminders', {
					params: {
						path: { list_id: sourceListId },
						query: {
							include_subtasks: true,
							skip: remindersPageOffset(pageIndex),
							limit: REMINDERS_PAGE_LIMIT,
							sort_by: 'position',
							sort_dir: 'asc',
						},
					},
				})
			)
			if (requestId !== remindersRequestId) return
			reminders = items
		} catch (e: unknown) {
			if (requestId !== remindersRequestId) return
			remindersError = e instanceof Error ? e.message : 'failed to load reminders'
		} finally {
			if (requestId === remindersRequestId) isLoadingReminders = false
		}
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!listId) return
		isLoading = true
		loadError = null
		list = null
		isEditing = false
		reminders = []
		remindersPageIndex = 0
		remindersError = null
		api.GET('/v1/reminder-lists/{list_id}', { params: { path: { list_id: listId } } })
			.then((r) => unwrap(r))
			.then((l) => {
				list = l
			})
			.catch((e: unknown) => {
				loadError = e instanceof Error ? e.message : 'failed to load list'
			})
			.finally(() => {
				isLoading = false
			})
	})

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!listId) return
		void loadReminders(listId, remindersPageIndex)
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
			data-dialog-content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2rem)] min-w-80 -translate-x-1/2 -translate-y-1/2 flex-col overflow-auto rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-xl"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div class="min-w-0 flex-1">
					<Dialog.Title class="truncate text-base font-semibold"
						>{list?.name ?? 'reminder list'}</Dialog.Title
					>
					<Dialog.Description class="text-xs text-zinc-500"
						>{listId ?? ''}</Dialog.Description
					>
				</div>
				<div class="flex shrink-0 items-center gap-1">
					{#if list && !isEditing}
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
								onclick={deleteList}
								disabled={isDeleting}
							>
								{isDeleting ? 'deleting…' : 'confirm?'}
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
				{:else if list}
					{#if deleteError}
						<div
							class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
						>
							{deleteError}
						</div>
					{/if}

					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							identity
						</p>
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Hash class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">id</span>
								<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
									>{list.id}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<User class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">owner</span>
								{#if onViewUser}
									<button
										type="button"
										class="min-w-0 truncate font-mono text-xs text-zinc-300 underline underline-offset-4 hover:text-zinc-100"
										onclick={() => onViewUser?.(list!.owner_id)}
										>{list.owner_id}</button
									>
								{:else}
									<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
										>{list.owner_id}</span
									>
								{/if}
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Calendar class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">created</span>
								<span class="text-xs text-zinc-300"
									>{new Date(list.created_at).toLocaleString()}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Clock class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-24 shrink-0 text-xs text-zinc-500">updated</span>
								<span class="text-xs text-zinc-300"
									>{new Date(list.updated_at).toLocaleString()}</span
								>
							</div>
						</div>
					</div>

					{#if isEditing}
						<div class="space-y-3">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								edit
							</p>
							<div class="space-y-1.5">
								<Label class="text-xs text-zinc-400">name</Label>
								<Input
									bind:value={editName}
									placeholder="name"
									class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
								/>
							</div>
							<div class="space-y-1.5">
								<Label class="text-xs text-zinc-400">description</Label>
								<Textarea
									bind:value={editDescription}
									placeholder="description"
									rows={2}
									class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
								/>
							</div>
							<div class="grid grid-cols-2 gap-3">
								<div class="space-y-1.5">
									<Label class="text-xs text-zinc-400">color</Label>
									<Input
										bind:value={editColor}
										placeholder="#hex or name"
										class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
									/>
								</div>
								<div class="space-y-1.5">
									<Label class="text-xs text-zinc-400">icon</Label>
									<Input
										bind:value={editIcon}
										placeholder="icon name"
										class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
									/>
								</div>
							</div>
							<div class="space-y-1.5">
								<Label class="text-xs text-zinc-400">position</Label>
								<Input
									type="number"
									value={editPosition ?? ''}
									oninput={(e: Event) => {
										const v = (e.target as HTMLInputElement).valueAsNumber
										editPosition = isNaN(v) ? null : v
									}}
									placeholder="position"
									class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
								/>
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
									onclick={saveList}
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
						<div class="space-y-1.5">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								details
							</p>
							<div
								class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
							>
								<div class="flex items-center gap-3 px-4 py-2.5">
									<span class="w-24 shrink-0 text-xs text-zinc-500">name</span>
									<span class="text-xs text-zinc-300">{list.name}</span>
								</div>
								{#if list.description}
									<div class="flex items-start gap-3 px-4 py-2.5">
										<span class="w-24 shrink-0 text-xs text-zinc-500"
											>description</span
										>
										<span class="min-w-0 text-xs text-zinc-300"
											>{list.description}</span
										>
									</div>
								{/if}
								{#if list.color}
									<div class="flex items-center gap-3 px-4 py-2.5">
										<span class="w-24 shrink-0 text-xs text-zinc-500"
											>color</span
										>
										<span class="inline-flex items-center gap-2">
											<span
												class="inline-block h-3.5 w-3.5 rounded-full border border-zinc-700"
												style="background-color: {list.color}"
											></span>
											<span class="text-xs text-zinc-300">{list.color}</span>
										</span>
									</div>
								{/if}
								{#if list.icon}
									<div class="flex items-center gap-3 px-4 py-2.5">
										<span class="w-24 shrink-0 text-xs text-zinc-500">icon</span
										>
										<span class="text-xs text-zinc-300">{list.icon}</span>
									</div>
								{/if}
								<div class="flex items-center gap-3 px-4 py-2.5">
									<span class="w-24 shrink-0 text-xs text-zinc-500">position</span
									>
									<span class="text-xs text-zinc-300">{list.position ?? '—'}</span
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
						</div>
					{/if}

					<!-- reminders -->
					<div class="space-y-1.5">
						<div class="flex items-center justify-between gap-3">
							<p
								class="flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
							>
								<ListChecks class="h-3.5 w-3.5" />
								reminders
							</p>
							<div class="flex items-center gap-2">
								<Button
									variant="outline"
									size="sm"
									class="h-7 rounded-lg px-2 text-xs"
									onclick={previousRemindersPage}
									disabled={remindersPageIndex === 0 || isLoadingReminders}
								>
									<ChevronLeft class="mr-1 h-3 w-3" />
									prev
								</Button>
								<span class="text-xs text-zinc-500 tabular-nums">
									page {remindersPageIndex + 1}{reminders.length > 0
										? ` · ${reminders.length} items`
										: ''}
								</span>
								<Button
									variant="outline"
									size="sm"
									class="h-7 rounded-lg px-2 text-xs"
									onclick={nextRemindersPage}
									disabled={reminders.length < REMINDERS_PAGE_LIMIT ||
										isLoadingReminders}
								>
									next
									<ChevronRight class="ml-1 h-3 w-3" />
								</Button>
							</div>
						</div>
						{#if isLoadingReminders}
							<div class="flex items-center justify-center py-6">
								<NokodoLoader />
							</div>
						{:else if remindersError}
							<div
								class="rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-xs text-red-200"
							>
								{remindersError}
							</div>
						{:else if reminders.length === 0}
							<div
								class="rounded-xl border border-dashed border-zinc-800 py-6 text-center text-sm text-zinc-500"
							>
								no reminders in this list
							</div>
						{:else}
							<div
								class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
							>
								{#each reminders as reminder (reminder.id)}
									<div class="flex items-start gap-3 px-4 py-2.5">
										<div class="mt-0.5 shrink-0">
											{#if reminder.status === 'completed'}
												<CircleCheck class="h-4 w-4 text-emerald-400" />
											{:else}
												<Circle class="h-4 w-4 text-zinc-500" />
											{/if}
										</div>
										<div class="min-w-0 flex-1">
											<div
												class="text-sm font-medium {reminder.status ===
												'completed'
													? 'text-zinc-500 line-through'
													: 'text-zinc-200'}"
											>
												{reminder.title}
											</div>
											{#if reminder.description}
												<div
													class="mt-0.5 line-clamp-2 text-xs text-zinc-400"
												>
													{reminder.description}
												</div>
											{/if}
											{#if reminder.due_at}
												<div class="mt-1 text-xs text-zinc-500">
													<Clock class="mr-1 inline h-3 w-3" />due {new Date(
														reminder.due_at
													).toLocaleString()}
												</div>
											{/if}
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
					>
						no list selected
					</div>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
