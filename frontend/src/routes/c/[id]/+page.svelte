<script lang="ts">
	import { page } from '$app/state'
	import { v1Client } from '$lib/api/v1/client'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import Button from '$lib/components/chat/Button.svelte'
	import ChatInputLiquidGlass from '$lib/components/chat/ChatInput.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { setActiveThread, type Thread } from '$lib/stores/session'
	import { fade } from 'svelte/transition'

	interface Message {
		id: string
		role: 'user' | 'assistant'
		content: string
		timestamp: Date
		model?: string
	}

	let selectedModel = $state('gpt-4')
	let messages = $state<Message[]>([])
	let inputValue = $state('')
	let isGenerating = $state(false)
	let generationTimeout: number | null = null

	const chrome = useSystemChrome()

	let thread = $state<Thread | null>(null)
	const isTemporaryChat = $derived(thread?.is_temporary ?? false)

	$effect(() => {
		const threadId = page.params.id
		if (!threadId) {
			thread = null
			setActiveThread(null)
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
		})()

		return () => {
			cancelled = true
			thread = null
			setActiveThread(null)
		}
	})

	$effect(() => {
		chrome.setAgentSelector({
			selectedAgent: selectedModel,
			onAgentChange: (agentId: string) => (selectedModel = agentId),
		})
	})

	$effect(() => {
		return () => chrome.setAgentSelector(null)
	})

	$effect(() => {
		const initialQuery = page.url.searchParams.get('q')
		if (initialQuery && messages.length === 0) {
			handleSendMessage(initialQuery)
		}
	})

	function handleSendMessage(content: string) {
		const userMessage: Message = {
			id: Date.now().toString(),
			role: 'user',
			content,
			timestamp: new Date(),
		}
		messages.push(userMessage)

		const aiMessageId = (Date.now() + 1).toString()
		const aiMessage: Message = {
			id: aiMessageId,
			role: 'assistant',
			content: '',
			timestamp: new Date(),
			model: selectedModel,
		}
		messages.push(aiMessage)
		isGenerating = true

		generationTimeout = setTimeout(() => {
			const response = `I received your message: "${content}". This is a demo response showcasing the liquid UI!`
			const lastMsg = messages[messages.length - 1]
			if (lastMsg && lastMsg.id === aiMessageId) {
				lastMsg.content = response
			}
			isGenerating = false
			generationTimeout = null
		}, 1000) as unknown as number
	}

	function handleStopGeneration() {
		if (generationTimeout) {
			clearTimeout(generationTimeout)
			generationTimeout = null
		}
		isGenerating = false
	}

	function handleCopyMessage(content: string) {
		navigator.clipboard.writeText(content)
	}

	function handleRegenerateMessage() {
		console.log('Regenerate message')
	}

	function handleEditMessage(messageId: string) {
		console.log('Edit message:', messageId)
	}
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
		{:else if messages.length === 0}
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
								modelName={message.model}
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
