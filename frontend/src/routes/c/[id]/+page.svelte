<script lang="ts">
	import { page } from '$app/state'
	import AgentSelector from '$lib/components/chat/AgentSelector.svelte'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import ChatGptLoadingIndicator from '$lib/components/chat/ChatGptLoadingIndicator.svelte'
	import ChatInput from '$lib/components/chat/ChatInput.svelte'
	import ChatSidebarToggleButton from '$lib/components/chat/ChatSidebarToggleButton.svelte'
	import MessageActionButton from '$lib/components/chat/MessageActionButton.svelte'
	import ToolExecutionCard from '$lib/components/chat/ToolExecutionCard.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import MarkdownRenderer from '$lib/components/markdown/MarkdownRenderer.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import { chat as chatStore } from '$lib/stores/chat.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { untrack } from 'svelte'
	import { fade } from 'svelte/transition'
	import { createChatState, type ApiMessage } from './chat.svelte'

	// Initialize chat state
	const chat = createChatState()

	// Local UI state
	let didLoadAgents = $state(false)
	let inputFocusToken = $state(0)
	let lastInputFocusKey = $state<string | null>(null)

	// System chrome for agent selector
	const chrome = useSystemChrome()

	// set accent color for auto accent colors feature
	$effect(() => {
		accentStore.set('green')
	})

	// ─────────────────────────────────────────────────────────────────────────────
	// Effects: Agents loading
	// ─────────────────────────────────────────────────────────────────────────────
	$effect(() => {
		if (!device.ready) return
		if (device.isMobile) return
		const threadId = page.params.id
		if (!threadId) return
		if (threadId === lastInputFocusKey) return
		lastInputFocusKey = threadId
		inputFocusToken += 1
	})

	$effect(() => {
		const t = chat.thread?.title
		pageTitleStore.pageTitle = t && t.trim() ? t : 'untitled chat'
	})

	$effect(() => {
		if (didLoadAgents) return
		didLoadAgents = true
		void agents.load()
	})

	$effect(() => {
		if (chat.selectedAgent !== '') return
		if (agents.list.length === 0) return
		chat.selectedAgent = agents.list[0].id
	})

	// ─────────────────────────────────────────────────────────────────────────────
	// Effects: Thread loading and management
	// ─────────────────────────────────────────────────────────────────────────────
	$effect(() => {
		const threadId = page.params.id
		return untrack(() => {
			if (!threadId) {
				chat.clearThread()
				return
			}
			let cancelled = false
			chat.isThreadLoading = true
			chat.hasLoadedBranch = false

			void (async () => {
				try {
					const loaded = await chat.loadTree(threadId)
					if (cancelled) return
					chat.hasLoadedBranch = loaded
				} finally {
					if (!cancelled) chat.isThreadLoading = false
				}
			})()

			return () => {
				cancelled = true
				chat.clearThread()
			}
		})
	})

	// ─────────────────────────────────────────────────────────────────────────────
	// Effects: Island context actions for agent selector
	// ─────────────────────────────────────────────────────────────────────────────
	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	// ─────────────────────────────────────────────────────────────────────────────
	// Effects: Tool events subscription
	// ─────────────────────────────────────────────────────────────────────────────
	$effect(() => {
		if (!chat.thread) return
		return chat.subscribeToToolEvents(chat.thread.id)
	})

	// ─────────────────────────────────────────────────────────────────────────────
	// Effects: Pending chat start
	// ─────────────────────────────────────────────────────────────────────────────
	$effect(() => {
		if (!chat.thread) return
		const pending = chatStore.pendingChatStart
		if (!pending || pending.threadId !== chat.thread.id) return
		if (chat.messages.length !== 0) {
			chatStore.consumePendingChatStart(chat.thread.id)
			return
		}
		if (
			chat.isGenerating ||
			chat.runError ||
			chat.optimisticUserMessage !== null ||
			chat.selectedAgent === ''
		)
			return
		const content = chatStore.consumePendingChatStart(chat.thread.id)
		if (!content) return
		chat.handleSendMessage(content)
	})

	// ─────────────────────────────────────────────────────────────────────────────
	// Effects: Input overlay height tracking
	// ─────────────────────────────────────────────────────────────────────────────
	$effect(() => {
		if (!chat.inputOverlay) {
			chat.inputOverlayHeight = 0
			return
		}
		const overlay = chat.inputOverlay
		const update = () => {
			chat.inputOverlayHeight = overlay?.offsetHeight ?? 0
		}
		update()
		const ro = new ResizeObserver(update)
		ro.observe(overlay)
		return () => ro.disconnect()
	})

	// ─────────────────────────────────────────────────────────────────────────────
	// Effects: Auto-scroll
	// ─────────────────────────────────────────────────────────────────────────────
	$effect(() => {
		const threadId = page.params.id
		if (!threadId) return
		if (threadId !== chat.lastThreadId) {
			chat.lastThreadId = threadId
			chat.initialScrollDone = false
			chat.autoScroll = true
		}
		if (!chat.hasLoadedBranch) {
			chat.initialScrollDone = false
			return
		}
		if (!chat.scrollContainer) return

		// Dependency reads to track changes
		const streamingContent = chat.streamingAssistant?.content ?? ''
		const optimisticContent = chat.optimisticUserMessage?.content ?? ''
		const blocksCount = chat.runBlocks.length
		void streamingContent
		void optimisticContent
		void blocksCount
		void chat.inputOverlayHeight

		if (!chat.initialScrollDone) {
			chat.initialScrollDone = true
			void chat.queueScrollToBottom('auto')
			return
		}

		// Keep pinned while streaming if user was already at bottom
		if (chat.isGenerating && chat.autoScroll) void chat.queueScrollToBottom('auto')
	})

	// ─────────────────────────────────────────────────────────────────────────────
	// Effects: Rebuild run blocks when messages change
	// ─────────────────────────────────────────────────────────────────────────────
	$effect(() => {
		chat.rebuildRunBlocks()
	})
</script>

{#snippet islandContextActions()}
	<AgentSelector
		selectedAgent={chat.selectedAgent}
		onAgentChange={(agentId) => (chat.selectedAgent = agentId)}
	/>
	{#if device.isMobile}
		<ChatSidebarToggleButton />
	{/if}
{/snippet}

<div class="absolute inset-0 flex flex-col">
	{#if !chat.autoScroll && chat.hasRenderableMessages}
		<div
			class="pointer-events-none absolute inset-x-0 z-20 flex justify-center"
			style={`bottom: ${Math.max(24, chat.inputOverlayHeight + 16)}px;`}
		>
			<button
				type="button"
				class="liquid-glass--frosted pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full border border-white/10 text-white/85 transition-colors hover:bg-white/10 hover:text-white"
				aria-label="scroll to bottom"
				onclick={() => {
					chat.autoScroll = true
					chat.scrollToBottom('smooth')
				}}
			>
				<ArrowUp class="h-4 w-4 rotate-180" />
			</button>
		</div>
	{/if}

	<div
		class="relative flex-1 overflow-y-auto"
		style="view-transition-name: thread-body;"
		bind:this={chat.scrollContainer}
		onscroll={chat.handleScroll}
	>
		<div
			class="mx-auto flex min-h-full w-full flex-col {device.isMobile ? '' : 'max-w-7xl'}"
			style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); padding-top: calc(var(--chrome-island-offset, 0px) + 16px); padding-bottom: {Math.max(
				96,
				chat.inputOverlayHeight + 24
			)}px;"
		>
			{#if chat.isTemporaryChat && chat.hasLoadedBranch && chat.messages.length === 0 && !chat.optimisticUserMessage && !chat.runError}
				<div class="flex flex-1 items-center justify-center py-16">
					<div class="max-w-md text-center">
						<div
							class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/5 text-white/85"
						>
							<EyeSlash class="h-7 w-7" />
						</div>
						<h2 class="text-2xl font-semibold text-white/90">temporary chat enabled</h2>
						<p class="mt-2 text-sm text-white/60">
							send a message to start. messages here won't be saved.
						</p>
					</div>
				</div>
			{:else if chat.hasLoadedBranch && !chat.hasRenderableMessages}
				<div class="flex flex-1 items-center justify-center py-16">
					<div class="max-w-md text-center">
						<div
							class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/5 text-white/85"
						>
							<EyeSlash class="h-7 w-7" />
						</div>
						<h2 class="text-2xl font-semibold text-white/90">no messages yet</h2>
						<p class="mt-2 text-sm text-white/60">
							send a message to begin this thread.
						</p>
					</div>
				</div>
			{:else if chat.hasLoadedBranch}
				<div class="flex flex-1 flex-col gap-6 py-4">
					{#if chat.isLoadingOlderMessages}
						<div class="flex justify-center py-4">
							<NokodoLoader className="opacity-70" shimmer />
						</div>
					{:else if chat.hasMoreMessages}
						<!-- Spacer for scroll trigger area -->
						<div class="h-1"></div>
					{/if}
					{#each chat.runBlocks as block, i (block.runId)}
						<div class="space-y-3">
							<!-- user messages for this run (both real and optimistic) -->
							{#each block.items.filter((item) => item.kind === 'user' || item.kind === 'optimistic_user') as item}
								{#if item.kind === 'user'}
									{@const siblings =
										chat.messageChildren.get(item.message.parent_id ?? null) ??
										[]}
									<UserChatMessage
										content={chat.contentPartsToText(item.message.content)}
										timestamp={chat.getMessageCreatedAt(item.message)}
										align={item.align}
										siblingCount={siblings.length}
										currentSiblingIndex={siblings.indexOf(item.message.id)}
										onPrevious={() =>
											chat.switchBranch(item.message.id, 'prev')}
										onNext={() => chat.switchBranch(item.message.id, 'next')}
									>
										{#snippet actions()}
											<MessageActionButton
												onclick={() =>
													chat.handleCopyMessage(
														chat.contentPartsToText(
															item.message.content
														)
													)}
												ariaLabel="copy message"
											>
												<DocumentDuplicate
													class="h-4 w-4"
													strokeWidth="2"
												/>
											</MessageActionButton>
											{#if item.align === 'right'}
												<MessageActionButton
													onclick={() =>
														chat.handleEditMessage(item.message.id)}
													ariaLabel="edit message"
												>
													<Pencil variant="solid" class="h-4 w-4" />
												</MessageActionButton>
												<MessageActionButton
													onclick={() =>
														chat.requestDeleteUserMessage(
															item.message.id
														)}
													ariaLabel="delete message"
												>
													<GarbageBin class="h-4 w-4" strokeWidth="2" />
												</MessageActionButton>
											{/if}
										{/snippet}
									</UserChatMessage>
								{:else if item.kind === 'optimistic_user'}
									<UserChatMessage
										content={item.content}
										timestamp={item.timestamp}
									>
										{#snippet actions()}
											<MessageActionButton
												onclick={() => chat.handleCopyMessage(item.content)}
												ariaLabel="copy message"
											>
												<DocumentDuplicate
													class="h-4 w-4"
													strokeWidth="2"
												/>
											</MessageActionButton>
										{/snippet}
									</UserChatMessage>
								{/if}
							{/each}

							<!-- agent run: render ALL items in chronological order -->
							{#if true}
								{@const responseItems = chat.getBlockResponseItems(block)}
								{@const firstAssistant = chat.getBlockFirstAssistant(block)}
								{@const isStreamingBlock =
									chat.blockHasStreamingAssistant(block) &&
									chat.streamingAssistant}

								{#if responseItems.length > 0 || isStreamingBlock}
									{@const rootId = block.responseRootId}
									{@const blockParentId =
										(rootId
											? (chat.messageTree.get(rootId)?.parent_id ?? null)
											: null) ??
										(isStreamingBlock ? chat.streamingAssistantParentId : null)}
									{@const assistantSiblings =
										chat.messageChildren.get(blockParentId) ?? []}
									{@const currentSiblingIndex = rootId
										? isStreamingBlock && !chat.messageTree.has(rootId)
											? assistantSiblings.length
											: assistantSiblings.indexOf(rootId)
										: 0}
									{@const siblingCount =
										assistantSiblings.length +
										(isStreamingBlock && !chat.messageTree.has(rootId ?? '')
											? 1
											: 0)}
									{@const displayAgent =
										firstAssistant?.sender_agent_id ??
										chat.streamingAssistant?.senderAgentId ??
										null}

									<AssistantChatMessage
										isLastMessage={i === chat.runBlocks.length - 1 &&
											!chat.runError}
										{siblingCount}
										{currentSiblingIndex}
										onPrevious={() =>
											rootId && chat.switchBranch(rootId, 'prev')}
										onNext={() => rootId && chat.switchBranch(rootId, 'next')}
										content=""
										timestamp={firstAssistant
											? chat.getMessageCreatedAt(firstAssistant)
											: isStreamingBlock
												? (chat.streamingAssistant?.timestamp ?? new Date())
												: undefined}
										isStreaming={Boolean(isStreamingBlock)}
										showStreamingPlaceholder={false}
										modelName={displayAgent
											? (chat.agentNameById.get(displayAgent) ?? 'assistant')
											: 'assistant'}
										avatarUrl={displayAgent
											? (chat.agentAvatarById.get(displayAgent) ?? null)
											: null}
									>
										{#snippet lead()}
											{#each responseItems as item, idx (idx)}
												{#if item.kind === 'assistant'}
													<div
														class="assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word"
													>
														<MarkdownRenderer
															content={chat.contentPartsToText(
																item.message.content
															)}
															isStreaming={false}
														/>
													</div>
												{:else if item.kind === 'tool'}
													{#key chat.toolTick}
														{@const exec = chat.getToolExecution(
															item.toolCallId
														)}
														{#if exec}
															<ToolExecutionCard execution={exec} />
														{/if}
													{/key}
												{:else if item.kind === 'streaming_tool'}
													{#key chat.toolTick}
														{@const exec = chat.getToolExecution(
															item.toolCallId
														)}
														{#if exec}
															<ToolExecutionCard execution={exec} />
														{/if}
													{/key}
												{:else if item.kind === 'streaming_assistant' && chat.streamingAssistant}
													{#if chat.streamingAssistant.content.trim()}
														<div
															class="assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word"
														>
															<MarkdownRenderer
																content={chat.streamingAssistant
																	.content}
																isStreaming={true}
															/>
														</div>
													{:else}
														<div
															class="assistant-markdown text-[0.95rem] leading-relaxed text-white/60"
														>
															<div class="my-3">
																<ChatGptLoadingIndicator />
															</div>
														</div>
													{/if}
												{/if}
											{/each}
										{/snippet}

										{#snippet actions()}
											<MessageActionButton
												onclick={() => {
													const allText = responseItems
														.filter(
															(
																i
															): i is {
																kind: 'assistant'
																message: ApiMessage
															} => i.kind === 'assistant'
														)
														.map((i) =>
															chat.contentPartsToText(
																i.message.content
															)
														)
														.join('\n\n')
													const streamText = isStreamingBlock
														? (chat.streamingAssistant?.content ?? '')
														: ''
													chat.handleCopyMessage(
														allText +
															(streamText ? '\n\n' + streamText : '')
													)
												}}
												ariaLabel="copy message"
											>
												<DocumentDuplicate
													class="h-4 w-4"
													strokeWidth="2"
												/>
											</MessageActionButton>
											{#if !isStreamingBlock}
												<MessageActionButton
													onclick={() => {
														// Pass the user message ID so new responses branch from there
														const userMessageId =
															chat.findRunUserMessage(block)
														chat.handleRegenerateMessage(userMessageId)
													}}
													ariaLabel="retry"
												>
													<ArrowPath class="h-4 w-4" strokeWidth="2" />
												</MessageActionButton>
											{/if}
										{/snippet}
									</AssistantChatMessage>
								{/if}
							{/if}
						</div>
					{/each}

					{#if chat.runError}
						<div in:fade={{ duration: 200 }}>
							<AssistantChatMessage
								content={chat.selectedAgent
									? 'there was an error generating a response.'
									: 'select an agent to generate a response.'}
								modelName={chat.selectedAgentName}
								isLastMessage={true}
								tone="error"
							>
								{#snippet actions()}
									<button
										type="button"
										class="rounded-xl bg-transparent px-3 py-1.5 text-sm text-white/70 transition-colors hover:text-white/95"
										onclick={() => chat.handleRegenerateMessage()}
									>
										retry
									</button>
								{/snippet}
							</AssistantChatMessage>
						</div>
					{/if}

					<!-- streaming assistant is rendered within its run block -->
				</div>
			{:else}
				<!-- while data is loading, keep layout stable; loader is rendered as an overlay -->
				<div class="flex-1"></div>
			{/if}
		</div>

		{#if chat.showThreadLoader}
			<div
				class="pointer-events-none absolute inset-0 flex items-center justify-center"
				in:fade={{ duration: 120 }}
				out:fade={{ duration: 260 }}
			>
				<NokodoLoader className="opacity-80" shimmer expanded />
			</div>
		{/if}
	</div>

	<div class="absolute right-0 bottom-0 left-0 z-10 pt-4 pb-5" bind:this={chat.inputOverlay}>
		<div
			class="relative mx-auto w-full {device.isMobile ? '' : 'max-w-7xl'}"
			style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
		>
			<div class="transition-all duration-500 ease-in-out">
				<ChatInput
					bind:value={chat.inputValue}
					onSubmit={chat.handleSendMessage}
					onStop={chat.handleStopGeneration}
					isGenerating={chat.isGenerating}
					placeholder="send a message"
					focusToken={inputFocusToken}
					viewTransitionName="chat-input"
				/>
			</div>
		</div>
	</div>
</div>

{#if chat.confirmDeleteMessage}
	<div
		class="fixed inset-0 z-60 flex items-center justify-center bg-black/55 px-6"
		role="button"
		tabindex="0"
		onclick={() => {
			if (!chat.isDeletingMessage) {
				chat.confirmDeleteMessage = null
				chat.deleteMessageError = null
			}
		}}
		onkeydown={(e) => {
			if (chat.isDeletingMessage) return
			if (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') {
				chat.confirmDeleteMessage = null
				chat.deleteMessageError = null
			}
		}}
	>
		<div
			class="liquid-glass rounded-container w-full max-w-sm px-6 py-5 shadow-[0_32px_64px_rgba(12,10,30,0.6)]"
			role="dialog"
			aria-modal="true"
			tabindex="-1"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
		>
			<div class="relative z-10">
				<div class="text-lg font-semibold text-white/90">delete message?</div>
				<div class="mt-2 text-sm text-white/60">{chat.confirmDeleteMessage.preview}</div>

				{#if chat.deleteMessageError}
					<div
						class="mt-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70"
					>
						{chat.deleteMessageError}
					</div>
				{/if}

				<div class="mt-5 flex items-center justify-end gap-2">
					<button
						type="button"
						class="rounded-2xl border border-white/10 bg-transparent px-4 py-2 text-sm text-white/80 transition-colors duration-150 hover:bg-white/5"
						disabled={chat.isDeletingMessage}
						onclick={() => {
							chat.confirmDeleteMessage = null
							chat.deleteMessageError = null
						}}
					>
						cancel
					</button>
					<button
						type="button"
						class="rounded-2xl border border-white/10 bg-white/10 px-4 py-2 text-sm text-white/90 transition-colors duration-150 hover:bg-white/15 disabled:opacity-60"
						disabled={chat.isDeletingMessage}
						onclick={() => {
							void (async () => {
								if (!chat.confirmDeleteMessage) return
								chat.isDeletingMessage = true
								chat.deleteMessageError = null
								try {
									const ok = await chat.deleteUserMessage(
										chat.confirmDeleteMessage.id
									)
									if (!ok) {
										chat.deleteMessageError = 'could not delete message'
										return
									}
									chat.confirmDeleteMessage = null
								} catch {
									chat.deleteMessageError = 'could not delete message'
								} finally {
									chat.isDeletingMessage = false
								}
							})()
						}}
					>
						{#if chat.isDeletingMessage}
							<ShimmerText className="inline-block">deleting</ShimmerText>
						{:else}
							delete
						{/if}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}
