<script lang="ts">
	import { api, getApiBaseUrl, getAuthHeaders, unwrap, type Schemas } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import {
		Bot,
		ChevronDown,
		ChevronUp,
		CircleMinus,
		CircleStop,
		Eraser,
		FlaskConical,
		Play,
		Plus,
		RefreshCw,
		User,
	} from '@lucide/svelte'
	import { onMount, tick } from 'svelte'

	type Agent = Schemas['Agent']

	// metadata
	let agents = $state<Agent[]>([])
	let isFetching = $state(true)
	let fetchError = $state<string | null>(null)

	// playground state
	let systemPrompt = $state('')
	let showSystem = $state(false)
	let selectedAgentId = $state<string>('')

	type PlaygroundMessage = { role: 'user' | 'assistant' | 'system'; content: string }
	let messages = $state<PlaygroundMessage[]>([])
	let inputRole = $state<'user' | 'assistant'>('user')
	let inputContent = $state('')

	let isStreaming = $state(false)
	let currentAbortController: AbortController | null = null
	let streamError = $state<string | null>(null)

	let messagesContainer: HTMLDivElement | undefined = $state()
	let systemTextarea: HTMLTextAreaElement | undefined = $state()
	let inputTextarea: HTMLTextAreaElement | undefined = $state()

	async function loadMeta() {
		isFetching = true
		fetchError = null
		try {
			agents = await api.GET('/v1/agents').then((r) => unwrap(r))
		} catch (e) {
			console.error('Failed to load playground metadata', e)
			fetchError = 'failed to load agents'
		} finally {
			isFetching = false
		}
	}

	onMount(() => {
		loadMeta()
	})

	function getAgentLabel(agentId: string) {
		const a = agents.find((a) => a.id === agentId)
		return a ? a.name : agentId
	}

	async function scrollToBottom() {
		await tick()
		if (messagesContainer) {
			messagesContainer.scrollTop = messagesContainer.scrollHeight
		}
	}

	function resizeTextarea(el: HTMLTextAreaElement | undefined) {
		if (!el) return
		el.style.height = ''
		el.style.height = Math.min(el.scrollHeight, 300) + 'px'
	}

	function addMessage() {
		if (!inputContent.trim()) return
		messages.push({ role: inputRole, content: inputContent.trim() })
		messages = messages
		inputContent = ''
		inputRole = inputRole === 'user' ? 'assistant' : 'user'
		scrollToBottom()
		if (inputTextarea) {
			inputTextarea.style.height = ''
		}
	}

	function removeMessage(idx: number) {
		messages = messages.filter((_, i) => i !== idx)
	}

	function clearAll() {
		messages = []
		inputContent = ''
		systemPrompt = ''
		streamError = null
	}

	async function runCompletion() {
		if (!selectedAgentId) {
			streamError = 'select an agent first'
			return
		}

		streamError = null

		// flush pending input into message list
		if (inputContent.trim()) {
			messages.push({ role: inputRole, content: inputContent.trim() })
			messages = messages
			inputContent = ''
		}

		// ensure there's at least one message to send
		const userMessages = messages.filter((m) => m.role === 'user')
		if (userMessages.length === 0) {
			streamError = 'add at least one user message'
			return
		}

		isStreaming = true

		// build the input text from the last user message
		const lastUserMsg = messages[messages.length - 1]
		const inputText =
			lastUserMsg?.role === 'user'
				? lastUserMsg.content
				: (messages.findLast((m) => m.role === 'user')?.content ?? '')

		// add empty assistant to stream into
		const assistantMsg: PlaygroundMessage = { role: 'assistant', content: '' }
		messages.push(assistantMsg)
		messages = messages
		await scrollToBottom()

		const controller = new AbortController()
		currentAbortController = controller

		try {
			const headers = await getAuthHeaders()
			const base = getApiBaseUrl() || ''

			const body = {
				agent_id: selectedAgentId,
				input: { text: inputText },
				stream: true,
				persist: false,
			}

			const res = await fetch(`${base}/v1/runs`, {
				method: 'POST',
				headers: {
					...headers,
					'Content-Type': 'application/json',
				},
				body: JSON.stringify(body),
				signal: controller.signal,
				credentials: 'include',
			})

			if (!res.ok) {
				const text = await res.text()
				streamError = `request failed (${res.status}): ${text}`
				messages = messages.filter((m) => m !== assistantMsg)
				return
			}

			if (!res.body) {
				streamError = 'no response body'
				messages = messages.filter((m) => m !== assistantMsg)
				return
			}

			const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()

			while (true) {
				const { value, done } = await reader.read()
				if (done) break

				const lines = value.split('\n')
				for (const line of lines) {
					if (!line.trim()) continue

					// parse SSE format: "event: ...\ndata: ..."
					const dataMatch = line.match(/^data:\s*(.+)$/)
					if (!dataMatch) continue

					const raw = dataMatch[1]
					if (raw === '[DONE]') continue

					try {
						const data = JSON.parse(raw)

						// handle different event types from the runs SSE stream
						if (data.type === 'delta' && data.delta?.text) {
							assistantMsg.content += data.delta.text
							messages = messages
							scrollToBottom()
						} else if (
							data.type === 'message_created' &&
							data.message?.type === 'assistant'
						) {
							// new assistant message started - content arrives via deltas
						} else if (data.type === 'done') {
							// run completed
						} else if (data.choices?.[0]?.delta?.content) {
							// openai-style streaming format fallback
							assistantMsg.content += data.choices[0].delta.content
							messages = messages
							scrollToBottom()
						}
					} catch {
						// skip non-JSON lines
					}
				}
			}
		} catch (e: unknown) {
			if (e instanceof DOMException && e.name === 'AbortError') {
				// user cancelled
			} else {
				console.error('Stream error', e)
				streamError = e instanceof Error ? e.message : String(e)
			}
		} finally {
			isStreaming = false
			currentAbortController = null
		}
	}

	function stopStream() {
		currentAbortController?.abort()
	}
</script>

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 items-center justify-between">
		<div>
			<h2 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
				<FlaskConical class="h-6 w-6 text-emerald-400" />
				playground
			</h2>
			<p class="text-zinc-400">
				test agents interactively with ephemeral, non-persisted runs.
			</p>
		</div>
		<div class="flex items-center gap-2">
			{#if messages.length > 0}
				<Button
					variant="outline"
					class="rounded-xl border-zinc-800 bg-zinc-900/50 text-zinc-300 hover:bg-zinc-800 hover:text-white"
					onclick={clearAll}
					disabled={isStreaming}
				>
					<Eraser class="mr-1.5 h-4 w-4" />
					clear all
				</Button>
			{/if}
		</div>
	</div>

	{#if isFetching}
		<div class="flex min-h-0 flex-1 items-center justify-center">
			<NokodoLoader />
		</div>
	{:else if fetchError}
		<div
			class="rounded-2xl border border-red-900/50 bg-red-900/10 p-6 text-center text-red-400 shadow-xl shadow-red-900/5"
		>
			<p>{fetchError}</p>
			<Button
				variant="outline"
				class="mt-4 border-red-800 hover:bg-red-900"
				onclick={loadMeta}
			>
				<RefreshCw class="mr-2 h-4 w-4" /> retry
			</Button>
		</div>
	{:else}
		<div class="flex min-h-0 flex-1 flex-col gap-4">
			<!-- agent selector -->
			<div
				class="flex shrink-0 flex-wrap items-end gap-4 rounded-2xl border border-zinc-800/60 bg-zinc-900/40 p-4"
			>
				<div class="min-w-60 flex-1 space-y-1.5">
					<Label class="text-xs font-medium text-zinc-400">agent</Label>
					<Select
						value={selectedAgentId}
						onValueChange={(v: string) => (selectedAgentId = v)}
					>
						<SelectTrigger class="h-10 rounded-xl border-zinc-800 bg-zinc-950/50">
							<div class="flex items-center gap-2 truncate text-left">
								<Bot class="h-4 w-4 text-emerald-400" />
								{selectedAgentId
									? getAgentLabel(selectedAgentId)
									: 'select an agent...'}
							</div>
						</SelectTrigger>
						<SelectContent>
							{#each agents as agent (agent.id)}
								<SelectItem value={agent.id}>{agent.name}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
				{#if selectedAgentId}
					{@const agent = agents.find((a) => a.id === selectedAgentId)}
					{#if agent}
						<div class="flex items-center gap-3 text-xs text-zinc-500">
							{#if agent.model_id}
								<span class="rounded-md bg-zinc-800 px-2 py-1">
									{agent.model_id}
								</span>
							{/if}
						</div>
					{/if}
				{/if}
			</div>

			<!-- system prompt collapsible -->
			<div class="shrink-0">
				<button
					type="button"
					class="flex w-full items-center justify-between rounded-xl border border-zinc-800/60 bg-zinc-900/40 px-4 py-2.5 text-sm transition-colors hover:border-zinc-700"
					onclick={() => {
						showSystem = !showSystem
						if (showSystem) {
							tick().then(() => resizeTextarea(systemTextarea))
						}
					}}
				>
					<div class="flex items-center gap-2">
						<span class="font-medium text-zinc-200">system instructions</span>
						{#if !showSystem && systemPrompt.trim()}
							<span class="line-clamp-1 max-w-xs text-zinc-500">
								{systemPrompt}
							</span>
						{/if}
					</div>
					{#if showSystem}
						<ChevronUp class="h-4 w-4 text-zinc-400" />
					{:else}
						<ChevronDown class="h-4 w-4 text-zinc-400" />
					{/if}
				</button>
				{#if showSystem}
					<div class="mt-1 rounded-xl border border-zinc-800/60 bg-zinc-950/50 p-3">
						<textarea
							bind:this={systemTextarea}
							bind:value={systemPrompt}
							class="w-full resize-none bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
							placeholder="you are a helpful assistant..."
							rows={4}
							oninput={() => resizeTextarea(systemTextarea)}
						></textarea>
					</div>
				{/if}
			</div>

			<!-- messages area -->
			<div
				class="flex min-h-0 flex-1 flex-col rounded-2xl border border-zinc-800/60 bg-zinc-950/50"
			>
				<div
					bind:this={messagesContainer}
					class="flex-1 space-y-3 overflow-y-auto scroll-smooth p-4"
				>
					{#if messages.length === 0}
						<div
							class="flex h-full flex-col items-center justify-center text-center opacity-40"
						>
							<FlaskConical class="mb-4 h-16 w-16 text-zinc-600" />
							<p class="text-lg font-medium text-zinc-400">ready to experiment</p>
							<p class="mt-1 max-w-sm text-sm text-zinc-500">
								add messages below, then click run to start an ephemeral agent run.
							</p>
						</div>
					{:else}
						{#each messages as msg, idx (idx)}
							<div class="group flex gap-3">
								<div class="flex shrink-0 items-start pt-2">
									<div
										class="flex h-7 min-w-20 items-center justify-center rounded-lg text-xs font-semibold uppercase {msg.role ===
										'user'
											? 'bg-blue-500/10 text-blue-400'
											: msg.role === 'assistant'
												? 'bg-emerald-500/10 text-emerald-400'
												: 'bg-amber-500/10 text-amber-400'}"
									>
										{msg.role}
									</div>
								</div>
								<div class="flex-1">
									<textarea
										class="w-full resize-none rounded-xl bg-zinc-900/50 p-3 text-sm text-zinc-100 transition-colors outline-none placeholder:text-zinc-600 focus:bg-zinc-900"
										rows={1}
										bind:value={msg.content}
										oninput={(e) => {
											const t = e.currentTarget
											t.style.height = ''
											t.style.height = Math.min(t.scrollHeight, 400) + 'px'
										}}
										onfocus={(e) => {
											const t = e.currentTarget
											t.style.height = ''
											t.style.height = Math.min(t.scrollHeight, 400) + 'px'
										}}
									></textarea>
								</div>
								<div class="flex shrink-0 items-start pt-2">
									<button
										type="button"
										class="rounded-lg p-1.5 text-zinc-600 opacity-0 transition-all group-hover:opacity-100 hover:bg-zinc-800 hover:text-red-400"
										onclick={() => removeMessage(idx)}
										disabled={isStreaming}
									>
										<CircleMinus class="h-4 w-4" />
									</button>
								</div>
							</div>
						{/each}
					{/if}
				</div>

				<!-- input bar -->
				<div class="shrink-0 border-t border-zinc-800/50 p-4">
					{#if streamError}
						<div class="mb-3 rounded-lg bg-red-900/20 px-3 py-2 text-sm text-red-400">
							{streamError}
						</div>
					{/if}

					<div class="rounded-xl border border-zinc-800/60 bg-zinc-900/30 p-3">
						<textarea
							bind:this={inputTextarea}
							bind:value={inputContent}
							class="w-full resize-none bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
							placeholder="enter {inputRole} message here..."
							rows={2}
							oninput={() => resizeTextarea(inputTextarea)}
							onkeydown={(e) => {
								if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
									e.preventDefault()
									runCompletion()
								}
							}}
						></textarea>

						<div
							class="mt-2 flex flex-col gap-2 border-t border-zinc-800/50 pt-2 sm:flex-row sm:items-center sm:justify-between"
						>
							<div class="flex items-center gap-2">
								<button
									type="button"
									class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors {inputRole ===
									'user'
										? 'bg-blue-500/10 text-blue-400 hover:bg-blue-500/20'
										: 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'}"
									onclick={() =>
										(inputRole = inputRole === 'user' ? 'assistant' : 'user')}
								>
									{#if inputRole === 'user'}
										<User class="h-3.5 w-3.5" />
									{:else}
										<Bot class="h-3.5 w-3.5" />
									{/if}
									{inputRole}
								</button>
							</div>

							<div class="flex items-center gap-2">
								<Button
									variant="outline"
									class="h-9 rounded-xl border-zinc-700 bg-zinc-900/50 text-zinc-300 hover:bg-zinc-800"
									onclick={addMessage}
									disabled={!inputContent.trim() || isStreaming}
								>
									<Plus class="mr-1.5 h-3.5 w-3.5" />
									add
								</Button>

								{#if isStreaming}
									<Button
										class="h-9 rounded-xl bg-red-500/80 text-white hover:bg-red-500"
										onclick={stopStream}
									>
										<CircleStop class="mr-1.5 h-3.5 w-3.5" />
										stop
									</Button>
								{:else}
									<Button
										class="h-9 rounded-xl bg-emerald-600 text-white hover:bg-emerald-500"
										onclick={runCompletion}
										disabled={!selectedAgentId ||
											(messages.length === 0 && !inputContent.trim())}
									>
										<Play class="mr-1.5 h-3.5 w-3.5 fill-current" />
										run
									</Button>
								{/if}
							</div>
						</div>
					</div>

					<p class="mt-2 text-center text-[10px] text-zinc-600">ctrl+enter to run</p>
				</div>
			</div>
		</div>
	{/if}
</div>
