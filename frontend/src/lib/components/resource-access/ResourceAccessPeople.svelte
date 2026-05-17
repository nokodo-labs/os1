<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronUpDown from '$lib/components/icons/ChevronUpDown.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import ShieldCheck from '$lib/components/icons/ShieldCheck.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import User from '$lib/components/icons/User.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import type { Group } from '$lib/stores/groups.svelte'
	import type { AccessLevel } from '$lib/stores/resourceAccess.svelte'
	import {
		levelLabel,
		SHARE_LEVELS,
		type RuleEntry,
		type UserPick,
		type UserResult,
	} from './resourceAccessModal'

	interface Props {
		panelClass: string
		quietButtonClass: string
		primaryButtonClass: string
		inputClass: string
		rules: RuleEntry[]
		searchQuery: string
		searchResults: UserResult[]
		filteredFriends: UserPick[]
		filteredGroups: Group[]
		isLoading: boolean
		isSaving: boolean
		saveError: string | null
		dragIndex: number | null
		dragOverIndex: number | null
		userLabel: (user: UserPick) => string
		onSearchInput: (event: Event) => void
		addUserRule: (user: UserPick) => void
		addGroupRule: (groupId: string, label: string) => void
		removeRule: (index: number) => void
		setLevel: (index: number, level: AccessLevel) => void
		onDragStart: (event: DragEvent, index: number) => void
		onDragOver: (event: DragEvent, index: number) => void
		onDrop: (event: DragEvent, index: number) => void
		onDragEnd: () => void
		saveRules: () => void | Promise<void>
	}

	let {
		panelClass,
		quietButtonClass,
		primaryButtonClass,
		inputClass,
		rules,
		searchQuery,
		searchResults,
		filteredFriends,
		filteredGroups,
		isLoading,
		isSaving,
		saveError,
		dragIndex,
		dragOverIndex,
		userLabel,
		onSearchInput,
		addUserRule,
		addGroupRule,
		removeRule,
		setLevel,
		onDragStart,
		onDragOver,
		onDrop,
		onDragEnd,
		saveRules,
	}: Props = $props()
</script>

<section class="{panelClass} p-5">
	<div class="mb-4 flex items-center justify-between gap-3">
		<div class="flex items-center gap-2">
			<ShieldCheck class="text-foreground/50 h-4 w-4" />
			<p class="text-foreground/90 text-sm font-semibold">people</p>
		</div>
		<p class="text-foreground/45 text-xs">{rules.length} total</p>
	</div>

	<div class="relative">
		<Search class="text-foreground/35 absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2" />
		<input
			class={inputClass}
			type="text"
			placeholder="search people and groups"
			value={searchQuery}
			oninput={onSearchInput}
		/>
	</div>

	{#if searchResults.length > 0}
		<div class="border-foreground/10 bg-foreground/4 mt-2 rounded-[18px] border py-1">
			{#each searchResults as user (user.id)}
				<button
					type="button"
					class="rounded-pill text-foreground/80 hover:bg-foreground/8 mx-1 flex w-[calc(100%-0.5rem)] cursor-pointer items-center gap-3 px-3 py-2.5 text-sm transition-colors"
					onclick={() => addUserRule(user)}
				>
					<div
						class="bg-foreground/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
					>
						<User class="h-4 w-4" />
					</div>
					<span class="flex-1 truncate text-left">
						{userLabel(user)}
					</span>
					<Plus class="text-foreground/40 h-4 w-4" />
				</button>
			{/each}
		</div>
	{/if}

	{#if filteredFriends.length > 0}
		<div class="mt-3">
			<p class="text-foreground/40 mb-2 text-xs">
				{searchQuery ? 'matching friends' : 'friends'}
			</p>
			<div class="flex flex-wrap gap-2">
				{#each filteredFriends as friend (friend.id)}
					<button
						type="button"
						class={quietButtonClass}
						onclick={() => addUserRule(friend)}
					>
						<User class="h-4 w-4" />
						<span class="max-w-36 truncate">{userLabel(friend)}</span>
						<Plus class="text-foreground/40 h-3.5 w-3.5" />
					</button>
				{/each}
			</div>
		</div>
	{/if}

	{#if filteredGroups.length > 0}
		<div class="mt-3">
			<p class="text-foreground/40 mb-2 text-xs">
				{searchQuery ? 'matching groups' : 'your groups'}
			</p>
			<div class="flex flex-wrap gap-2">
				{#each filteredGroups as group (group.id)}
					{@const alreadyAdded = rules.some((rule) => rule.subjectGroupId === group.id)}
					<button
						type="button"
						class={quietButtonClass}
						onclick={() => addGroupRule(group.id, group.name)}
						disabled={alreadyAdded}
					>
						<UserGroup class="h-4 w-4" />
						<span class="max-w-36 truncate">{group.name}</span>
						{#if alreadyAdded}
							<Check class="text-foreground/50 h-3.5 w-3.5" />
						{/if}
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<div class="mt-4 flex flex-col gap-1">
		{#if isLoading}
			<div class="flex min-h-40 items-center justify-center py-4">
				<NokodoLoader shimmer />
			</div>
		{:else if rules.length === 0}
			<EmptyState label="no one added yet - add people or groups above" compact />
		{:else}
			{#each rules as rule, ruleIndex (rule.localId)}
				<div
					class="border-foreground/10 bg-foreground/4 flex items-center gap-3 rounded-[18px] border px-3 py-2.5 transition-all {dragOverIndex ===
					ruleIndex
						? 'border-(--accent-primary)/40 bg-(--accent-primary)/5'
						: ''} {dragIndex === ruleIndex ? 'opacity-40' : ''}"
					draggable="true"
					ondragstart={(event) => onDragStart(event, ruleIndex)}
					ondragover={(event) => onDragOver(event, ruleIndex)}
					ondrop={(event) => onDrop(event, ruleIndex)}
					ondragend={onDragEnd}
					role="listitem"
				>
					<div
						class="text-foreground/20 flex cursor-grab flex-col items-center active:cursor-grabbing"
						aria-hidden="true"
					>
						<ChevronUpDown class="h-4 w-4" />
					</div>

					<div
						class="bg-foreground/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
					>
						{#if rule.subjectGroupId}
							<UserGroup class="h-4 w-4" />
						{:else}
							<User class="h-4 w-4" />
						{/if}
					</div>

					<span class="text-foreground/80 min-w-0 flex-1 truncate text-sm">
						{rule.subjectLabel}
					</span>

					<div
						class="border-foreground/10 bg-foreground/5 rounded-pill flex items-center gap-1 border p-1"
					>
						{#each SHARE_LEVELS as option (option.value)}
							<button
								type="button"
								class="rounded-pill cursor-pointer px-2.5 py-1 text-xs font-semibold transition-all {rule.level ===
								option.value
									? 'bg-(--accent-primary) text-white'
									: 'text-foreground/40 hover:text-foreground/70'}"
								onclick={() => setLevel(ruleIndex, option.value)}
							>
								{levelLabel(option.value)}
							</button>
						{/each}
					</div>

					<button
						type="button"
						class="text-foreground/30 cursor-pointer transition-colors hover:text-red-400"
						onclick={() => removeRule(ruleIndex)}
						aria-label="remove"
					>
						<Trash class="h-4 w-4" />
					</button>
				</div>
			{/each}
		{/if}
	</div>

	{#if saveError}
		<p class="mt-3 text-sm text-red-400">{saveError}</p>
	{/if}

	<div class="mt-4 flex justify-end gap-2">
		<button type="button" class={primaryButtonClass} onclick={saveRules} disabled={isSaving}>
			{#if isSaving}
				<ShimmerText className="inline-block">saving</ShimmerText>
			{:else}
				<Check class="h-4 w-4" />
				save
			{/if}
		</button>
	</div>
</section>
