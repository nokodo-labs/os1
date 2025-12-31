<script lang="ts">
	import { page } from '$app/state'
	import type { Agent } from '$lib/api/generated'
	import type { components } from '$lib/api/types'
	import { v1Client } from '$lib/api/v1/client'
	import { getAccessToken } from '$lib/auth/session'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import Button from '$lib/components/chat/Button.svelte'
	import ChatInputLiquidGlass from '$lib/components/chat/ChatInput.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
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
			return
		}

		let cancelled = false
		void (async () => {
			const { data } = await v1Client().GET('/threads/{thread_id}', {
				params: { path: { thread_id: threadId } },
			})
			if (cancelled) return
			thread = data ?? null
			setActiveThread(data ?? null)
			if (data) {
				await loadBranch(data.id)
			}
		})()

		return () => {
			cancelled = true
			thread = null
			setActiveThread(null)
			messages = []
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
		if (!selectedAgent) {
			runError = true
			lastRunInput = trimmed
			optimisticUserMessage = {
				id: `client-${Date.now()}`,
				role: 'user',
				content: trimmed,
				timestamp: new Date(),
			}
			return
		}
		runError = false
		lastRunInput = trimmed
		optimisticUserMessage = {
			id: `client-${Date.now()}`,
			role: 'user',
			content: trimmed,
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
				input: trimmed,
				runId,
			})
			if (runId !== activeRun) return
			inputValue = ''
			optimisticUserMessage = null
			streamingAssistant = null
			runError = false
			await loadBranch(thread.id)
		} catch (e) {
			console.error('Failed to run thread', e)
			runError = true
			const ok = await loadBranch(thread.id)
			if (ok) optimisticUserMessage = null
			streamingAssistant = null
		} finally {
			if (runId === activeRun) isGenerating = false
		}
	}

	async function runThreadStream(opts: {
		threadId: string
		agentId: string
		input: string | null
		runId: number
	}): Promise<void> {
		const token = getAccessToken()
		const response = await fetch(`/v1/threads/${opts.threadId}/run/stream`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'text/event-stream',
				...(token ? { Authorization: `Bearer ${token}` } : {}),
			},
			body: JSON.stringify({ agent_id: opts.agentId, input: opts.input }),
		})
		if (!response.ok || !response.body) {
			throw new Error(`stream request failed: ${response.status}`)
		}

		const reader = response.body.getReader()
		const decoder = new TextDecoder()
		let buffer = ''

		while (true) {
			if (opts.runId !== activeRun) {
				try {
					await reader.cancel()
				} catch {
					// ignore
				}
				return
			}

			const { value, done } = await reader.read()
			if (done) break
			buffer += decoder.decode(value, { stream: true })

			let splitIndex = buffer.indexOf('\n\n')
			while (splitIndex !== -1) {
				const rawEvent = buffer.slice(0, splitIndex)
				buffer = buffer.slice(splitIndex + 2)
				splitIndex = buffer.indexOf('\n\n')

				let eventType = ''
				let data = ''
				for (const line of rawEvent.split('\n')) {
					if (line.startsWith('event:')) eventType = line.slice(6).trim()
					if (line.startsWith('data:')) data += line.slice(5).trim()
				}
				if (!eventType || !data) continue
				if (eventType === 'agent_error') {
					throw new Error(data)
				}
				if (eventType !== 'agent_delta') continue
				const delta = JSON.parse(data) as {
					chat?: { message?: { content?: any[] }; done?: boolean }
					done?: boolean
				}
				if (delta.done) return
				const contentParts = delta.chat?.message?.content
				if (!contentParts || !streamingAssistant) continue

				const nextText = contentParts
					.map((p) => (p?.type === 'text' ? p.text : ''))
					.filter(Boolean)
					.join('')
				if (nextText) {
					streamingAssistant = {
						...streamingAssistant,
						content: streamingAssistant.content + nextText,
					}
				}
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
			streamingAssistant = null
			await loadBranch(thread.id)
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

<div class="flex-1 overflow-y-auto">
	<div class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-8 pt-8 pb-32">
		{#if isTemporaryChat && messages.length === 0}
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
		{:else if !hasRenderableMessages}
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
		{:else}
			<div class="flex flex-1 flex-col gap-6 py-8">
				{#each messages as message, index (message.id)}
					<div in:fade={{ duration: 200 }}>
						{#if message.role === 'user'}
							<UserChatMessage
								content={message.content}
								timestamp={message.timestamp}
							>
								{#snippet actions()}
									<Button
										variant="ghost"
										size="sm"
										onclick={() => handleCopyMessage(message.content)}
									>
										<DocumentDuplicate
											className="w-3.5 h-3.5"
											strokeWidth="2"
										/>
									</Button>
									<Button
										variant="ghost"
										size="sm"
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
										variant="ghost"
										size="sm"
										onclick={() => handleCopyMessage(message.content)}
									>
										<DocumentDuplicate
											className="w-3.5 h-3.5"
											strokeWidth="2"
										/>
									</Button>
									<Button
										variant="ghost"
										size="sm"
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
									variant="ghost"
									size="sm"
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
								<Button variant="ghost" size="sm" onclick={retryLastRun}>
									retry
								</Button>
								<Button variant="ghost" size="sm" onclick={retryLastRun}>
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
									variant="ghost"
									size="sm"
									onclick={() =>
										handleCopyMessage(streamingAssistant?.content ?? '')}
								>
									<DocumentDuplicate className="w-3.5 h-3.5" strokeWidth="2" />
								</Button>
								<Button variant="ghost" size="sm" onclick={handleStopGeneration}>
									stop
								</Button>
							{/snippet}
						</AssistantChatMessage>
					</div>
				{/if}
			</div>
		{/if}
	</div>
</div>

<div class="absolute right-0 bottom-0 left-0 z-10 pt-10 pb-8">
	<div class="mx-auto w-full max-w-7xl px-8">
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
