<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import {
		EntranceController,
		inputBoxMorphSource,
		type EntranceMode,
	} from '$lib/animations/entrance.svelte'
	import { getApiBaseUrl } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import { scrollGesture } from '$lib/attachments/scrollgesture'
	import {
		beginningOfChatSegments,
		blockHasStreamingAssistant,
		branchAlternativeCount,
		composingFaces,
		computeBlockCitations,
		contentPartsToText,
		createChatState,
		createTypingSignal,
		extractAttachmentRefs,
		extractFileParts,
		extractMediaParts,
		getBlockFirstAssistant,
		getBlockResponseItems,
		getBlockSystemEvents,
		getBlockTimeHeader,
		getMessageCreatedAt,
		getUserRunItemTimestamp,
		groupResponseItems,
		hasAttachmentParts,
		isFailureOutstanding,
		pendingAttachmentsToFileParts,
		pendingAttachmentsToMediaParts,
		siblingIdsOfKind,
		systemEventSegments,
		systemEventUserIds,
		ThreadNotFoundError,
		timeHeaderSegments,
		unarchiveThread,
		type ApiMessage,
		type MessageAuthor,
		type RunItem,
		type SystemNameResolver,
		type TypingSignal,
	} from '$lib/chat'
	import type { RunModifiers } from '$lib/chat/attachments'
	import { cancelMessageReveal, messageAnchor, revealMessage } from '$lib/chat/messageFocus'
	import { RunActivity } from '$lib/components/chat/activities'
	import AgentSelector from '$lib/components/chat/AgentSelector.svelte'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import AttachmentRefs from '$lib/components/chat/AttachmentRefs.svelte'
	import ChatGptLoadingIndicator from '$lib/components/chat/ChatGptLoadingIndicator.svelte'
	import ChatInput from '$lib/components/chat/ChatInput.svelte'
	import ChatSidebarToggleButton from '$lib/components/chat/ChatSidebarToggleButton.svelte'
	import ChatSystemRow from '$lib/components/chat/ChatSystemRow.svelte'
	import CitationSourcesModal from '$lib/components/chat/CitationSourcesModal.svelte'
	import CitationSourcesPill from '$lib/components/chat/CitationSourcesPill.svelte'
	import ConversationIdentity from '$lib/components/chat/ConversationIdentity.svelte'
	import CopyButton from '$lib/components/chat/CopyButton.svelte'
	import FloatingButtons from '$lib/components/chat/FloatingButtons.svelte'
	import MediaAttachments from '$lib/components/chat/MediaAttachments.svelte'
	import RegenerateMenu from '$lib/components/chat/RegenerateMenu.svelte'
	import ReplyPreview from '$lib/components/chat/ReplyPreview.svelte'
	import RunFailureEntry from '$lib/components/chat/RunFailureEntry.svelte'
	import SteeringQueue from '$lib/components/chat/SteeringQueue.svelte'
	import { ToolGroup } from '$lib/components/chat/tools'
	import TypingIndicator from '$lib/components/chat/TypingIndicator.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import ViewportMetricsReadout from '$lib/components/chat/ViewportMetricsReadout.svelte'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import ArrowUpTray from '$lib/components/icons/ArrowUpTray.svelte'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import ChatPlus from '$lib/components/icons/ChatPlus.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import Clock from '$lib/components/icons/Clock.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import MarkdownRenderer from '$lib/components/markdown/MarkdownRenderer.svelte'
	import ChatPropertiesModal from '$lib/components/modals/ChatPropertiesModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { useSidebar } from '$lib/contexts/sidebarContext.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { accentStore } from '$lib/stores/accent.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import { chat as chatStore, isPeopleThread, threadKind } from '$lib/stores/chat.svelte'
	import { device, visualViewportOvershoot } from '$lib/stores/device.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { canEditAccessLevel, resourceAccess } from '$lib/stores/resourceAccess.svelte'
	import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { conversationDisplay } from '$lib/utils/conversationDisplay'
	import { userDisplayName } from '$lib/utils/resourceAuthors'
	import { untrack } from 'svelte'
	import { SvelteDate } from 'svelte/reactivity'

	const chat = createChatState()
	const threadId = $derived(chat.thread?.id ?? null)

	// outgoing-bubble entrance, driven by the bubbleAnimation preference.
	const reducedMotion =
		typeof window !== 'undefined' &&
		typeof window.matchMedia === 'function' &&
		window.matchMedia('(prefers-reduced-motion: reduce)').matches
	const entranceMode = $derived.by((): EntranceMode => {
		if (reducedMotion) return 'none'
		return (preferences.data.appearance.bubbleAnimation ?? 'morph') as EntranceMode
	})
	const entrance = new EntranceController(() => entranceMode)
	let optimisticMsgEl = $state<HTMLElement | null>(null)
	let inputBoxEl = $state<HTMLElement | null>(null)
	// the optimistic bubble hides its own clock while the ghost is carrying it.
	const optimisticClockHidden = $derived(entrance.inFlight)
	// id of the steering row a morph ghost is currently flying into; that row is
	// hidden during the flight so the real bubble and the ghost don't both show.
	let morphingSteeringId = $state<string | null>(null)
	const hiddenSteeringId = $derived(entrance.inFlight ? morphingSteeringId : null)

	// the bubble of the newest steering-queue row, or null if the queue is empty.
	function lastSteeringBubble(): HTMLElement | null {
		const queue = document.querySelector('[aria-label="steering queue"]')
		if (!queue) return null
		const lastRow = queue.lastElementChild as HTMLElement | null
		return lastRow?.querySelector('[style*="steering-message-"]') as HTMLElement | null
	}

	// the outgoing user bubble, resolved across the optimistic -> persisted swap:
	// once the backend persist replaces the optimistic item, optimisticMsgEl goes
	// stale, so fall back to the newest right-aligned (own) message bubble in the
	// list.  lets the live-tracking morph keep its target after the swap.
	function lastOutgoingBubble(): HTMLElement | null {
		if (!messageListEl) return null
		const articles = messageListEl.querySelectorAll('[role="article"].ml-auto')
		const last = articles[articles.length - 1] as HTMLElement | undefined
		return (last?.querySelector('.bubble-content') as HTMLElement | null) ?? null
	}

	// a user message that arrived live from another session (cross-device sync)
	// plays the fallback entrance once, on mount.  the mark is set by the WS
	// handler only for live tail-appends, so history / branch-switch / paging
	// never animate.  own sends already animated via the optimistic path.
	function revealOnSync(node: HTMLElement, id: string): void {
		if (chat.consumeMessageEntrance(id)) entrance.reveal(node)
	}

	// genuine user scroll gestures (wheel / touch) on the message container:
	// keeps the pin authoritative on scroll-up even while streaming keeps firing
	// programmatic scrolls, and avoids the a11y static-interaction warning.
	const detectUserScroll = scrollGesture((direction) => chat.onUserScrollGesture(direction))

	/** send wrapper: animates the outgoing bubble out of the input via the
	 *  entrance controller (mode from the bubbleAnimation preference). */
	async function handleChatSend(content: string, modifiers?: RunModifiers): Promise<void> {
		const trimmed = content.trim()
		const startsFreshRun =
			!chat.isGenerating &&
			chat.streamingAssistant === null &&
			chat.thread !== null &&
			selectedAgent.id !== ''
		const canAnimate =
			entranceMode !== 'none' && trimmed.length > 0 && typeof document !== 'undefined'

		if (!canAnimate) {
			chat.handleSendMessage(content, modifiers)
			return
		}

		const source = inputBoxMorphSource(inputBoxEl)
		if (startsFreshRun) {
			// not pinned to bottom: the bubble lands below the fold — fly the ghost
			// down and out of the viewport instead of into an off-screen target.
			if (!chat.autoScroll) {
				void chat.handleSendMessage(content, modifiers)
				await entrance.flyOutDown(source, trimmed)
				return
			}
			void chat.handleSendMessage(content, modifiers)
			// resolve the bubble across the optimistic -> persisted swap (optimisticMsgEl
			// goes stale once the persist replaces the element), so the tracking morph
			// keeps its target as the autoscroll + placeholder push it up mid-flight.
			const target = () =>
				(optimisticMsgEl?.querySelector('.bubble-content') as HTMLElement | null) ??
				lastOutgoingBubble()
			await entrance.morphTo(source, target, trimmed, () => chat.scrollToBottom('auto'))
		} else {
			// in-progress run: animate into the freshly-queued steering bubble.
			const queueLenBefore = chat.queuedSteeringMessages.length
			void chat.handleSendMessage(content, modifiers)
			if (chat.queuedSteeringMessages.length <= queueLenBefore) return
			// hide the just-enqueued row while a morph ghost flies into it (a no-op
			// in flyup mode, where inFlight stays false and the row animates in place).
			morphingSteeringId = chat.queuedSteeringMessages.at(-1)?.id ?? null
			try {
				await entrance.animateFrom(source, lastSteeringBubble, trimmed)
			} finally {
				morphingSteeringId = null
			}
		}
	}

	// local UI state
	let didLoadAgents = $state(false)
	let inputFocusToken = $state(0)
	let lastInputFocusKey = $state<string | null>(null)
	let lastChatRefreshVersion = 0
	let isReadOnly = $state(false)
	let threadNotFound = $state(false)
	let messageListEl = $state<HTMLDivElement | null>(null)
	let pageShellEl = $state<HTMLDivElement | null>(null)
	/**
	 * px the page shell overhangs the visible viewport bottom. in-browser android
	 * keeps the layout viewport full-height when the keyboard opens, so the shell's
	 * `bottom: 0` edge - and the composer pinned to it - can end under the keyboard.
	 * everything anchored to that edge is lifted by this instead.
	 */
	let bottomOverhang = $state(0)

	/** how long the keyboard animation runs before the viewport numbers settle. */
	const VIEWPORT_SETTLE_MS = 300
	let overhangSettleFrame: number | null = null
	let overhangSettleTimer: ReturnType<typeof setTimeout> | null = null

	function cancelOverhangSettle() {
		if (overhangSettleFrame !== null) cancelAnimationFrame(overhangSettleFrame)
		if (overhangSettleTimer !== null) clearTimeout(overhangSettleTimer)
		overhangSettleFrame = null
		overhangSettleTimer = null
	}

	/**
	 * the rect and the viewport numbers must come from the SAME layout, so both are
	 * read live here rather than off the store snapshot. `settle` re-measures after
	 * the keyboard animation: android fires viewport events all the way through it
	 * and the last one is not reliably the settled state.
	 */
	function measureBottomOverhang(settle = false) {
		const shell = pageShellEl
		if (!shell) {
			bottomOverhang = 0
			return
		}
		bottomOverhang = visualViewportOvershoot(
			shell.getBoundingClientRect().bottom,
			window.visualViewport?.height ?? window.innerHeight,
			window.visualViewport?.offsetTop ?? 0
		)
		if (!settle) return
		cancelOverhangSettle()
		overhangSettleFrame = requestAnimationFrame(() => {
			overhangSettleFrame = null
			measureBottomOverhang()
		})
		overhangSettleTimer = setTimeout(() => {
			overhangSettleTimer = null
			measureBottomOverhang()
		}, VIEWPORT_SETTLE_MS)
	}

	let bottomHoldFrame: number | null = null
	let bottomHoldUntil = 0

	/**
	 * hold the transcript on its EXACT bottom across a viewport resize.
	 *
	 * the keyboard resizes the transcript itself now
	 * (`interactive-widget=resizes-content`): the browser clamps `scrollTop` to the
	 * new maximum, then the composer's keyboard padding swap grows the transcript's
	 * bottom padding back a frame later - so the view ends a few px short of the
	 * bottom with no scroll event left to correct it. worse, the clamp's own scroll
	 * event is dispatched in the SAME frame as the resize (resize steps run before
	 * scroll steps), before any store sync, and the pin reads it as the reader
	 * scrolling away. so this arms the existing programmatic-scroll suppression
	 * synchronously from the resize, then re-lands on the bottom every frame until
	 * the keyboard animation has settled.
	 *
	 * a genuine gesture during the settle still wins: it releases the pin itself,
	 * which ends the hold on the next frame.
	 */
	function holdBottomThroughSettle() {
		if (!chat.autoScroll) return
		chat.markProgrammaticScroll('auto')
		bottomHoldUntil = performance.now() + VIEWPORT_SETTLE_MS
		if (bottomHoldFrame !== null) return
		const step = () => {
			bottomHoldFrame = null
			if (!chat.autoScroll) return
			chat.scrollToBottom('auto')
			if (performance.now() < bottomHoldUntil) bottomHoldFrame = requestAnimationFrame(step)
		}
		bottomHoldFrame = requestAnimationFrame(step)
	}

	function cancelBottomHold() {
		if (bottomHoldFrame !== null) cancelAnimationFrame(bottomHoldFrame)
		bottomHoldFrame = null
	}

	let isUnarchivingThread = $state(false)
	// a latch, deliberately not reactive: the anchor effect writes it, and as
	// $state that write would re-run the effect and cancel its own reveal.
	let handledAnchorKey: string | null = null

	/** grace period for a search anchor whose message is still rendering. */
	const ANCHOR_REVEAL_WAIT_MS = 1500

	/** `?vvdebug` on the url shows the live viewport metrics readout (F101). */
	const viewportDebug = $derived(page.url.searchParams.has('vvdebug'))

	/** message the composer is currently replying to, if any. */
	let replyDraft = $state<ApiMessage | null>(null)
	const replyDraftAuthor = $derived(authorNameOf(replyDraft))

	// citation sources modal state
	type Citation = components['schemas']['Citation']
	let sourcesModalCitations = $state<Citation[] | null>(null)

	// people conversation header / participant panel
	// the island identity opens the chat info modal; the members panel is one of
	// its tiles, so both surfaces stay reachable from the header.
	let infoOpen = $state(false)
	const isPeopleConversation = $derived(chat.thread ? isPeopleThread(chat.thread) : false)
	const conversationKind = $derived(chat.thread ? threadKind(chat.thread) : 'solo')
	const conversationHeader = $derived(
		chat.thread && isPeopleConversation
			? conversationDisplay(chat.thread, session.currentUserId)
			: null
	)

	// who is composing in this thread right now. a solo chat has nobody else to
	// wait for, so the bubble only exists where more than one person can write.
	const composers = $derived(
		isPeopleConversation && threadId
			? composingFaces(
					chatStore.composingUserIds(threadId),
					chat.participantById,
					chat.currentUserId
				)
			: []
	)

	// system rows name people the roster may no longer hold - somebody removed
	// from the chat is still named by the row that removed them - so an id the
	// roster cannot answer for is looked up once through the session store.
	const systemNameResolver = $derived.by((): SystemNameResolver => {
		const participants = chat.participantById
		const threadAgents = chat.threadAgentById
		const groups = (chat.thread?.participants ?? []).filter(
			(participant) => participant.kind === 'group'
		)
		return {
			currentUserId: chat.currentUserId,
			name: (id) => {
				const known = participants.get(id) ?? threadAgents.get(id)
				if (known) return known.name
				const group = groups.find((participant) => participant.group.id === id)
				if (group) return group.group.name
				const summary = session.getUserSummary(id)
				return summary ? userDisplayName(summary) : null
			},
		}
	})

	$effect(() => {
		const ids = systemEventUserIds(chat.systemEvents.values())
		const owner = chat.thread?.owner_id
		if (owner) ids.push(owner)
		if (ids.length > 0) void session.ensureUsers(ids)
	})

	/**
	 * when the transcript starts.
	 *
	 * the in-flow headers only mark SILENCES between blocks, so the opening
	 * stamp belongs to whoever knows the top is really the beginning - here.
	 */
	const transcriptOpensAt = $derived(chat.runBlocks[0]?.startedAt ?? null)

	/** the row that opens the transcript, once its top really is the beginning. */
	const beginningSegments = $derived.by(() => {
		const thread = chat.thread
		if (!thread) return []
		const creator = thread.owner_id
			? thread.owner_id === chat.currentUserId
				? 'you'
				: systemNameResolver.name(thread.owner_id)
			: null
		if (conversationKind === 'group') {
			return beginningOfChatSegments({
				kind: 'group',
				counterpartName: null,
				chatName: thread.title?.trim() || (conversationHeader?.title ?? null),
				creatorName: creator,
			})
		}
		if (conversationKind === 'direct') {
			return beginningOfChatSegments({
				kind: 'direct',
				counterpartName: conversationHeader?.faces[0]?.label ?? null,
				chatName: null,
				creatorName: null,
			})
		}
		// a solo chat is a chat with ONE assistant, so it opens the same way a DM
		// does - and stays silent when the thread does not name exactly one.
		const soloAgents = [...chat.threadAgentById.values()]
		return beginningOfChatSegments({
			kind: 'solo',
			counterpartName: soloAgents.length === 1 ? soloAgents[0].name : null,
			chatName: null,
			creatorName: null,
		})
	})

	// invocation: in a multi-writer thread the send button only sends, so an
	// agent has to be armed explicitly for the next send. one agent only.
	let armedAgentId = $state<string | null>(null)
	// any of the user's agents can be invoked; the run brings it into the thread,
	// exactly as picking one in a solo chat does. participants list first.
	const invokableAgents = $derived.by((): MessageAuthor[] => {
		if (!isPeopleConversation) return []
		const others = agents.list
			.filter((agent) => !chat.threadAgentById.has(agent.id))
			.map(
				(agent): MessageAuthor => ({
					id: agent.id,
					name: agent.name,
					avatarUrl: agent.profile_image_url ?? null,
					isAgent: true,
				})
			)
		return [...chat.threadAgentById.values(), ...others]
	})
	// swipe-up sends straight to the selected agent (or the first invokable one).
	const swipeInvokeAgent = $derived(
		invokableAgents.find((agent) => agent.id === selectedAgent.id) ?? invokableAgents[0] ?? null
	)
	// the id, not the thread object: a roster refresh must not disarm mid-compose.
	const armedThreadId = $derived(chat.thread?.id ?? null)
	$effect(() => {
		void armedThreadId
		armedAgentId = null
	})

	// archived is private per-user state, no longer on the shared thread roster.
	// TODO(frontend): source this from the per-user thread-state store once the
	// by-user-status endpoints are wired in; the header unarchive affordance
	// stays hidden until then (archiving itself still works via threadActions).
	const threadArchivedForMe = false

	// system chrome for agent selector
	const chrome = useSystemChrome()
	const sidebar = useSidebar() as { selectChat?: (id: string | null) => void } | null

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
		if (threadNotFound) {
			pageTitleStore.pageTitle = 'page not found'
			return
		}
		const thread = chat.thread
		if (!thread) {
			pageTitleStore.pageTitle = ''
			return
		}
		const t = thread.title
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
			threadNotFound = false
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
			// a search hit names the page to open; without one the loader opens
			// at the reader's last-read message.
			const searchAnchor = page.url.searchParams.get('message')

			void (async () => {
				try {
					const loaded = await chat.loadTree(
						threadId,
						searchAnchor ? { anchorMessageId: searchAnchor } : undefined
					)
					if (cancelled) return
					chat.hasLoadedBranch = loaded
				} catch (err) {
					if (cancelled) return
					if (err instanceof ThreadNotFoundError) {
						threadNotFound = true
						chat.hasLoadedBranch = false
						return
					}
					console.error('failed to load thread', err)
					chat.hasLoadedBranch = false
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

	$effect(() => {
		const version = chatStore.refreshVersion
		const routeThreadId = page.params.id
		if (version === 0 || version === lastChatRefreshVersion) return
		if (!routeThreadId || !chat.hasLoadedBranch) return
		lastChatRefreshVersion = version

		let cancelled = false
		untrack(() => {
			void (async () => {
				try {
					// a refresh keeps the window the reader is on, so it anchors
					// on the current leaf rather than re-resolving last-read.
					const loaded = await chat.loadTree(routeThreadId, {
						anchorMessageId: chat.currentLeafId,
					})
					if (!cancelled) chat.hasLoadedBranch = loaded
				} catch (err) {
					if (cancelled) return
					if (err instanceof ThreadNotFoundError) {
						threadNotFound = true
						chat.hasLoadedBranch = false
						return
					}
					console.error('failed to refresh thread', err)
				}
			})()
		})

		return () => {
			cancelled = true
		}
	})

	// effects: Island context actions for agent selector
	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	// a conversation is a different viewing mode: the chat sidebar neither lists
	// it nor can navigate to it, so the whole chat shell steps aside.
	$effect(() => {
		chrome.setChatShell(!isPeopleConversation)
		return () => chrome.setChatShell(true)
	})

	// effects: resolve read-only access for non-owner threads
	$effect(() => {
		const thread = chat.thread
		if (!thread) {
			isReadOnly = false
			return
		}
		isReadOnly = !canEditAccessLevel(resourceAccess.level('thread', thread.id, thread.owner_id))
		let cancelled = false
		void resourceAccess
			.ensure('thread', thread.id, thread.owner_id)
			.then((level) => {
				if (cancelled) return
				isReadOnly = !canEditAccessLevel(level)
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
		if (threadNotFound) return
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

	// effects: typing signal emission
	// the signal owns the cadence (heartbeat while composing, stop on clear,
	// send or blur); this page only tells it what the composer looks like now.
	let composerFocused = $state(false)
	let typingSignal: TypingSignal | null = null
	$effect(() => {
		const tid = threadId
		if (!tid) return
		const signal = createTypingSignal((typing) => chat.sendTypingEvent(tid, typing))
		typingSignal = signal
		return () => {
			signal.stop()
			typingSignal = null
		}
	})
	$effect(() => {
		// reads the draft itself, not a "has text" boolean: a deletion is composer
		// activity exactly like a keystroke, and both must refresh the receiver TTL.
		const draft = chat.inputValue
		typingSignal?.update(draft, composerFocused && !isReadOnly)
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
		// border box, not the default content box: the overlay's own padding is
		// what changes when the virtual keyboard opens (pb-6 <-> pb-2), and a
		// content-box observer never reports that - the published height would
		// stay 16px stale and the transcript's padding with it.
		const ro = new ResizeObserver(update)
		ro.observe(overlay, { box: 'border-box' })
		return () => ro.disconnect()
	})

	// effects: keep the composer on the visible viewport bottom, not the layout one.
	// android resizes its layout viewport for the keyboard now
	// (`interactive-widget=resizes-content` in app.html), so this measures 0 there;
	// ios ignores that meta and still needs the lift.
	$effect(() => {
		void device.viewportHeight
		void device.viewportOffsetTop
		// the layout viewport can move without the visual one (url bar, rotation)
		void device.height
		measureBottomOverhang(true)
	})

	$effect(() => {
		const shell = pageShellEl
		if (!shell) return
		// the shell's own box can change with no viewport metric changing at all
		// (a late `--app-height`, a safe-area inset landing), and a document scroll
		// moves its client rect while both viewports stay put - neither reaches the
		// device store, so neither would re-run the effect above.
		const onGeometry = () => measureBottomOverhang(true)
		const observer = new ResizeObserver(onGeometry)
		observer.observe(shell)
		window.addEventListener('scroll', onGeometry, { passive: true })
		return () => {
			observer.disconnect()
			window.removeEventListener('scroll', onGeometry)
			cancelOverhangSettle()
		}
	})

	// effects: a viewport resize is not the reader scrolling away (see
	// holdBottomThroughSettle). listened to directly - the device store coalesces
	// its sync into a rAF, which is already a frame later than the scroll event
	// the resize produces.
	$effect(() => {
		const onViewportResize = () => holdBottomThroughSettle()
		window.addEventListener('resize', onViewportResize, { passive: true })
		window.visualViewport?.addEventListener('resize', onViewportResize, { passive: true })
		return () => {
			window.removeEventListener('resize', onViewportResize)
			window.visualViewport?.removeEventListener('resize', onViewportResize)
			cancelBottomHold()
		}
	})

	$effect(() => {
		if (!messageListEl) return
		const target = messageListEl
		const observer = new ResizeObserver(() => {
			// content height drives whether a scroll affordance means anything
			chat.onContentResize()
			if (chat.autoScroll) void chat.queueScrollToBottom('auto')
		})
		observer.observe(target)
		if (chat.scrollContainer) observer.observe(chat.scrollContainer)
		return () => observer.disconnect()
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

	/**
	 * the message a reply quotes, or null when it is off the loaded branch.
	 * a reply is a semantic anchor, so the target may legitimately be absent.
	 */
	function replyTarget(message: ApiMessage): ApiMessage | null {
		const id = message.reply_to_message_id
		if (!id) return null
		return chat.messageTree.get(id) ?? null
	}

	/**
	 * the message an answer quotes, or null when the quote would be redundant.
	 *
	 * with a single writer every answer follows the message it answers, so the
	 * quote would restate the line directly above it on every turn. answers
	 * that reached further back still quote, and multi-writer threads always do.
	 */
	function answeredMessage(
		assistant: ApiMessage | null,
		above: RunItem | undefined
	): ApiMessage | null {
		if (!assistant) return null
		const target = replyTarget(assistant)
		if (!target) return null
		if (isPeopleConversation) return target
		if (above?.kind === 'user' && above.message.id === target.id) return null
		return target
	}

	/** who wrote a message, for a quote header. */
	function authorNameOf(target: ApiMessage | null): string | null {
		if (!target) return null
		if (target.sender_agent_id) {
			return chat.agentNameById.get(target.sender_agent_id) ?? 'assistant'
		}
		const userId = target.sender_user_id
		if (!userId) return null
		if (userId === chat.currentUserId) return 'you'
		return chat.participantById.get(userId)?.name ?? 'someone'
	}

	/** author of the message a reply answers. */
	function replyAuthorName(message: ApiMessage): string | null {
		return authorNameOf(replyTarget(message))
	}

	/**
	 * who to label a message with, or null to label nobody.
	 *
	 * only OTHER people in a group chat need identifying: your own bubbles are
	 * already identified by side, and a solo thread or DM has nobody to
	 * disambiguate - so those keep looking exactly as they do today.
	 */
	function senderOf(message: ApiMessage): MessageAuthor | null {
		if (conversationKind !== 'group') return null
		const userId = message.sender_user_id
		if (!userId || userId === chat.currentUserId) return null
		return (
			chat.participantById.get(userId) ?? {
				id: userId,
				name: 'someone',
				avatarUrl: null,
				isAgent: false,
			}
		)
	}

	/**
	 * the newest of YOUR messages on this branch.
	 *
	 * imessage carries one receipt word, under that message alone, so it travels
	 * down the transcript instead of repeating beside every bubble (F127). the
	 * ownership test is the one `buildRunBlocks` aligns bubbles by.
	 */
	const latestOwnMessageId = $derived.by((): string | null => {
		const userId = chat.currentUserId
		for (let index = chat.messages.length - 1; index >= 0; index -= 1) {
			const message = chat.messages[index]
			if (message.type !== 'user') continue
			if (userId && message.sender_user_id && message.sender_user_id !== userId) continue
			return message.id
		}
		return null
	})

	/** same, for a neighbouring run item (which may be optimistic). */
	function senderOfItem(item: RunItem | undefined): MessageAuthor | null {
		if (!item || item.kind !== 'user') return null
		return senderOf(item.message)
	}

	/**
	 * who a bubble belongs to, for grouping consecutive ones.
	 *
	 * unlike `senderOf` this answers for EVERY message including your own, since
	 * a run of your own bubbles groups exactly like anyone else's.
	 */
	function bubbleAuthorOf(item: RunItem | undefined): string | null {
		if (!item) return null
		if (item.kind === 'optimistic_user') return chat.currentUserId
		if (item.kind === 'user') return item.message.sender_user_id ?? null
		return null
	}

	// effects: jump to the message this load opened at - a search anchor
	// (?message=<id>), or the reader's last-read message when there is none
	$effect(() => {
		const threadId = page.params.id
		const anchorId = page.url.searchParams.get('message') ?? chat.initialAnchorMessageId
		if (!threadId || !anchorId) return
		const anchorKey = `${threadId}:${anchorId}`
		if (handledAnchorKey === anchorKey) return
		if (!chat.hasLoadedBranch) return
		handledAnchorKey = anchorKey
		// stop the initial bottom pin from fighting the anchor scroll
		chat.autoScroll = false
		chat.initialScrollDone = true
		// the reveal parks the view, often right on an edge of the loaded window.
		// marked both before (target already mounted) and on settle (target
		// mounted late) so paging never reads it as the reader arriving there.
		chat.markProgrammaticScroll('auto')
		void revealMessage(anchorId, { wait: ANCHOR_REVEAL_WAIT_MS }).then((revealed) => {
			if (revealed) chat.markProgrammaticScroll('auto')
			if (revealed || handledAnchorKey !== anchorKey) return
			// the anchor is not on this branch: fall back to the live tail
			chat.autoScroll = true
			void chat.queueScrollToBottom('auto')
		})
	})

	// a reveal still waiting for its message must not outlive the thread that
	// asked for it, or it fires against whatever the next thread renders.
	$effect(() => {
		void page.params.id
		return () => cancelMessageReveal()
	})

	async function handleBackToMessages(): Promise<void> {
		await goto(resolve('/messages'), { keepFocus: true, noScroll: true })
	}

	function handleNewChat() {
		sidebar?.selectChat?.(null)
		window.dispatchEvent(new CustomEvent('focus:chat-input'))
		void goto(resolve('/?chat=new' as unknown as '/'), { keepFocus: true, noScroll: true })
	}

	function openConversationInfo(): void {
		if (!chat.thread) return
		infoOpen = true
	}

	async function handleUnarchiveThread(): Promise<void> {
		const id = chat.thread?.id
		if (!id || isUnarchivingThread) return
		isUnarchivingThread = true
		try {
			await unarchiveThread(id)
		} finally {
			isUnarchivingThread = false
		}
	}
</script>

{#snippet islandContextActions()}
	{#if isPeopleConversation}
		<button
			type="button"
			class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
			onclick={() => void handleBackToMessages()}
			aria-label="back to messages"
		>
			<ChevronLeft strokeWidth="2" />
		</button>
	{/if}
	{#if conversationHeader}
		<span class="flex h-full min-w-0 items-center">
			<ConversationIdentity display={conversationHeader} onOpen={openConversationInfo} />
		</span>
	{/if}
	{#if threadArchivedForMe}
		<button
			type="button"
			class="group rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
			disabled={isUnarchivingThread}
			onclick={() => void handleUnarchiveThread()}
			aria-label="unarchive chat"
			title="unarchive chat"
		>
			<ArrowUpTray class="h-5 w-5" />
		</button>
	{/if}
	<AgentSelector
		selectedAgent={selectedAgent.id}
		onAgentChange={(agentId) => selectedAgent.set(agentId)}
	/>
	{#if device.isMobile && !isPeopleConversation}
		<button
			type="button"
			class="flex cursor-pointer items-center justify-center opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
			onclick={handleNewChat}
			aria-label="new chat"
		>
			<ChatPlus />
		</button>
		<ChatSidebarToggleButton />
	{/if}
{/snippet}

<div class="absolute inset-0 flex flex-col" bind:this={pageShellEl}>
	{#if !chat.autoScroll && chat.canScroll && chat.hasRenderableMessages}
		<div
			class="pointer-events-none absolute inset-x-0 z-20 flex justify-center"
			style={`bottom: ${Math.max(24, chat.inputOverlayHeight + 16) + bottomOverhang}px;`}
		>
			<LiquidGlass
				tag="button"
				type="button"
				class="border-foreground/10 text-foreground/85 hover:bg-foreground/10 hover:text-foreground pointer-events-auto flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border transition-colors"
				cornerRadius={18}
				aria-label="scroll to bottom"
				onpointerdown={(e: PointerEvent) => e.preventDefault()}
				onclick={() => {
					chat.autoScroll = true
					chat.queueScrollToBottom('smooth')
				}}
			>
				<ArrowUp class="h-4 w-4 rotate-180" />
			</LiquidGlass>
		</div>
	{/if}

	<div
		class="relative flex-1 overflow-x-hidden overflow-y-auto"
		style="view-transition-name: thread-body; scrollbar-gutter: stable;"
		bind:this={chat.scrollContainer}
		onscroll={chat.handleScroll}
		{@attach detectUserScroll}
	>
		<div
			bind:this={messageListEl}
			class="mx-auto flex min-h-full w-full flex-col {device.isMobile ? '' : 'max-w-7xl'}"
			style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); padding-top: var(--chrome-island-offset); padding-bottom: {chat.inputOverlayHeight +
				bottomOverhang}px;"
		>
			{#if threadNotFound}
				<div class="flex flex-1 items-center justify-center py-16">
					<div class="max-w-md text-center">
						<div
							class="text-foreground/90 text-[4.75rem] leading-none font-semibold tracking-tight"
						>
							404
						</div>
						<h2 class="text-foreground/90 mt-3 text-2xl font-semibold">
							chat not found
						</h2>
						<p class="text-foreground/60 mt-2 text-sm">
							this chat doesn't exist or you don't have access to it.
						</p>
					</div>
				</div>
			{:else if chat.isTemporaryChat && chat.hasLoadedBranch && chat.messages.length === 0 && !chat.optimisticUserMessage && !chat.streamingAssistant}
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
				<div class="flex flex-1 flex-col items-center justify-center py-16">
					<EmptyState
						label="no messages yet"
						description="send a message to start this chat."
					>
						{#snippet icon()}<ChatBubbles variant="solid" class="size-6" />{/snippet}
					</EmptyState>
				</div>
			{:else if chat.hasLoadedBranch}
				<!-- no bottom padding of its own: the only gap between the last message
				     and the composer is the input overlay's own top padding -->
				<div class="flex flex-1 flex-col gap-6 pt-4">
					<!-- one loader for both paging directions, so they cannot drift apart -->
					{#snippet pagingLoader()}
						<div class="flex justify-center py-4">
							<NokodoLoader className="opacity-70" shimmer />
						</div>
					{/snippet}
					<!-- the text bubble's own waiting state: shown before the first
					     token, and again at the end of what is written whenever the
					     stream goes quiet mid-answer -->
					{#snippet streamingTextPlaceholder()}
						<div
							class="assistant-markdown text-foreground/60 text-[0.95rem] leading-relaxed"
						>
							<div class="my-3">
								<ChatGptLoadingIndicator />
							</div>
						</div>
					{/snippet}
					{#if chat.isLoadingOlderMessages}
						{@render pagingLoader()}
					{:else if chat.hasMoreMessages}
						<!-- spacer for scroll trigger area -->
						<div class="h-1"></div>
					{:else if beginningSegments.length > 0 || transcriptOpensAt}
						<!-- only once the top of the transcript IS the beginning: a
						     window that has paged back to an arbitrary point is not
						     something to date or to introduce. the two rows belong
						     together, so they sit closer than the block gap. -->
						<div class="space-y-1">
							{#if beginningSegments.length > 0}
								<ChatSystemRow segments={beginningSegments} header />
							{/if}
							{#if transcriptOpensAt}
								<ChatSystemRow segments={timeHeaderSegments(transcriptOpensAt)} />
							{/if}
						</div>
					{/if}
					{#each chat.runBlocks as block, i (block.runId)}
						{@const userItems = block.items.filter(
							(item) => item.kind === 'user' || item.kind === 'optimistic_user'
						)}
						{@const bubbleTailStyle =
							preferences.data.appearance.bubbleTailStyle ?? 'imessage'}
						{@const systemRows = getBlockSystemEvents(block)}
						{@const timeHeader = getBlockTimeHeader(block)}
						<div class="space-y-3">
							<!-- imessage's own rule: date the transcript where it went quiet,
							     rather than stamping every bubble -->
							{#if timeHeader}
								<ChatSystemRow segments={timeHeaderSegments(timeHeader)} />
							{/if}
							<!-- what happened TO the chat: its own block, never beside a bubble -->
							{#each systemRows as systemEvent (systemEvent.id)}
								<ChatSystemRow
									segments={systemEventSegments(systemEvent, systemNameResolver)}
								/>
							{/each}
							<!-- user messages for this run (both real and optimistic) -->
							{#each userItems as item, itemIndex (item.kind === 'user' ? item.message.id : `${block.runId}-optimistic-${itemIndex}`)}
								{@const isFirst = itemIndex === 0}
								{@const isLast = itemIndex === userItems.length - 1}
								<!-- consecutive bubbles from one person form a tight run: only
								     the edges of a run carry a tail, and only a bubble that
								     starts one keeps its full top margin. -->
								{@const author = bubbleAuthorOf(item)}
								{@const startsGroup =
									isFirst || bubbleAuthorOf(userItems[itemIndex - 1]) !== author}
								{@const endsGroup =
									isLast || bubbleAuthorOf(userItems[itemIndex + 1]) !== author}
								{@const showTail =
									bubbleTailStyle === 'none'
										? false
										: bubbleTailStyle === 'whatsapp'
											? startsGroup
											: endsGroup}
								{#if item.kind === 'user'}
									{@const timestamp = getUserRunItemTimestamp(
										item,
										userItems[itemIndex - 1]
									)}
									{@const siblings = siblingIdsOfKind(
										item.message.parent_id ?? null,
										'user',
										chat.messageChildren,
										chat.messageTree
									)}
									{@const siblingTotal = branchAlternativeCount(
										item.message.parent_id ?? null,
										siblings,
										chat.siblingCounts
									)}
									{@const meta = (item.message.metadata ?? {}) as Record<
										string,
										unknown
									>}
									{@const viewTransitionName =
										meta.steering_state === 'injected'
											? `steering-message-${item.message.id}`
											: undefined}
									{@const sender = senderOf(item.message)}
									{@const prevSender = senderOfItem(userItems[itemIndex - 1])}
									{@const nextSender = senderOfItem(userItems[itemIndex + 1])}
									<div
										{@attach messageAnchor(item.message.id)}
										class="rounded-3xl"
										class:-mt-2={!startsGroup}
									>
										<UserChatMessage
											content={contentPartsToText(item.message.content)}
											contentParts={item.message.content}
											messageId={item.message.id}
											isLatestOwn={item.message.id === latestOwnMessageId}
											entrance={(node) => revealOnSync(node, item.message.id)}
											attachmentRefs={extractAttachmentRefs(item.message)}
											{timestamp}
											align={item.align}
											siblingCount={siblingTotal}
											currentSiblingIndex={siblings.indexOf(item.message.id)}
											onPrevious={() =>
												chat.switchBranch(item.message.id, 'prev')}
											onNext={() =>
												chat.switchBranch(item.message.id, 'next')}
											tailStyle={bubbleTailStyle}
											{showTail}
											{viewTransitionName}
											replyTo={replyTarget(item.message)}
											replyToAuthor={replyAuthorName(item.message)}
											senderName={sender?.name ?? null}
											senderAvatarUrl={sender?.avatarUrl ?? null}
											showSenderName={sender !== null &&
												sender.id !== prevSender?.id}
											showSenderAvatar={sender !== null &&
												sender.id !== nextSender?.id}
											onReply={isReadOnly
												? undefined
												: () => {
														replyDraft = item.message
														inputFocusToken += 1
													}}
											onDelete={item.align === 'right'
												? () =>
														chat.requestDeleteUserMessage(
															item.message.id
														)
												: undefined}
											onEditSave={item.align === 'right'
												? (c) =>
														chat.handleSaveEditMessage(
															item.message.id,
															c
														)
												: undefined}
											onEditSaveAsCopy={item.align === 'right' &&
											!isPeopleConversation
												? (c) =>
														chat.handleSaveAsCopyMessage(
															item.message.id,
															c
														)
												: undefined}
										/>
									</div>
								{:else if item.kind === 'optimistic_user'}
									{@const timestamp = getUserRunItemTimestamp(
										item,
										userItems[itemIndex - 1]
									)}
									{@const oMedia = pendingAttachmentsToMediaParts(
										item.attachments
									)}
									{@const oFiles = pendingAttachmentsToFileParts(
										item.attachments
									)}
									<!-- the optimistic bubble is hidden (opacity) while the entrance ghost
									     is in flight, then revealed when it lands. -->
									<div
										style:opacity={entrance.inFlight ? '0' : '1'}
										bind:this={optimisticMsgEl}
										class:-mt-2={!startsGroup}
									>
										<UserChatMessage
											content={item.text}
											optimisticMediaParts={oMedia}
											optimisticFileParts={oFiles}
											{timestamp}
											tailStyle={bubbleTailStyle}
											{showTail}
											sending={!optimisticClockHidden && !item.deliveryFailed}
											notDelivered={item.deliveryFailed}
										/>
									</div>
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
								<!-- an answer's alternatives are other answers: the run's own
								     user message lands under the same parent for the moment
								     before the response exists, and counting it flashed a
								     phantom "2/2" on brand new messages -->
								{@const assistantSiblings = siblingIdsOfKind(
									blockParentId,
									'response',
									chat.messageChildren,
									chat.messageTree
								)}
								{@const currentSiblingIndex = rootId
									? isStreamingBlock && !chat.messageTree.has(rootId)
										? assistantSiblings.length
										: assistantSiblings.indexOf(rootId)
									: 0}
								{@const siblingCount =
									branchAlternativeCount(
										blockParentId,
										assistantSiblings,
										chat.siblingCounts
									) +
									(isStreamingBlock && !chat.messageTree.has(rootId ?? '')
										? 1
										: 0)}
								{@const displayAgent =
									firstAssistant?.sender_agent_id ??
									block.agentId ??
									chat.streamingAssistant?.senderAgentId ??
									null}

								{#snippet citationPill()}
									<CitationSourcesPill
										citations={blockCitations}
										onclick={() => {
											sourcesModalCitations = blockCitations
										}}
									/>
								{/snippet}
								<AssistantChatMessage
									persistentActions={blockCitations.length > 0
										? citationPill
										: undefined}
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
										{@const answered = answeredMessage(
											firstAssistant,
											userItems.at(-1)
										)}
										<!-- the block's first answer names the invocation it
										replies to, so users can see which chat snapshot the
										agent actually saw -->
										{#if answered && firstAssistant}
											<div class="mb-2 max-w-md">
												<ReplyPreview
													message={answered}
													authorName={replyAuthorName(firstAssistant)}
													jumpable
												/>
											</div>
										{/if}
										<div class="relative space-y-2">
											{#each segments as segment, idx (idx)}
												{#if segment.type === 'assistant' || segment.type === 'streaming_assistant'}
													{@const text =
														segment.type === 'streaming_assistant'
															? (chat.streamingAssistant?.content ??
																'')
															: contentPartsToText(
																	segment.item.message.content
																)}
													{@const citeId =
														segment.type === 'streaming_assistant'
															? (chat.streamingAssistant?.messageId ??
																'')
															: segment.item.message.id}
													{#if segment.type === 'assistant' && hasAttachmentParts(segment.item.message.content)}
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
													{#if segment.type === 'assistant' && extractAttachmentRefs(segment.item.message).length > 0}
														<div class="mb-2">
															<AttachmentRefs
																refs={extractAttachmentRefs(
																	segment.item.message
																)}
															/>
														</div>
													{/if}
													{@const awaitingText =
														segment.type === 'streaming_assistant' &&
														chat.streamingAssistant != null &&
														!chat.streamingAssistant.isError &&
														!chat.hasActiveStreamingToolCalls &&
														!segments.some(
															(s) =>
																s.type === 'tool_group' &&
																s.toolCallIds.some((id) => {
																	const e =
																		chat.getToolExecution(id)
																	return (
																		e != null &&
																		(e.status === 'pending' ||
																			e.status === 'running')
																	)
																})
														)}
													{#if text.trim()}
														<div
															class="assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word select-text"
															{@attach messageAnchor(
																segment.type === 'assistant'
																	? segment.item.message.id
																	: null
															)}
														>
															<MarkdownRenderer
																content={text}
																isStreaming={segment.type ===
																	'streaming_assistant' &&
																	!chat.streamingAssistant
																		?.isError}
																citations={chat.citationSources.get(
																	citeId
																) ?? []}
															/>
														</div>
														{#if awaitingText && chat.isStreamingTextStalled}
															{@render streamingTextPlaceholder()}
														{/if}
													{:else if awaitingText}
														{@render streamingTextPlaceholder()}
													{/if}
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
												{:else if segment.type === 'run_activity'}
													<RunActivity activity={segment.activity} />
												{:else if segment.type === 'run_failure'}
													<RunFailureEntry
														failure={segment.failure}
														outstanding={isFailureOutstanding(
															segment.failure,
															chat.messageTree.values()
														)}
														onRetry={isReadOnly
															? undefined
															: () =>
																	chat.handleRegenerateMessage(
																		segment.failure
																			.anchorMessageId,
																		null,
																		segment.failure.agentId
																	)}
													/>
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
										{#if !isStreamingBlock && !isReadOnly && !isPeopleConversation}
											<RegenerateMenu
												onRegenerate={(prompt) => {
													const userMessageId =
														chat.findRunUserMessage(block)
													chat.handleRegenerateMessage(
														userMessageId,
														prompt
													)
													// physical keyboard: focus the input for a follow-up
													if (!device.isMobile) inputFocusToken += 1
												}}
											/>
										{:else if chat.streamingAssistant?.isError && !isReadOnly}
											<button
												type="button"
												class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/80 hover:bg-foreground/10 hover:text-foreground/90 flex cursor-pointer items-center gap-1.5 border px-3 py-1 text-xs font-medium transition-colors"
												onclick={() => chat.handleRegenerateMessage()}
											>
												<ArrowPath class="size-3.5" strokeWidth="2.5" />
												try again
											</button>
										{/if}
									{/snippet}
								</AssistantChatMessage>
							{/if}
						</div>
					{/each}

					<!-- streaming assistant is rendered within its run block -->

					{#if chat.isLoadingNewerMessages}
						{@render pagingLoader()}
					{:else if chat.hasNewerMessages}
						<!-- spacer for scroll trigger area -->
						<div class="h-1"></div>
					{/if}
					<!-- a DM's left column is already the other person: only a group
					     needs the bubble to say whose typing it is -->
					<TypingIndicator {composers} showFaces={conversationKind === 'group'} />
					<FloatingButtons
						onQuote={!isReadOnly
							? (content) => {
									chat.inputValue = content
								}
							: undefined}
					/>
				</div>
			{:else if chat.showThreadLoader}
				<!-- spinner, not a skeleton: the transcript is bottom-anchored and the load ends
				     in a scroll jump, so a placeholder never becomes the content in place -->
				<div class="flex flex-1 items-center justify-center py-4">
					<NokodoLoader className="opacity-70" shimmer />
				</div>
			{:else}
				<!-- keeps the layout stable while the thread resolves -->
				<div class="flex-1"></div>
			{/if}
		</div>
	</div>

	{#if !threadNotFound && !isReadOnly}
		<div
			class="absolute right-0 left-0 z-10 pt-8 {device.virtualKeyboardOpen && device.isMobile
				? 'pb-2'
				: 'pb-6'}"
			style="bottom: {bottomOverhang}px;"
			bind:this={chat.inputOverlay}
		>
			<div
				class="relative mx-auto w-full {device.isMobile ? '' : 'max-w-7xl'}"
				style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
			>
				<div class="relative transition-all duration-500 ease-in-out">
					<SteeringQueue
						messages={chat.queuedSteeringMessages}
						onDrop={(runId, messageId) => chat.dropSteering(runId, messageId)}
						entrance={entrance.attach}
						hiddenId={hiddenSteeringId}
					/>
					<!-- morph source is the input box only (not the steering queue above it) -->
					<div bind:this={inputBoxEl}>
						<ChatInput
							bind:value={chat.inputValue}
							onSubmit={handleChatSend}
							onStop={chat.handleStopGeneration}
							isGenerating={chat.isGenerating}
							placeholder="send a message"
							focusToken={inputFocusToken}
							viewTransitionName="chat-input"
							replyTo={replyDraft}
							replyToAuthor={replyDraftAuthor}
							onCancelReply={() => (replyDraft = null)}
							{invokableAgents}
							{swipeInvokeAgent}
							{armedAgentId}
							onArmAgent={(id) => (armedAgentId = id)}
							onFocusChange={(focused) => (composerFocused = focused)}
						/>
					</div>
				</div>
			</div>
		</div>
	{/if}

	{#if entrance.ghost}
		<!-- entrance morph ghost: morphs the input box into the outgoing bubble;
		     carries the sending clock until the message persists. -->
		<div
			bind:this={entrance.ghostEl}
			class="text-foreground pointer-events-none fixed z-50 block rounded-3xl px-3 py-2"
			aria-hidden="true"
			style="left: {entrance.ghost.left}px; top: {entrance.ghost.top}px; width: {entrance
				.ghost.width}px; height: {entrance.ghost
				.height}px; background-color: var(--accent-primary); box-shadow: 0 4px 16px var(--accent-border);"
		>
			{#if entrance.inFlight}
				<span
					class="text-foreground/55 pointer-events-none absolute top-1/2 -left-6 flex size-4 -translate-y-1/2 items-center justify-center"
				>
					<span class="ghost-clock-tick flex size-4 items-center justify-center">
						<Clock class="h-4 w-4" strokeWidth="2" />
					</span>
				</span>
			{/if}
			<span class="leading-relaxed whitespace-pre-wrap wrap-break-word"
				>{entrance.ghost.text}</span
			>
		</div>
	{/if}
</div>

<CitationSourcesModal
	open={sourcesModalCitations !== null}
	citations={sourcesModalCitations ?? []}
	onClose={() => {
		sourcesModalCitations = null
	}}
/>

<ChatPropertiesModal open={infoOpen} thread={chat.thread} onClose={() => (infoOpen = false)} />

{#if viewportDebug}
	<ViewportMetricsReadout
		shell={pageShellEl}
		overlay={chat.inputOverlay}
		overhang={bottomOverhang}
	/>
{/if}

<style>
	@keyframes ghostClockTick {
		to {
			transform: rotate(360deg);
		}
	}

	.ghost-clock-tick {
		animation: ghostClockTick 1.4s steps(12) infinite;
		transform-origin: center;
	}
</style>
