<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChatInput from '$lib/components/chat/ChatInput.svelte'
	import SearchResultsBox, {
		type SearchResultsKeyHandler,
		type SearchResultsRow,
		type SearchResultsSection,
	} from '$lib/components/common/SearchResultsBox.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import Inbox from '$lib/components/icons/Inbox.svelte'
	import LoadingMoreIndicator from '$lib/components/LoadingMoreIndicator.svelte'
	import ConversationAvatar from '$lib/components/messages/ConversationAvatar.svelte'
	import ConversationCard from '$lib/components/messages/ConversationCard.svelte'
	import ConversationGroupingButton from '$lib/components/messages/ConversationGroupingButton.svelte'
	import ConversationRow from '$lib/components/messages/ConversationRow.svelte'
	import ConversationSection from '$lib/components/messages/ConversationSection.svelte'
	import MessageRequestsModal from '$lib/components/messages/MessageRequestsModal.svelte'
	import NewConversationModal from '$lib/components/messages/NewConversationModal.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
	import { Skeleton } from '$lib/components/primitives'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import {
		conversationMatchesName,
		searchConversations,
		searchInvites,
	} from '$lib/messages/conversationSearch'
	import {
		groupConversations,
		readStoredGrouping,
		storeGrouping,
		type ConversationGroupingId,
	} from '$lib/messages/grouping'
	import type { Thread } from '$lib/stores/chat.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { messages } from '$lib/stores/messages.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { conversationDisplay } from '$lib/utils/conversationDisplay'

	const chrome = useSystemChrome()

	const islandButtonClass =
		'group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]'

	const SKELETON_ROWS = [0, 1, 2, 3, 4, 5, 6]
	const SEARCH_SKELETON_ROWS = [0, 1, 2]

	/** one row of the find-mode results, in either of its two runs. */
	type SearchEntry = {
		id: string
		kind: 'conversation' | 'invite'
		thread: Thread
		dividerAbove: boolean
	}

	let composerOpen = $state(false)
	let requestsOpen = $state(false)

	let groupBy = $state<ConversationGroupingId>(readStoredGrouping())

	const groups = $derived(
		groupConversations(groupBy, messages.conversations, (id) => messages.unreadCount(id))
	)

	// find mode: the bar at the bottom is always there, and a query is what
	// swaps the inbox above it for results.
	let searchValue = $state('')
	let conversationHits = $state<Thread[]>([])
	let inviteHits = $state<Thread[]>([])
	let isSearchLoading = $state(false)
	let searchKeyHandler = $state<SearchResultsKeyHandler | undefined>(undefined)
	let searchDebounceTimer: number | null = null
	let searchAbort: AbortController | null = null

	const searchQuery = $derived(searchValue.trim())
	const isSearching = $derived(searchQuery.length > 0)

	const searchSections = $derived.by((): SearchResultsSection<SearchEntry>[] => {
		const sections: SearchResultsSection<SearchEntry>[] = []
		if (conversationHits.length > 0) {
			sections.push({
				id: 'conversations',
				label: 'conversations',
				items: conversationHits.map((thread, index) => ({
					id: `conversation:${thread.id}`,
					kind: 'conversation',
					thread,
					dividerAbove: index > 0,
				})),
			})
		}
		if (inviteHits.length > 0) {
			sections.push({
				id: 'invites',
				label: 'requests',
				items: inviteHits.map((thread, index) => ({
					id: `invite:${thread.id}`,
					kind: 'invite',
					thread,
					dividerAbove: index > 0,
				})),
			})
		}
		return sections
	})

	function selectGrouping(id: ConversationGroupingId): void {
		groupBy = id
		storeGrouping(id)
	}

	function openConversation(threadId: string): void {
		void goto(resolve(`/c/${threadId}`))
	}

	/** requests have no page of their own, so a matched one opens the modal. */
	function openSearchEntry(entry: SearchEntry): void {
		if (entry.kind === 'invite') {
			requestsOpen = true
			return
		}
		openConversation(entry.thread.id)
	}

	/** enter with nothing walked to takes the top hit, the way a search field does. */
	function submitSearch(): void {
		const first = searchSections[0]?.items[0]
		if (first) openSearchEntry(first)
	}

	function clearSearch(): void {
		searchValue = ''
	}

	/** the page itself scrolls, so the next page is pulled in when the end nears the viewport. */
	function loadMoreOnView(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries.some((entry) => entry.isIntersecting)) void messages.loadMore()
			},
			{ rootMargin: '400px 0px' }
		)
		observer.observe(node)
		return () => observer.disconnect()
	}

	$effect(() => {
		void messages.load()
		void messages.loadInvites()
	})

	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	// the listed inbox answers by name instantly; the debounced server pass adds
	// what only it can see (titles and message content across every page).
	$effect(() => {
		const query = searchQuery
		const userId = session.currentUserId
		const loaded = messages.conversations

		if (searchDebounceTimer !== null) {
			window.clearTimeout(searchDebounceTimer)
			searchDebounceTimer = null
		}
		searchAbort?.abort()
		searchAbort = null

		if (!query) {
			conversationHits = []
			inviteHits = []
			isSearchLoading = false
			return
		}

		inviteHits = searchInvites(messages.invites, query, userId)
		conversationHits = loaded.filter((thread) => conversationMatchesName(thread, query, userId))
		if (!userId) return

		isSearchLoading = true
		const controller = new AbortController()
		searchAbort = controller
		searchDebounceTimer = window.setTimeout(() => {
			searchDebounceTimer = null
			void searchConversations({ query, userId, loaded, signal: controller.signal })
				.then((found) => {
					if (!controller.signal.aborted) conversationHits = found
				})
				.catch(() => {})
				.finally(() => {
					if (!controller.signal.aborted) isSearchLoading = false
				})
		}, 180)
	})
</script>

{#snippet islandContextActions()}
	<!-- requests have no standalone view: the entry point exists only while some are pending -->
	{#if messages.inviteCount > 0}
		<button
			type="button"
			class="{islandButtonClass} relative"
			onclick={() => (requestsOpen = true)}
			aria-label="message requests"
		>
			<Inbox class="h-6 w-6" strokeWidth="2" />
			<span
				class="bg-foreground text-background absolute -top-0.5 -right-0.5 flex size-3.5 items-center justify-center rounded-full text-[9px] leading-none font-semibold"
				aria-hidden="true"
			>
				{messages.inviteCount > 9 ? '9+' : messages.inviteCount}
			</span>
		</button>
	{/if}
	<button
		type="button"
		class={islandButtonClass}
		onclick={() => (composerOpen = true)}
		aria-label="new conversation"
	>
		<ChatPlus class="h-6 w-6" strokeWidth="2" />
	</button>
	<button
		type="button"
		class={islandButtonClass}
		onclick={() => modals.open('archived-chats')}
		aria-label="archived chats"
	>
		<ArchiveBox class="h-6 w-6" strokeWidth="2" />
	</button>
	<ConversationGroupingButton value={groupBy} onSelect={selectGrouping} />
{/snippet}

{#snippet searchRow(entry: SearchEntry, state: SearchResultsRow)}
	{#if entry.kind === 'conversation'}
		<ConversationRow
			thread={entry.thread}
			unreadCount={messages.unreadCount(entry.thread.id)}
			selected={state.highlighted}
			dividerAbove={entry.dividerAbove}
			onOpen={state.select}
			onRemoved={messages.removeConversation}
		/>
	{:else}
		{@const display = conversationDisplay(entry.thread, session.currentUserId)}
		<div class="relative min-w-0" role="listitem">
			{#if entry.dividerAbove}
				<span
					class="bg-foreground/10 pointer-events-none absolute top-0 right-0 left-17 h-px"
					aria-hidden="true"
				></span>
			{/if}
			<button
				type="button"
				class="hover:bg-interactive-hover flex w-full min-w-0 cursor-pointer items-center gap-3 border-none px-3 py-2.5 text-left transition-colors duration-200"
				style={state.highlighted ? 'background-color: rgb(var(--accent-rgb) / 0.3);' : ''}
				onclick={state.select}
			>
				<ConversationAvatar faces={display.faces} isGroup={display.isGroup} />
				<span class="flex min-w-0 flex-1 flex-col gap-0.5">
					<span class="text-foreground truncate text-sm font-medium">{display.title}</span
					>
					<span class="text-foreground/50 truncate text-xs">wants to message you</span>
				</span>
				<ChevronRight class="text-foreground/40 h-4 w-4 shrink-0" strokeWidth="2" />
			</button>
		</div>
	{/if}
{/snippet}

<div class="absolute inset-0 flex flex-col">
	<div class="relative flex-1 overflow-y-auto">
		<div
			class="flex flex-col gap-6"
			style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); padding-top: calc(var(--chrome-island-offset, 0px) + var(--spacing-island-content)); padding-bottom: 96px;"
		>
			<PageTitle icon={ChatBubble} label="messages" iconColor="text-(--accent-primary)" />

			{#if isSearching}
				<SearchResultsBox
					query={searchQuery}
					sections={searchSections}
					listRole="list"
					listLabel="conversation results"
					onSelect={openSearchEntry}
					onDismiss={clearSearch}
					onKeyHandler={(handler) => (searchKeyHandler = handler)}
					row={searchRow}
				/>
				{#if searchSections.length === 0}
					<ConversationCard>
						{#if isSearchLoading}
							{#each SEARCH_SKELETON_ROWS as row (row)}
								<div class="flex items-center gap-3 px-3 py-3">
									<Skeleton shape="avatar" width="2.75rem" height="2.75rem" />
									<Skeleton shape="lines" lines={2} class="flex-1" />
								</div>
							{/each}
						{:else}
							<EmptyState label="no conversations found" compact>
								{#snippet icon()}<ChatBubble class="size-6" />{/snippet}
							</EmptyState>
						{/if}
					</ConversationCard>
				{/if}
			{:else}
				<!-- requests live above the inbox, not beside it: they are a transient
				     interruption, not a second place conversations live -->
				{#if messages.inviteCount > 0}
					<ConversationCard label="requests">
						<button
							type="button"
							class="hover:bg-interactive-hover flex w-full cursor-pointer items-center gap-3 border-none bg-transparent px-3.5 py-3 text-left transition-colors"
							onclick={() => (requestsOpen = true)}
						>
							<span
								class="flex h-7 min-w-7 items-center justify-center rounded-full bg-(--accent-primary) px-2 text-xs font-semibold text-white"
							>
								{messages.inviteCount}
							</span>
							<span
								class="text-foreground/85 min-w-0 flex-1 truncate text-sm font-medium"
							>
								{messages.inviteCount === 1
									? 'message request'
									: 'message requests'}
							</span>
							<ChevronRight
								class="text-foreground/40 h-4 w-4 shrink-0"
								strokeWidth="2"
							/>
						</button>
					</ConversationCard>
				{/if}

				{#if messages.isLoading && messages.conversations.length === 0}
					<ConversationCard>
						{#each SKELETON_ROWS as row (row)}
							<div class="flex items-center gap-3 px-3 py-3">
								<Skeleton shape="avatar" width="2.75rem" height="2.75rem" />
								<Skeleton shape="lines" lines={2} class="flex-1" />
							</div>
						{/each}
					</ConversationCard>
				{:else if messages.conversations.length === 0}
					<ConversationCard>
						<EmptyState
							label="no conversations yet"
							description="start a DM or group chat."
						>
							{#snippet icon()}<ChatBubble class="size-6" />{/snippet}
						</EmptyState>
					</ConversationCard>
				{:else}
					{#each groups as group (group.id)}
						<ConversationSection
							label={group.label || undefined}
							threads={group.threads}
							unreadCountOf={(id) => messages.unreadCount(id)}
							onOpen={openConversation}
							onRemoved={messages.removeConversation}
						/>
					{/each}
					{#if messages.hasMore && !messages.isLoadingMore}
						<div aria-hidden="true" {@attach loadMoreOnView}></div>
					{/if}
					{#if messages.isLoadingMore}
						<LoadingMoreIndicator className="py-3" label="loading more" />
					{/if}
				{/if}
			{/if}
		</div>
	</div>

	<!-- find mode docks the chat input at the bottom of the page, in both layout
	     modes: messages is a flat list, so there is no detail pane to hand it to. -->
	<div
		class="absolute right-0 bottom-0 left-0 z-10 pt-4 {device.virtualKeyboardOpen &&
		device.isMobile
			? 'pb-2'
			: 'pb-6'}"
		data-messages-search-bar
	>
		<div
			class="relative mx-auto w-full {device.isMobile ? '' : 'max-w-7xl'}"
			style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
		>
			<ChatInput
				bind:value={searchValue}
				mode="search"
				placeholder="search conversations"
				onSubmit={submitSearch}
				onClear={clearSearch}
				onKeyDown={(event) => searchKeyHandler?.(event) || false}
				showSearchFilters={false}
				clearOnSubmit={false}
				viewTransitionName="chat-input"
			/>
		</div>
	</div>
</div>

<NewConversationModal open={composerOpen} onClose={() => (composerOpen = false)} />
<MessageRequestsModal
	open={requestsOpen}
	onClose={() => (requestsOpen = false)}
	onOpenConversation={(threadId) => {
		requestsOpen = false
		openConversation(threadId)
	}}
/>
