<script lang="ts">
	import { page } from '$app/state'
	import {
		blockHasStreamingAssistant,
		contentPartsToText,
		createChatState,
		getBlockFirstAssistant,
		getBlockResponseItems,
		getMessageCreatedAt,
		type ApiMessage,
	} from '$lib/chat'
	import AgentSelector from '$lib/components/chat/AgentSelector.svelte'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import ChatGptLoadingIndicator from '$lib/components/chat/ChatGptLoadingIndicator.svelte'
	import ChatInput from '$lib/components/chat/ChatInput.svelte'
	import ChatSidebarToggleButton from '$lib/components/chat/ChatSidebarToggleButton.svelte'
	import CopyButton from '$lib/components/chat/CopyButton.svelte'
	import MessageActionButton from '$lib/components/chat/MessageActionButton.svelte'
	import ToolExecutionCard from '$lib/components/chat/ToolExecutionCard.svelte'
	import TypingIndicator from '$lib/components/chat/TypingIndicator.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
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
	import { preferences } from '$lib/stores/preferences.svelte'
	import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
	import { untrack } from 'svelte'
	import { fade } from 'svelte/transition'

	// initialize chat state
	const chat = createChatState()
	const threadId = $derived(chat.thread?.id ?? null)

	// local UI state
	let didLoadAgents = $state(false)
	let inputFocusToken = $state(0)
	let lastInputFocusKey = $state<string | null>(null)

	// system chrome for agent selector
	const chrome = useSystemChrome()

	// set accent color for auto accent colors feature
	$effect(() => {
		accentStore.set('green')
	})

	// focus chat input when agent run completes (desktop only)
	let wasGenerating = $state(false)
	$effect(() => {
		const generating = chat.isGenerating
		if (wasGenerating && !generating && !device.isMobile) {
			// only focus if the textarea isn't already focused
			const active = document.activeElement
			const isTextareaFocused =
				active?.tagName === 'TEXTAREA' && active.closest('[data-chat-input]')
			if (!isTextareaFocused) {
				inputFocusToken += 1
			}
		}
		wasGenerating = generating
	})

	// effects: agents loading
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
		if (selectedAgent.id !== '') return
		if (agents.list.length === 0) return
		selectedAgent.set(selectedAgent.resolveDefault(agents.list))
	})

	// effects: thread loading and management
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

	// effects: Island context actions for agent selector
	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	// effects: real-time event subscriptions (tool, message, typing, run events)
	$effect(() => {
		if (!chat.thread) return
		return chat.subscribeToChatEvents(chat.thread.id)
	})

	// effects: pending create-and-run stream handoff
	$effect(() => {
		if (!chat.thread) return
		const pending = chatStore.pendingCreateAndRun
		if (!pending || pending.threadId !== chat.thread.id) return
		const stream = chatStore.consumePendingCreateAndRun(chat.thread.id)
		if (!stream) return
		chat.resumeCreateAndRun(stream, chat.thread.id)
	})

	// effects: pending chat start (for non-streaming handoffs)
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
			chat.streamingAssistant !== null ||
			chat.optimisticUserMessage !== null ||
			selectedAgent.id === ''
		)
			return
		const content = chatStore.consumePendingChatStart(chat.thread.id)
		if (!content) return
		chat.handleSendMessage(content)
	})

	// effects: input draft persistence
	// restore draft on mount
	$effect(() => {
		const threadId = page.params.id
		if (!threadId) return
		const draft = chatStore.getDraft(threadId)
		if (draft) chat.inputValue = draft
	})
	// sync input changes back to draft store
	$effect(() => {
		const threadId = page.params.id
		if (!threadId) return
		chatStore.setDraft(threadId, chat.inputValue)
	})

	// effects: typing event emission
	// fires typing.start every 3s while user is typing; typing.stop on idle/clear
	const hasInput = $derived(chat.inputValue.trim().length > 0)
	let typingStopTimeout: ReturnType<typeof setTimeout> | null = null
	let typingRepeatInterval: ReturnType<typeof setInterval> | null = null
	let isTyping = false
	$effect(() => {
		const tid = threadId
		const typing = hasInput
		if (!tid) return

		if (typing) {
			if (!isTyping) {
				// start typing: fire immediately + start 3s repeat
				isTyping = true
				chat.sendTypingEvent(tid, true)
				typingRepeatInterval = setInterval(() => {
					chat.sendTypingEvent(tid, true)
				}, 3000)
			}
			// reset idle stop timer on every keystroke
			if (typingStopTimeout) clearTimeout(typingStopTimeout)
			typingStopTimeout = setTimeout(() => {
				if (isTyping && tid) {
					isTyping = false
					if (typingRepeatInterval) clearInterval(typingRepeatInterval)
					typingRepeatInterval = null
					chat.sendTypingEvent(tid, false)
				}
			}, 3000)
		} else if (isTyping) {
			// input cleared: stop immediately
			isTyping = false
			if (typingStopTimeout) clearTimeout(typingStopTimeout)
			typingStopTimeout = null
			if (typingRepeatInterval) clearInterval(typingRepeatInterval)
			typingRepeatInterval = null
			chat.sendTypingEvent(tid, false)
		}

		return () => {
			if (typingStopTimeout) clearTimeout(typingStopTimeout)
			if (typingRepeatInterval) clearInterval(typingRepeatInterval)
			if (isTyping && tid) {
				chat.sendTypingEvent(tid, false)
				isTyping = false
			}
			typingStopTimeout = null
			typingRepeatInterval = null
		}
	})

	// effects: input overlay height tracking
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

	// effects: auto-scroll
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

		// dependency reads to track changes
		const streamingContent = chat.streamingAssistant?.content ?? ''
		const optimisticContent = chat.optimisticUserMessage?.content ?? ''
		const blocksCount = chat.runBlocks.length
		const keyboardOpen = device.virtualKeyboardOpen
		void streamingContent
		void optimisticContent
		void blocksCount
		void chat.inputOverlayHeight

		if (!chat.initialScrollDone) {
			chat.initialScrollDone = true
			void chat.queueScrollToBottom('auto')
			return
		}

		// when the virtual keyboard opens/closes the viewport shrinks/grows;
		// re-pin to bottom so the latest messages stay visible.
		if (keyboardOpen && chat.autoScroll) {
			void chat.queueScrollToBottom('auto')
		}

		// keep pinned to bottom when user was already there. covers both
		// local streaming and cross-session incoming messages
		if (chat.autoScroll) void chat.queueScrollToBottom('auto')
	})
</script>

{#snippet islandContextActions()}
	<AgentSelector
		selectedAgent={selectedAgent.id}
		onAgentChange={(agentId) => selectedAgent.set(agentId)}
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
		style="view-transition-name: thread-body; scrollbar-gutter: stable;"
		bind:this={chat.scrollContainer}
		onscroll={chat.handleScroll}
	>
		<div
			class="mx-auto flex min-h-full w-full flex-col {device.isMobile ? '' : 'max-w-7xl'}"
			style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); padding-top: var(--chrome-island-offset); padding-bottom: {Math.max(
				96,
				chat.inputOverlayHeight + 24
			)}px;"
		>
			{#if chat.isTemporaryChat && chat.hasLoadedBranch && chat.messages.length === 0 && !chat.optimisticUserMessage && !chat.streamingAssistant}
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
						<!-- spacer for scroll trigger area -->
						<div class="h-1"></div>
					{/if}
					{#each chat.runBlocks as block, i (block.runId)}
						{@const userItems = block.items.filter(
							(item) => item.kind === 'user' || item.kind === 'optimistic_user'
						)}
						{@const bubbleTailStyle =
							preferences.data.appearance.bubbleTailStyle ?? 'none'}
						<div class="space-y-3">
							<!-- user messages for this run (both real and optimistic) -->
							{#each userItems as item, itemIndex (item.kind === 'user' ? item.message.id : `${block.runId}-optimistic-${itemIndex}`)}
								{@const isFirst = itemIndex === 0}
								{@const isLast = itemIndex === userItems.length - 1}
								{@const showTail =
									bubbleTailStyle === 'none'
										? false
										: bubbleTailStyle === 'whatsapp'
											? isFirst
											: isLast}
								{#if item.kind === 'user'}
									{@const siblings =
										chat.messageChildren.get(item.message.parent_id ?? null) ??
										[]}
									<UserChatMessage
										content={contentPartsToText(item.message.content)}
										timestamp={getMessageCreatedAt(item.message)}
										align={item.align}
										siblingCount={siblings.length}
										currentSiblingIndex={siblings.indexOf(item.message.id)}
										onPrevious={() =>
											chat.switchBranch(item.message.id, 'prev')}
										onNext={() => chat.switchBranch(item.message.id, 'next')}
										tailStyle={bubbleTailStyle}
										{showTail}
									>
										{#snippet actions()}
											<CopyButton
												content={contentPartsToText(item.message.content)}
											/>
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
										tailStyle={bubbleTailStyle}
										{showTail}
									>
										{#snippet actions()}
											<CopyButton content={item.content} />
										{/snippet}
									</UserChatMessage>
								{/if}
							{/each}

							<!-- agent run: render ALL items in chronological order -->
							{#if getBlockResponseItems(block).length > 0 || (blockHasStreamingAssistant(block) && chat.streamingAssistant)}
								{@const responseItems = getBlockResponseItems(block)}
								{@const firstAssistant = getBlockFirstAssistant(block)}
								{@const isStreamingBlock =
									blockHasStreamingAssistant(block) && chat.streamingAssistant}
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
									isLastMessage={i === chat.runBlocks.length - 1}
									{siblingCount}
									{currentSiblingIndex}
									onPrevious={() => rootId && chat.switchBranch(rootId, 'prev')}
									onNext={() => rootId && chat.switchBranch(rootId, 'next')}
									content={isStreamingBlock && chat.streamingAssistant?.isError
										? (chat.streamingAssistant.errorMessage ??
											'something went wrong')
										: ''}
									tone={isStreamingBlock && chat.streamingAssistant?.isError
										? 'error'
										: 'default'}
									timestamp={firstAssistant
										? getMessageCreatedAt(firstAssistant)
										: isStreamingBlock
											? (chat.streamingAssistant?.timestamp ?? new Date())
											: undefined}
									isStreaming={Boolean(isStreamingBlock) &&
										!chat.streamingAssistant?.isError}
									isRunActive={chat.isGenerating}
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
														content={contentPartsToText(
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
															isStreaming={!chat.streamingAssistant
																.isError}
														/>
													</div>
												{:else if !chat.streamingAssistant.isError && !chat.hasActiveStreamingToolCalls}
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
										<CopyButton
											content={() => {
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
														contentPartsToText(i.message.content)
													)
													.join('\n\n')
												const streamText = isStreamingBlock
													? (chat.streamingAssistant?.content ?? '')
													: ''
												return (
													allText +
													(streamText ? '\n\n' + streamText : '')
												)
											}}
										/>
										{#if !isStreamingBlock}
											<MessageActionButton
												onclick={() => {
													// pass the user message ID so new responses branch from there
													const userMessageId =
														chat.findRunUserMessage(block)
													chat.handleRegenerateMessage(userMessageId)
												}}
												ariaLabel="retry"
											>
												<ArrowPath class="h-4 w-4" strokeWidth="2" />
											</MessageActionButton>
										{:else if chat.streamingAssistant?.isError}
											<button
												type="button"
												class="rounded-xl bg-transparent px-3 py-1.5 text-sm text-white/70 transition-colors hover:text-white/95"
												onclick={() => chat.handleRegenerateMessage()}
											>
												retry
											</button>
										{/if}
									{/snippet}
								</AssistantChatMessage>
							{/if}
						</div>
					{/each}

					<!-- streaming assistant is rendered within its run block -->

					<TypingIndicator typingUserIds={chat.typingUsers} />
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

	<div
		class="absolute right-0 bottom-0 left-0 z-10 pt-4 {device.virtualKeyboardOpen &&
		device.isMobile
			? 'pb-2'
			: 'pb-6'}"
		bind:this={chat.inputOverlay}
	>
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
