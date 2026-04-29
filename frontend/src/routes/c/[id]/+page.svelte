<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { getApiBaseUrl } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import {
		blockHasStreamingAssistant,
		computeBlockCitations,
		contentPartsToText,
		createChatState,
		extractFileParts,
		extractMediaParts,
		fetchThreadAccessLevel,
		getBlockFirstAssistant,
		getBlockResponseItems,
		getMessageCreatedAt,
		groupResponseItems,
		hasAttachmentParts,
		pendingAttachmentsToFileParts,
		pendingAttachmentsToMediaParts,
		type ApiMessage,
	} from '$lib/chat'
	import AgentSelector from '$lib/components/chat/AgentSelector.svelte'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import ChatGptLoadingIndicator from '$lib/components/chat/ChatGptLoadingIndicator.svelte'
	import ChatInput from '$lib/components/chat/ChatInput.svelte'
	import ChatSidebarToggleButton from '$lib/components/chat/ChatSidebarToggleButton.svelte'
	import CitationSourcesModal from '$lib/components/chat/CitationSourcesModal.svelte'
	import CitationSourcesPill from '$lib/components/chat/CitationSourcesPill.svelte'
	import CopyButton from '$lib/components/chat/CopyButton.svelte'
	import FloatingButtons from '$lib/components/chat/FloatingButtons.svelte'
	import MediaAttachments from '$lib/components/chat/MediaAttachments.svelte'
	import MessageActionButton from '$lib/components/chat/MessageActionButton.svelte'
	import RegenerateMenu from '$lib/components/chat/RegenerateMenu.svelte'
	import SteeringQueue from '$lib/components/chat/SteeringQueue.svelte'
	import { ToolGroup } from '$lib/components/chat/tools'
	import TypingIndicator from '$lib/components/chat/TypingIndicator.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte'
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
	import { session } from '$lib/stores/session.svelte'
	import { untrack } from 'svelte'
	import { SvelteDate } from 'svelte/reactivity'
	import { fade } from 'svelte/transition'

	// initialize chat state
	const chat = createChatState()
	const threadId = $derived(chat.thread?.id ?? null)

	// local UI state
	let didLoadAgents = $state(false)
	let inputFocusToken = $state(0)
	let lastInputFocusKey = $state<string | null>(null)
	let isReadOnly = $state(false)

	// citation sources modal state
	type Citation = components['schemas']['Citation']
	let sourcesModalCitations = $state<Citation[] | null>(null)

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
		if (!session.isLoggedIn) {
			didLoadAgents = false
			return
		}
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

			// if a pending create-and-run targets this thread, skip the API fetch:
			// the thread doesn't exist on the backend yet. use the optimistic stub
			// from the cache and let the pending-stream handoff effect handle the rest.
			const pending = chatStore.pendingCreateAndRun
			if (pending && pending.threadId === threadId) {
				const cached = chatStore.threadCache.get(threadId)
				if (cached) {
					chat.setThread(cached)
					chatStore.activeThread = cached
				}
				chat.optimisticUserMessage = {
					text: pending.text,
					attachments: pending.attachments,
					timestamp: new SvelteDate(),
				}
				chat.viewingStreamingBranch = true
				chat.rebuildRunBlocks()
				chat.isThreadLoading = false
				chat.hasLoadedBranch = true
				return () => {
					chat.clearThread()
				}
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

	// effects: resolve read-only access for non-owner threads
	$effect(() => {
		const thread = chat.thread
		const userId = session.currentUser?.id
		if (!thread || !userId) {
			isReadOnly = false
			return
		}
		if (thread.owner_id === userId) {
			isReadOnly = false
			return
		}
		// non-owner: fetch effective access level
		let cancelled = false
		void fetchThreadAccessLevel(thread.id)
			.then((level) => {
				if (cancelled) return
				isReadOnly = !level || level === 'reader'
			})
			.catch(() => {
				if (!cancelled) isReadOnly = true
			})
		return () => {
			cancelled = true
		}
	})

	// effects: real-time event subscriptions (tool, message, typing, run events)
	$effect(() => {
		if (!chat.thread) return
		return chat.subscribeToChatEvents(chat.thread.id)
	})

	// effects: navigate away when thread is deleted (e.g. from another session)
	$effect(() => {
		if (chat.thread) return
		if (!page.params.id) return
		// thread was nulled while we're on a /c/[id] route - redirect home
		if (chat.isThreadLoading) return
		if (chat.hasLoadedBranch === false && !chatStore.pendingCreateAndRun) return
		void goto(resolve('/'), { replaceState: true })
	})

	// effects: pending create-and-run stream handoff
	$effect(() => {
		if (!chat.thread) return
		const pending = chatStore.pendingCreateAndRun
		if (!pending || pending.threadId !== chat.thread.id) return
		const stream = chatStore.consumePendingCreateAndRun(chat.thread.id)
		if (!stream) return
		const tid = chat.thread.id
		chat.resumeCreateAndRun(stream, tid).then((result) => {
			if (result?.resolvedThreadId && result.resolvedThreadId !== tid) {
				// backend assigned a different thread ID (client ID conflict) - redirect
				void goto(resolve(`/c/${result.resolvedThreadId}`), { replaceState: true })
			}
		})
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
		const optimisticContent = chat.optimisticUserMessage?.text ?? ''
		const blocksCount = chat.runBlocks.length
		const keyboardOpen = device.virtualKeyboardOpen
		void streamingContent
		void optimisticContent
		void blocksCount
		void chat.inputOverlayHeight
		// track tool call argument changes so scroll sticks during tool streaming
		void chat.streamingAssistant?.toolCalls

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
			<LiquidGlass
				tag="button"
				type="button"
				class="border-foreground/10 text-foreground/85 hover:bg-foreground/10 hover:text-foreground pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full border transition-colors"
				cornerRadius={18}
				aria-label="scroll to bottom"
				onpointerdown={(e: PointerEvent) => e.preventDefault()}
				onclick={() => {
					chat.queueScrollToBottom('smooth')
					chat.autoScroll = true
				}}
			>
				<ArrowUp class="h-4 w-4 rotate-180" />
			</LiquidGlass>
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
			style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); padding-top: var(--chrome-island-offset); padding-bottom: {chat.inputOverlayHeight}px;"
		>
			{#if chat.isTemporaryChat && chat.hasLoadedBranch && chat.messages.length === 0 && !chat.optimisticUserMessage && !chat.streamingAssistant}
				<div class="flex flex-1 items-center justify-center py-16">
					<div class="max-w-md text-center">
						<div
							class="bg-foreground/5 text-foreground/85 mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full"
						>
							<EyeSlash class="h-7 w-7" />
						</div>
						<h2 class="text-foreground/90 text-2xl font-semibold">
							temporary chat enabled
						</h2>
						<p class="text-foreground/60 mt-2 text-sm">
							send a message to start. messages here won't be saved.
						</p>
					</div>
				</div>
			{:else if chat.hasLoadedBranch && !chat.hasRenderableMessages}
				<div class="flex flex-1 items-center justify-center py-16">
					<div class="max-w-md text-center">
						<div
							class="bg-foreground/5 text-foreground/85 mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full"
						>
							<EyeSlash class="h-7 w-7" />
						</div>
						<h2 class="text-foreground/90 text-2xl font-semibold">no messages yet</h2>
						<p class="text-foreground/60 mt-2 text-sm">
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
									{@const meta = (item.message.metadata_ ?? {}) as Record<
										string,
										unknown
									>}
									{@const viewTransitionName =
										meta.steering_state === 'injected'
											? `steering-message-${item.message.id}`
											: undefined}
									<UserChatMessage
										content={contentPartsToText(item.message.content)}
										contentParts={item.message.content}
										timestamp={getMessageCreatedAt(item.message)}
										align={item.align}
										siblingCount={siblings.length}
										currentSiblingIndex={siblings.indexOf(item.message.id)}
										onPrevious={() =>
											chat.switchBranch(item.message.id, 'prev')}
										onNext={() => chat.switchBranch(item.message.id, 'next')}
										tailStyle={bubbleTailStyle}
										{showTail}
										{viewTransitionName}
										onEditSave={item.align === 'right'
											? (c) => chat.handleSaveEditMessage(item.message.id, c)
											: undefined}
										onEditSaveAsCopy={item.align === 'right'
											? (c) =>
													chat.handleSaveAsCopyMessage(item.message.id, c)
											: undefined}
									>
										{#snippet actions()}
											<CopyButton
												content={contentPartsToText(item.message.content)}
											/>
											{#if item.align === 'right'}
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
									{@const oMedia = pendingAttachmentsToMediaParts(
										item.attachments
									)}
									{@const oFiles = pendingAttachmentsToFileParts(
										item.attachments
									)}
									<UserChatMessage
										content={item.text}
										optimisticMediaParts={oMedia}
										optimisticFileParts={oFiles}
										timestamp={item.timestamp}
										tailStyle={bubbleTailStyle}
										{showTail}
									>
										{#snippet actions()}
											<CopyButton content={item.text} />
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
								{@const blockCitations = computeBlockCitations(
									responseItems,
									isStreamingBlock ? chat.streamingAssistant : null,
									chat.citationSources
								)}
								{@const rootId = block.responseRootId}
								{@const rootMessage = rootId ? chat.messageTree.get(rootId) : null}
								{@const blockParentId =
									rootMessage?.parent_id ??
									(isStreamingBlock ? chat.streamingAssistantParentId : null) ??
									null}
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
									block.agentId ??
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
										: rootMessage
											? getMessageCreatedAt(rootMessage)
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
										{@const segments = groupResponseItems(responseItems)}
										<div class="relative">
											{#each segments as segment, idx (idx)}
												{#if segment.type === 'assistant'}
													{#if hasAttachmentParts(segment.item.message.content)}
														<div class="mb-2">
															<MediaAttachments
																mediaParts={extractMediaParts(
																	segment.item.message.content,
																	getApiBaseUrl()
																)}
																fileParts={extractFileParts(
																	segment.item.message.content,
																	getApiBaseUrl()
																)}
															/>
														</div>
													{/if}
													<div
														class="assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word"
													>
														<MarkdownRenderer
															content={contentPartsToText(
																segment.item.message.content
															)}
															isStreaming={false}
															citations={chat.citationSources.get(
																segment.item.message.id
															) ?? []}
														/>
													</div>
												{:else if segment.type === 'tool_group'}
													{@const toolExecs = segment.toolCallIds
														.map((id) => chat.getToolExecution(id))
														.filter(
															(e): e is NonNullable<typeof e> =>
																e != null
														)}
													{#if toolExecs.length > 0}
														<ToolGroup executions={toolExecs} />
													{/if}
												{:else if segment.type === 'streaming_assistant' && chat.streamingAssistant}
													{@const hasActiveTools = segments.some(
														(s) =>
															s.type === 'tool_group' &&
															s.toolCallIds.some((id) => {
																const e = chat.getToolExecution(id)
																return (
																	e != null &&
																	(e.status === 'pending' ||
																		e.status === 'running')
																)
															})
													)}
													{#if chat.streamingAssistant.content.trim()}
														<div
															class="assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word"
														>
															<MarkdownRenderer
																content={chat.streamingAssistant
																	.content}
																isStreaming={!chat
																	.streamingAssistant.isError}
																citations={chat.citationSources.get(
																	chat.streamingAssistant
																		.messageId
																) ?? []}
															/>
														</div>
													{:else if !chat.streamingAssistant.isError && !chat.hasActiveStreamingToolCalls && !hasActiveTools}
														<div
															class="assistant-markdown text-foreground/60 text-[0.95rem] leading-relaxed"
														>
															<div class="my-3">
																<ChatGptLoadingIndicator />
															</div>
														</div>
													{/if}
												{/if}
											{/each}
										</div>
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
											<RegenerateMenu
												onRegenerate={(prompt) => {
													const userMessageId =
														chat.findRunUserMessage(block)
													chat.handleRegenerateMessage(
														userMessageId,
														prompt
													)
												}}
											/>
										{:else if chat.streamingAssistant?.isError}
											<button
												type="button"
												class="border-destructive/30 text-destructive hover:bg-destructive/10 flex items-center gap-1.5 rounded-xl border bg-transparent px-3 py-1.5 text-sm font-medium transition-colors"
												onclick={() => chat.handleRegenerateMessage()}
											>
												<ArrowPath class="size-3.5" strokeWidth="2.5" />
												retry
											</button>
										{/if}
									{/snippet}

									{#snippet persistentActions()}
										{#if blockCitations.length > 0}
											<CitationSourcesPill
												citations={blockCitations}
												onclick={() => {
													sourcesModalCitations = blockCitations
												}}
											/>
										{/if}
									{/snippet}
								</AssistantChatMessage>
							{/if}
						</div>
					{/each}

					<!-- streaming assistant is rendered within its run block -->

					<TypingIndicator typingUserIds={chat.typingUsers} />
					<FloatingButtons
						{threadId}
						onQuote={(content) => {
							chat.inputValue = content
						}}
					/>
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
				<SteeringQueue
					messages={chat.queuedSteeringMessages}
					onDrop={(runId, messageId) => chat.dropSteering(runId, messageId)}
				/>
				<ChatInput
					bind:value={chat.inputValue}
					onSubmit={chat.handleSendMessage}
					onStop={chat.handleStopGeneration}
					isGenerating={chat.isGenerating}
					placeholder="send a message"
					disabled={isReadOnly}
					focusToken={inputFocusToken}
					viewTransitionName="chat-input"
					threadAttachments={chat.threadAttachments}
					onToggleAttachmentStatus={chat.toggleAttachmentStatus}
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
				<div class="text-foreground/90 text-lg font-semibold">delete message?</div>
				<div class="text-foreground/60 mt-2 text-sm">
					{chat.confirmDeleteMessage.preview}
				</div>
				<div class="text-foreground/40 mt-2 text-xs">
					this will also delete all replies and branches below this message.
				</div>

				{#if chat.deleteMessageError}
					<div
						class="border-foreground/10 bg-foreground/5 text-foreground/70 mt-3 rounded-2xl border px-3 py-2 text-sm"
					>
						{chat.deleteMessageError}
					</div>
				{/if}

				<div class="mt-5 flex items-center justify-end gap-2">
					<button
						type="button"
						class="border-foreground/10 text-foreground/80 hover:bg-foreground/5 cursor-pointer rounded-2xl border bg-transparent px-4 py-2 text-sm transition-colors duration-150 disabled:cursor-default"
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
						class="border-foreground/10 bg-foreground/10 text-foreground/90 hover:bg-foreground/15 cursor-pointer rounded-2xl border px-4 py-2 text-sm transition-colors duration-150 disabled:cursor-default disabled:opacity-60"
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

<CitationSourcesModal
	open={sourcesModalCitations !== null}
	citations={sourcesModalCitations ?? []}
	onClose={() => {
		sourcesModalCitations = null
	}}
/>
