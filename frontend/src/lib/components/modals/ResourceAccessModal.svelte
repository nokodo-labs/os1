<script lang="ts">
	import { api } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronUpDown from '$lib/components/icons/ChevronUpDown.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import User from '$lib/components/icons/User.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { groups } from '$lib/stores/groups.svelte'
	import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'

	type AccessLevel = components['schemas']['AccessLevel']
	type AccessRuleResponse = components['schemas']['AccessRuleResponse']
	type AccessRuleCreate = components['schemas']['AccessRuleCreate']

	interface UserResult {
		id: string
		display_name?: string | null
		email?: string | null
	}

	interface RuleEntry {
		id: string | null
		subjectLabel: string
		subjectUserId: string | null
		subjectGroupId: string | null
		level: AccessLevel
		orderIndex: number
	}

	interface Props {
		open: boolean
		payload: ResourceAccessPayload | null
		onClose: () => void
	}

	let { open, payload, onClose }: Props = $props()

	let rules = $state<RuleEntry[]>([])
	let isSaving = $state(false)
	let isLoading = $state(false)
	let saveError = $state<string | null>(null)

	let searchQuery = $state('')
	let searchResults = $state<UserResult[]>([])
	let searchDebounce: ReturnType<typeof setTimeout> | null = null

	// drag state
	let dragIndex = $state<number | null>(null)
	let dragOverIndex = $state<number | null>(null)

	const ACCESS_LEVELS: AccessLevel[] = ['reader', 'editor', 'admin']

	// ---- API helpers ----

	async function loadRules(): Promise<void> {
		if (!payload) return
		isLoading = true
		try {
			let fetched: AccessRuleResponse[] = []
			switch (payload.resourceType) {
				case 'file': {
					const { data } = await api.GET('/v1/files/{file_id}/access-rules', {
						params: { path: { file_id: payload.resourceId } },
					})
					if (data) fetched = data
					break
				}
				case 'thread': {
					const { data } = await api.GET('/v1/threads/{thread_id}/access-rules', {
						params: { path: { thread_id: payload.resourceId } },
					})
					if (data) fetched = data
					break
				}
				case 'project': {
					const { data } = await api.GET(
						'/v1/projects/{project_id}/access-rules',
						{ params: { path: { project_id: payload.resourceId } } }
					)
					if (data) fetched = data
					break
				}
				case 'group': {
					const { data } = await api.GET('/v1/groups/{group_id}/access-rules', {
						params: { path: { group_id: payload.resourceId } },
					})
					if (data) fetched = data
					break
				}
				case 'agent': {
					const { data } = await api.GET('/v1/agents/{agent_id}/access-rules', {
						params: { path: { agent_id: payload.resourceId } },
					})
					if (data) fetched = data
					break
				}
			}
			rules = fetched.map((r, i) => ({
				id: r.id,
				subjectLabel:
					r.subject_user_id ?? r.subject_group_id ?? r.subject_role_id ?? 'unknown',
				subjectUserId: r.subject_user_id ?? null,
				subjectGroupId: r.subject_group_id ?? null,
				level: r.level,
				orderIndex: i,
			}))
		} finally {
			isLoading = false
		}
	}

	async function saveRules(): Promise<void> {
		if (!payload) return
		isSaving = true
		saveError = null
		const body: AccessRuleCreate[] = rules.map((r, i) => ({
			subject_user_id: r.subjectUserId ?? undefined,
			subject_group_id: r.subjectGroupId ?? undefined,
			level: r.level,
			order_index: i,
		}))
		try {
			switch (payload.resourceType) {
				case 'file':
					await api.PUT('/v1/files/{file_id}/access-rules', {
						params: { path: { file_id: payload.resourceId } },
						body,
					})
					break
				case 'thread':
					await api.PUT('/v1/threads/{thread_id}/access-rules', {
						params: { path: { thread_id: payload.resourceId } },
						body,
					})
					break
				case 'project':
					await api.PUT('/v1/projects/{project_id}/access-rules', {
						params: { path: { project_id: payload.resourceId } },
						body,
					})
					break
				case 'group':
					await api.PUT('/v1/groups/{group_id}/access-rules', {
						params: { path: { group_id: payload.resourceId } },
						body,
					})
					break
				case 'agent':
					await api.PUT('/v1/agents/{agent_id}/access-rules', {
						params: { path: { agent_id: payload.resourceId } },
						body,
					})
					break
			}
			onClose()
		} catch {
			saveError = 'failed to save access rules'
		} finally {
			isSaving = false
		}
	}

	// ---- search ----

	async function doSearch(q: string): Promise<void> {
		if (!q.trim()) {
			searchResults = []
			return
		}
		try {
			const { data } = await api.GET('/v1/users', {
				params: { query: { q: q.trim(), limit: 10 } },
			})
			searchResults = (data ?? []) as UserResult[]
		} catch {
			searchResults = []
		}
	}

	function onSearchInput(e: Event) {
		searchQuery = (e.target as HTMLInputElement).value
		if (searchDebounce) clearTimeout(searchDebounce)
		searchDebounce = setTimeout(() => void doSearch(searchQuery), 300)
	}

	function addUserRule(user: UserResult, level: AccessLevel = 'reader'): void {
		if (rules.some((r) => r.subjectUserId === user.id)) return
		rules = [
			...rules,
			{
				id: null,
				subjectLabel: user.display_name ?? user.email ?? user.id,
				subjectUserId: user.id,
				subjectGroupId: null,
				level,
				orderIndex: rules.length,
			},
		]
		searchQuery = ''
		searchResults = []
	}

	function addGroupRule(groupId: string, label: string, level: AccessLevel = 'reader'): void {
		if (rules.some((r) => r.subjectGroupId === groupId)) return
		rules = [
			...rules,
			{
				id: null,
				subjectLabel: label,
				subjectUserId: null,
				subjectGroupId: groupId,
				level,
				orderIndex: rules.length,
			},
		]
	}

	function removeRule(index: number): void {
		rules = rules.filter((_, i) => i !== index)
	}

	function setLevel(index: number, level: AccessLevel): void {
		rules = rules.map((r, i) => (i === index ? { ...r, level } : r))
	}

	// ---- drag-and-drop reordering ----

	function onDragStart(e: DragEvent, index: number): void {
		dragIndex = index
		if (e.dataTransfer) {
			e.dataTransfer.effectAllowed = 'move'
		}
	}

	function onDragOver(e: DragEvent, index: number): void {
		e.preventDefault()
		dragOverIndex = index
		if (e.dataTransfer) {
			e.dataTransfer.dropEffect = 'move'
		}
	}

	function onDrop(e: DragEvent, toIndex: number): void {
		e.preventDefault()
		if (dragIndex === null || dragIndex === toIndex) {
			dragIndex = null
			dragOverIndex = null
			return
		}
		const reordered = [...rules]
		const [moved] = reordered.splice(dragIndex, 1)
		reordered.splice(toIndex, 0, moved)
		rules = reordered
		dragIndex = null
		dragOverIndex = null
	}

	function onDragEnd(): void {
		dragIndex = null
		dragOverIndex = null
	}

	// ---- filtered groups (client-side) ----

	const filteredGroups = $derived(
		groups.list.filter(
			(g) => !searchQuery || g.name.toLowerCase().includes(searchQuery.toLowerCase())
		)
	)

	// ---- lifecycle ----

	$effect(() => {
		if (open && payload) {
			void loadRules()
			void groups.load()
		}
	})

	$effect(() => {
		if (!open) {
			rules = []
			searchQuery = ''
			searchResults = []
			saveError = null
			dragIndex = null
			dragOverIndex = null
		}
	})
</script>

<BaseModal
	{open}
	title="access rules"
	description={payload?.title ? `sharing: ${payload.title}` : undefined}
	{onClose}
	widthClassName="max-w-3xl"
>
	<div class="flex flex-col gap-4">
		<!-- search for users -->
		<div class="relative">
			<Search class="text-foreground/30 absolute top-1/2 left-3.5 size-4 -translate-y-1/2" />
			<input
				class="bg-foreground/8 text-foreground ring-foreground/10 placeholder:text-foreground/30 w-full rounded-xl py-3 pr-4 pl-10 text-sm ring-1 outline-none focus:ring-(--accent-primary)/50"
				type="text"
				placeholder="search users and groups"
				value={searchQuery}
				oninput={onSearchInput}
			/>
		</div>

		{#if searchResults.length > 0}
			<div class="rounded-xl border border-white/8 bg-white/4 py-1">
				{#each searchResults as user (user.id)}
					<button
						class="text-foreground/80 hover:bg-foreground/6 flex w-full cursor-pointer items-center gap-3 px-4 py-2.5 text-sm transition-colors"
						onclick={() => addUserRule(user)}
					>
						<div
							class="bg-foreground/10 flex size-8 shrink-0 items-center justify-center rounded-full"
						>
							<User class="size-4" />
						</div>
						<span class="flex-1 text-left">
							{user.display_name ?? user.email ?? user.id}
						</span>
						<Plus class="text-foreground/40 size-4" />
					</button>
				{/each}
			</div>
		{/if}

		<!-- quick-add / filter: groups -->
		{#if filteredGroups.length > 0}
			<div>
				<p class="text-foreground/40 mb-2 text-xs">
					{searchQuery ? 'matching groups' : 'your groups'}
				</p>
				<div class="flex flex-wrap gap-2">
					{#each filteredGroups as group (group.id)}
						{@const alreadyAdded = rules.some((r) => r.subjectGroupId === group.id)}
						<button
							class="liquid-glass flex cursor-pointer items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm transition-all hover:brightness-110 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
							onclick={() => addGroupRule(group.id, group.name)}
							disabled={alreadyAdded}
						>
							<UserGroup class="size-3.5" />
							{group.name}
							{#if alreadyAdded}
								<Check class="text-foreground/50 size-3" />
							{/if}
						</button>
					{/each}
				</div>
			</div>
		{/if}

		<!-- ACL rules list -->
		<div class="flex flex-col gap-1">
			<p class="text-foreground/40 mb-1 text-xs">
				access rules {rules.length > 0 ? `(${rules.length})` : ''}
			</p>
			{#if isLoading}
				<div class="py-4 flex justify-center"><NokodoLoader shimmer /></div>
			{:else if rules.length === 0}
				<p class="text-foreground/30 py-4 text-center text-sm">
					no rules yet — add users or groups above
				</p>
			{:else}
				{#each rules as rule, i (i)}
					<div
						class="flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-all {dragOverIndex ===
						i
							? 'border-(--accent-primary)/40 bg-(--accent-primary)/5'
							: 'border-white/8 bg-white/4'} {dragIndex === i ? 'opacity-40' : ''}"
						draggable="true"
						ondragstart={(e) => onDragStart(e, i)}
						ondragover={(e) => onDragOver(e, i)}
						ondrop={(e) => onDrop(e, i)}
						ondragend={onDragEnd}
						role="listitem"
					>
						<!-- drag handle -->
						<div
							class="text-foreground/20 flex cursor-grab flex-col items-center active:cursor-grabbing"
							aria-hidden="true"
						>
							<ChevronUpDown class="size-4" />
						</div>

						<!-- subject icon -->
						<div
							class="bg-foreground/10 flex size-8 shrink-0 items-center justify-center rounded-full"
						>
							{#if rule.subjectGroupId}
								<UserGroup class="size-4" />
							{:else}
								<User class="size-4" />
							{/if}
						</div>

						<!-- label -->
						<span class="text-foreground/80 flex-1 truncate text-sm"
							>{rule.subjectLabel}</span
						>

						<!-- level selector -->
						<div class="flex items-center gap-1 rounded-lg bg-black/15 p-0.5">
							{#each ACCESS_LEVELS as lvl (lvl)}
								<button
									class="cursor-pointer rounded-md px-2.5 py-1 text-xs transition-all {rule.level ===
									lvl
										? 'bg-(--accent-primary)/20 font-medium text-(--accent-primary)'
										: 'text-foreground/40 hover:text-foreground/70'}"
									onclick={() => setLevel(i, lvl)}
								>
									{lvl}
								</button>
							{/each}
						</div>

						<!-- remove -->
						<button
							class="text-foreground/30 cursor-pointer transition-colors hover:text-red-400"
							onclick={() => removeRule(i)}
							aria-label="remove rule"
						>
							<Trash class="size-4" />
						</button>
					</div>
				{/each}
			{/if}
		</div>

		{#if saveError}
			<p class="text-sm text-red-400">{saveError}</p>
		{/if}

		<!-- save -->
		<div class="flex justify-end gap-2 pt-1">
			<button
				class="text-foreground/60 hover:text-foreground cursor-pointer rounded-xl px-4 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40"
				onclick={onClose}
				disabled={isSaving}
			>
				cancel
			</button>
			<button
				class="liquid-glass cursor-pointer rounded-xl px-5 py-2 text-sm font-medium transition-all hover:brightness-110 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50"
				onclick={saveRules}
				disabled={isSaving}
			>
				{#if isSaving}<ShimmerText className="inline-block">saving</ShimmerText>{:else}save{/if}
			</button>
		</div>
	</div>
</BaseModal>
