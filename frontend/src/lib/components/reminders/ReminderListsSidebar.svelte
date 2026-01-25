<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ReminderListRow from '$lib/components/reminders/ReminderListRow.svelte'
	import { reminders } from '$lib/stores/reminders.svelte'

	interface Props {
		selectedListId: string | null | undefined
		isLoading?: boolean
	}

	let { selectedListId, isLoading = false }: Props = $props()

	const lists = $derived(reminders.lists)
	const defaultCounts = $derived(reminders.defaultCounts)

	let showCreateDialog = $state(false)
	let newListName = $state('')

	function selectList(listId: string | null) {
		const url = listId ? `/reminders/lists/${listId}` : '/reminders'
		// @ts-expect-error resolve typing is narrower than our constructed URL
		void goto(resolve(url as never), { keepFocus: true, noScroll: true })
	}

	function handleCreateList() {
		showCreateDialog = true
		newListName = ''
	}

	function openListMenu(listId: string) {
		window.dispatchEvent(new CustomEvent('nokodo:reminders:list-menu', { detail: { listId } }))
	}
</script>

<div class="flex h-full min-h-0 flex-col">
	<header class="mt-7 flex max-h-22 items-center justify-between gap-3 px-2 py-5 pb-4">
		<div class="flex min-w-0 items-center gap-2">
			<ListBullet className="h-5 w-5 text-white/60" />
			<h2 class="min-w-0 truncate text-lg font-semibold tracking-wide text-white/85">
				lists
			</h2>
		</div>
		<button
			type="button"
			class="inline-flex h-9 w-9 items-center justify-center rounded-full border border-transparent bg-transparent text-white/80 transition-all duration-200 hover:border-white/10 hover:bg-white/5 hover:text-white"
			onclick={handleCreateList}
			aria-label="create list"
		>
			<Plus className="h-5 w-5" />
		</button>
	</header>

	{#if isLoading}
		<div class="flex flex-1 items-center justify-center">
			<NokodoLoader className="opacity-70" expanded={false} />
		</div>
	{:else}
		<nav class="min-h-0 flex-1 overflow-y-auto px-2 pt-2 pb-2">
			<div class="space-y-1">
				<ReminderListRow
					title="reminders"
					count={defaultCounts.pending_count}
					selected={selectedListId === null}
					leading={{ type: 'checkbox' }}
					onSelect={() => selectList(null)}
				/>

				{#each lists as list (list.id)}
					<ReminderListRow
						title={list.name}
						count={list.pending_count}
						selected={selectedListId === list.id}
						leading={{ type: 'emoji', emoji: list.icon ?? '📋', color: list.color }}
						onSelect={() => selectList(list.id)}
						onMenu={() => openListMenu(list.id)}
					/>
				{/each}
			</div>
		</nav>
	{/if}
</div>
