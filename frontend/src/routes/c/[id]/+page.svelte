<script lang="ts">
	import { page } from '$app/state'
	import type { Agent } from '$lib/api/generated'
	import { runChatStream, type StreamedMessage } from '$lib/api/streaming'
	import type { components } from '$lib/api/types'
	import { v1Client } from '$lib/api/v1/client'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import Button from '$lib/components/chat/Button.svelte'
	import ChatInputLiquidGlass from '$lib/components/chat/ChatInput.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import NokodoLoader from '$lib/components/common/NokodoLoader.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import {
		consumePendingChatStart,
		pendingChatStart,
		setActiveThread,
		type Thread,
	} from '$lib/stores/session'
	import { fade } from 'svelte/transition'

	interface Message {
		id: string
		role: 'user' | 'assistant'
		content: string
		timestamp: Date
		model?: string
		senderAgentId?: string | null
	}

	type ApiMessage = components['schemas']['Message']

	let messages = $state<Message[]>([])
	let inputValue = $state('')
	let isGenerating = $state(false)
	let activeRun = 0
	let selectedAgent = $state('')
	let agents = $state<Agent[]>([])
	let optimisticUserMessage = $state<Message | null>(null)
	let streamingAssistant = $state<Message | null>(null)
	let runError = $state(false)
	let lastRunInput = $state('')

	const chrome = useSystemChrome()
	let selectedAgentName = $derived(
		agents.find((a) => a.id === selectedAgent)?.name ?? 'assistant'
	)
	let agentNameById = $derived(new Map(agents.map((a) => [a.id, a.name])))

	let thread = $state<Thread | null>(null)
	const isTemporaryChat = $derived(thread?.is_temporary ?? false)
	let isThreadLoading = $state(false)
	let hasLoadedBranch = $state(false)
	let showThreadLoader = $derived(isThreadLoading)

	function contentPartsToText(parts: ApiMessage['content']): string {
		if (!parts || parts.length === 0) return ''
		return parts
			.map((p) => {
				if (!p) return ''
				if (p.type === 'text') return p.text
				if (p.type === 'refusal') return p.reason
				if (p.type === 'json') {
					try {
						return JSON.stringify(p.data)
					} catch {
						return ''
					}
				}
				return ''
			})
			.filter(Boolean)
			.join('\n')
	}

	function apiMessageToUiMessage(msg: ApiMessage): Message {
		const senderAgentId = msg.sender_agent_id ?? null
		return {
			id: msg.id,
			role: msg.type === 'user' ? 'user' : 'assistant',
			content: contentPartsToText(msg.content),
			timestamp: new Date(msg.created_at),
			model: 'assistant',
			senderAgentId,
		}
	}

	$effect(() => {
		let cancelled = false
		void (async () => {
			const { data, error } = await v1Client().GET('/agents')
			if (cancelled) return
			if (error) {
				console.error('Failed to load agents', error)
				agents = []
				return
			}
			agents = data ?? []
			if (selectedAgent === '' && agents.length > 0) selectedAgent = agents[0].id
		})()
		return () => {
			cancelled = true
		}
	})

	async function loadBranch(threadId: string): Promise<boolean> {
		const { data, error } = await v1Client().GET('/threads/{thread_id}/branch', {
			params: { path: { thread_id: threadId } },
		})
		if (error) {
			console.error('Failed to load thread branch', error)
			messages = []
			return false
		}
		messages = (data ?? []).map(apiMessageToUiMessage)
		return true
	}

	$effect(() => {
		const threadId = page.params.id
		if (!threadId) {
			thread = null
			setActiveThread(null)
			messages = []
			isThreadLoading = false
			hasLoadedBranch = false
			return
		}

		let cancelled = false
		isThreadLoading = true
		hasLoadedBranch = false
		void (async () => {
			try {
				const { data } = await v1Client().GET('/threads/{thread_id}', {
					params: { path: { thread_id: threadId } },
				})
				if (cancelled) return
				thread = data ?? null
				setActiveThread(data ?? null)
				if (data) {
					hasLoadedBranch = await loadBranch(data.id)
				} else {
					hasLoadedBranch = true
				}
			} finally {
				if (!cancelled) isThreadLoading = false
			}
		})()

		return () => {
			cancelled = true
			isThreadLoading = true
			thread = null
			setActiveThread(null)
			messages = []
			hasLoadedBranch = false
		}
	})

	$effect(() => {
		chrome.setAgentSelector({
			selectedAgent,
			onAgentChange: (agentId: string) => (selectedAgent = agentId),
		})
	})

	$effect(() => {
		return () => chrome.setAgentSelector(null)
	})

	$effect(() => {
		if (!thread) return
		const pending = $pendingChatStart
		if (!pending || pending.threadId !== thread.id) return
		if (messages.length !== 0) {
			consumePendingChatStart(thread.id)
			return
		}
		if (isGenerating || runError || optimisticUserMessage !== null || selectedAgent === '')
			return
		const content = consumePendingChatStart(thread.id)
		if (!content) return
		handleSendMessage(content)
	})

	async function handleSendMessage(content: string) {
		const trimmed = content.trim()
		if (!trimmed) return
		if (!thread) return
		const runBaseMessage = trimmed
		if (!selectedAgent) {
			runError = true
			lastRunInput = runBaseMessage
			optimisticUserMessage = {
				id: `client-${Date.now()}`,
				role: 'user',
				content: runBaseMessage,
				timestamp: new Date(),
			}
			return
		}
		runError = false
		lastRunInput = runBaseMessage
		// optimistic user message will be replaced by message_created event
		optimisticUserMessage = {
			id: `client-${Date.now()}`,
			role: 'user',
			content: runBaseMessage,
			timestamp: new Date(),
		}

		isGenerating = true
		streamingAssistant = {
			id: `stream-${Date.now()}`,
			role: 'assistant',
			content: '',
			timestamp: new Date(),
			model: selectedAgentName,
			senderAgentId: selectedAgent,
		}
		const runId = ++activeRun

		try {
			await runThreadStream({
				threadId: thread.id,
				agentId: selectedAgent,
				input: runBaseMessage,
				runId,
			})
			if (runId !== activeRun) return
			inputValue = ''
			runError = false
			// messages are added via message_created events during streaming
			optimisticUserMessage = null
			streamingAssistant = null
		} catch (e) {
			console.error('Failed to run thread', e)
			runError = true
			optimisticUserMessage = null
			streamingAssistant = null
		} finally {
			if (runId === activeRun) isGenerating = false
		}
	}

	function streamedMsgToUi(msg: StreamedMessage): Message {
		const textContent = msg.content
			.map((p) => (p.type === 'text' && p.text ? p.text : ''))
			.filter(Boolean)
			.join('\n')
		return {
			id: msg.id,
			role: msg.type === 'user' ? 'user' : 'assistant',
			content: textContent,
			timestamp: msg.created_at ? new Date(msg.created_at) : new Date(),
			model: 'assistant',
			senderAgentId: msg.sender_agent_id ?? null,
		}
	}

	let runAbortController: AbortController | null = null

	async function runThreadStream(opts: {
		threadId: string
		agentId: string
		input: string | null
		runId: number
	}): Promise<void> {
		runAbortController?.abort()
		runAbortController = new AbortController()

		for await (const delta of runChatStream({
			threadId: opts.threadId,
			agentId: opts.agentId,
			input: opts.input,
			signal: runAbortController.signal,
		})) {
			if (opts.runId !== activeRun) {
				runAbortController.abort()
				return
			}

			switch (delta.event) {
				case 'error':
					throw new Error(delta.data.message || 'generation failed')
				case 'done':
					return
				case 'message_created': {
					const uiMsg = streamedMsgToUi(delta.data)
					if (uiMsg.role === 'user') optimisticUserMessage = null
					if (uiMsg.role === 'assistant') streamingAssistant = null
					messages = [...messages, uiMsg]
					break
				}
				case 'text_delta':
					if (delta.data.text && streamingAssistant) {
						streamingAssistant = {
							...streamingAssistant,
							content: streamingAssistant.content + delta.data.text,
						}
					}
					break
			}
		}
	}

	async function retryLastRun() {
		if (!thread) return
		if (!selectedAgent) return
		runError = false
		isGenerating = true
		const runId = ++activeRun
		try {
			streamingAssistant = {
				id: `stream-${Date.now()}`,
				role: 'assistant',
				content: '',
				timestamp: new Date(),
				model: selectedAgentName,
				senderAgentId: selectedAgent,
			}
			await runThreadStream({
				threadId: thread.id,
				agentId: selectedAgent,
				input: optimisticUserMessage ? lastRunInput : null,
				runId,
			})
			if (runId !== activeRun) return
			runError = false
			optimisticUserMessage = null
			streamingAssistant = null
		} catch (e) {
			console.error('Failed to retry run', e)
			runError = true
			streamingAssistant = null
		} finally {
			if (runId === activeRun) isGenerating = false
		}
	}

	function handleStopGeneration() {
		// no server-side cancellation yet; this just ignores the in-flight response.
		activeRun++
		isGenerating = false
	}

	function handleCopyMessage(content: string) {
		navigator.clipboard.writeText(content)
	}

	function handleRegenerateMessage() {
		void retryLastRun()
	}

	function handleEditMessage(messageId: string) {
		console.log('Edit message:', messageId)
	}

	let hasRenderableMessages = $derived(
		messages.length > 0 || optimisticUserMessage !== null || runError
	)
</script>

<div class="relative flex-1 overflow-y-auto" style="view-transition-name: thread-body;">
	<div class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-8 pt-8 pb-20">
		{#if isTemporaryChat && hasLoadedBranch && messages.length === 0}
			<div class="flex flex-1 items-center justify-center py-16">
				<div class="max-w-md text-center">
					<div
						class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/5 text-white/85"
					>
						<EyeSlash className="h-7 w-7" />
					</div>
					<h2 class="text-2xl font-semibold text-white/90">temporary chat enabled</h2>
					<p class="mt-2 text-sm text-white/60">
						send a message to start. messages here won’t be saved.
					</p>
				</div>
			</div>
		{:else if hasLoadedBranch && !hasRenderableMessages}
			<div class="flex flex-1 items-center justify-center py-16">
				<div class="max-w-md text-center">
					<div
						class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/5 text-white/85"
					>
						<EyeSlash className="h-7 w-7" />
					</div>
					<h2 class="text-2xl font-semibold text-white/90">no messages yet</h2>
					<p class="mt-2 text-sm text-white/60">send a message to begin this thread.</p>
				</div>
			</div>
		{:else if hasLoadedBranch}
			<div class="flex flex-1 flex-col gap-6 py-4">
				{#each messages as message, index (message.id)}
					<div in:fade={{ duration: 200 }}>
						{#if message.role === 'user'}
							<UserChatMessage
								content={message.content}
								timestamp={message.timestamp}
							>
								{#snippet actions()}
									<Button
										variant="glass"
										size="icon"
										onclick={() => handleCopyMessage(message.content)}
									>
										<DocumentDuplicate
											className="w-3.5 h-3.5"
											strokeWidth="2"
										/>
									</Button>
									<Button
										variant="glass"
										size="icon"
										onclick={() => handleEditMessage(message.id)}
									>
										<Pencil className="w-3.5 h-3.5" strokeWidth="2" />
									</Button>
								{/snippet}
							</UserChatMessage>
						{:else}
							<AssistantChatMessage
								content={message.content}
								timestamp={message.timestamp}
								modelName={message.senderAgentId
									? (agentNameById.get(message.senderAgentId) ?? 'assistant')
									: 'assistant'}
								isLastMessage={index === messages.length - 1}
							>
								{#snippet actions()}
									<Button
										variant="glass"
										size="icon"
										onclick={() => handleCopyMessage(message.content)}
									>
										<DocumentDuplicate
											className="w-3.5 h-3.5"
											strokeWidth="2"
										/>
									</Button>
									<Button
										variant="glass"
										size="icon"
										onclick={handleRegenerateMessage}
									>
										<ArrowPath className="w-3.5 h-3.5" strokeWidth="2" />
									</Button>
								{/snippet}
							</AssistantChatMessage>
						{/if}
					</div>
				{/each}

				{#if optimisticUserMessage}
					<div in:fade={{ duration: 200 }}>
						<UserChatMessage
							content={optimisticUserMessage.content}
							timestamp={optimisticUserMessage.timestamp}
						>
							{#snippet actions()}
								<Button
									variant="glass"
									size="icon"
									onclick={() =>
										handleCopyMessage(optimisticUserMessage?.content ?? '')}
								>
									<DocumentDuplicate className="w-3.5 h-3.5" strokeWidth="2" />
								</Button>
							{/snippet}
						</UserChatMessage>
					</div>
				{/if}

				{#if runError}
					<div in:fade={{ duration: 200 }}>
						<AssistantChatMessage
							content={selectedAgent
								? 'there was an error generating a response.'
								: 'select an agent to generate a response.'}
							modelName={selectedAgentName}
							isLastMessage={true}
							tone="error"
						>
							{#snippet actions()}
								<Button variant="secondary" size="sm" onclick={retryLastRun}>
									retry
								</Button>
								<Button variant="secondary" size="sm" onclick={retryLastRun}>
									regenerate
								</Button>
							{/snippet}
						</AssistantChatMessage>
					</div>
				{/if}

				{#if streamingAssistant}
					<div in:fade={{ duration: 200 }}>
						<AssistantChatMessage
							content={streamingAssistant.content}
							timestamp={streamingAssistant.timestamp}
							modelName={streamingAssistant.senderAgentId
								? (agentNameById.get(streamingAssistant.senderAgentId) ??
									'assistant')
								: 'assistant'}
							isLastMessage={true}
						>
							{#snippet actions()}
								<Button
									variant="glass"
									size="icon"
									onclick={() =>
										handleCopyMessage(streamingAssistant?.content ?? '')}
								>
									<DocumentDuplicate className="w-3.5 h-3.5" strokeWidth="2" />
								</Button>
							{/snippet}
						</AssistantChatMessage>
					</div>
				{/if}
			</div>
		{:else}
			<!-- while data is loading, keep layout stable; loader is rendered as an overlay -->
			<div class="flex-1"></div>
		{/if}
	</div>

	{#if showThreadLoader}
		<div
			class="pointer-events-none absolute inset-0 flex items-center justify-center"
			in:fade={{ duration: 120 }}
			out:fade={{ duration: 260 }}
		>
			<NokodoLoader className="opacity-80" shimmer expanded />
		</div>
	{/if}
</div>

<div class="absolute right-0 bottom-0 left-0 z-10 pt-4 pb-5">
	<div class="relative mx-auto w-full max-w-7xl px-8">
		<div
			style="view-transition-name: chat-input;"
			class="transition-all duration-500 ease-in-out"
		>
			<ChatInputLiquidGlass
				bind:value={inputValue}
				onSubmit={handleSendMessage}
				onStop={handleStopGeneration}
				{isGenerating}
				placeholder="send a message"
			/>
		</div>
	</div>
</div>
