<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'

	type Message = Schemas['Message']
	type Thread = Schemas['Thread']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ThreadFlowView from '$lib/components/thread-flow/ThreadFlowView.svelte'
	import { Button } from '$lib/components/ui/button'
	import { ChevronDown, Download, FileJson, FileText, GitBranch, X } from '@lucide/svelte'
	import { Dialog, DropdownMenu } from 'bits-ui'
	import { tick } from 'svelte'

	type ViewTab = 'messages' | 'tree'

	type Props = {
		open: boolean
		threadId: string | null
		onClose?: () => void
	}

	let { open = $bindable(false), threadId, onClose }: Props = $props()

	let thread = $state<Thread | null>(null)
	let isLoading = $state(false)
	let error = $state<string | null>(null)

	let messages = $state<Message[]>([])
	let messageSkip = $state(0)
	let messageHasMore = $state(true)
	let isLoadingMessages = $state(false)
	let messageError = $state<string | null>(null)
	let messagesEl = $state<HTMLDivElement | null>(null)
	let activeTab = $state<ViewTab>('tree')
	let allMessagesLoaded = $state(false)

	const messagePageSize = 60

	type ThreadWithDeletedAt = Thread & { deleted_at?: string | null }

	function deletedAt(thread: Thread): string | null {
		return (thread as ThreadWithDeletedAt).deleted_at ?? null
	}

	function close() {
		open = false
		onClose?.()
	}

	function downloadBlob(content: string, filename: string, mime: string) {
		const blob = new Blob([content], { type: mime })
		const url = URL.createObjectURL(blob)
		const a = document.createElement('a')
		a.href = url
		a.download = filename
		a.click()
		URL.revokeObjectURL(url)
	}

	function exportJson() {
		if (!thread) return
		const payload = { thread, messages }
		const name = (thread.title ?? thread.id).replace(/[^a-zA-Z0-9_-]/g, '_')
		downloadBlob(JSON.stringify(payload, null, 2), `thread-${name}.json`, 'application/json')
	}

	function exportMessagesOnly() {
		if (!thread) return
		const name = (thread.title ?? thread.id).replace(/[^a-zA-Z0-9_-]/g, '_')
		downloadBlob(JSON.stringify(messages, null, 2), `messages-${name}.json`, 'application/json')
	}

	function exportPlainText() {
		if (!thread) return
		const lines = messages.map((m) => {
			const role = m.type ?? 'message'
			const ts = new Date(m.created_at).toISOString()
			return `[${ts}] ${role}:\n${contentToText(m)}\n`
		})
		const name = (thread.title ?? thread.id).replace(/[^a-zA-Z0-9_-]/g, '_')
		downloadBlob(lines.join('\n---\n\n'), `thread-${name}.txt`, 'text/plain')
	}

	async function loadAllMessages() {
		if (!threadId || allMessagesLoaded) return

		while (messageHasMore) {
			await loadOlderMessages()
		}
		allMessagesLoaded = true
	}

	/**
	 * Render content with visible special characters for debugging.
	 * Shows \n, \r, \t as escaped sequences with visual markers.
	 */
	function renderDebugText(text: string): string {
		return text
			.replace(/\r\n/g, '⏎\r\n')
			.replace(/\n/g, '⏎\n')
			.replace(/\r/g, '↵\r')
			.replace(/\t/g, '→\t')
	}

	function errorMessage(e: unknown): string {
		return e instanceof Error ? e.message : String(e)
	}

	function contentToText(message: Message) {
		const parts = message.content ?? []
		const rendered = parts
			.map((part) => {
				if ('text' in part && typeof part.text === 'string') return part.text
				if ('data' in part && part.data) return JSON.stringify(part.data, null, 2)
				if ('reason' in part && typeof part.reason === 'string')
					return `refusal: ${part.reason}`
				if ('url' in part && part.url) return `attachment: ${part.url}`
				if ('filename' in part && part.filename) return `attachment: ${part.filename}`
				return ''
			})
			.filter((s): s is string => Boolean(s))

		// render tool calls if present
		if (message.tool_calls?.length) {
			for (const tc of message.tool_calls) {
				const name = (tc as Record<string, unknown>).name ?? '?'
				const rawArgs = (tc as Record<string, unknown>).arguments
				let argsStr = ''
				if (typeof rawArgs === 'string') {
					argsStr = rawArgs
				} else if (rawArgs != null) {
					argsStr = JSON.stringify(rawArgs, null, 2)
				}
				rendered.push(`tool_call: ${name}(${argsStr})`)
			}
		}

		// render tool result context if this is a tool message
		if (message.tool_call_id) {
			const prefix = message.is_error ? 'tool_error' : 'tool_result'
			rendered.unshift(`[${prefix} for ${message.tool_call_id}]`)
		}

		// Join with newlines and apply debug rendering
		const raw = rendered.join('\n\n')
		return renderDebugText(raw)
	}

	async function loadThreadMeta(id: string) {
		thread = unwrap(
			await api.GET('/v1/threads/{thread_id}', {
				params: { path: { thread_id: id }, query: { include_hidden: true } },
			})
		)
	}

	async function loadLatestMessages(id: string) {
		isLoadingMessages = true
		messageError = null
		messageHasMore = true
		messageSkip = 0
		messages = []

		try {
			const page = unwrap(
				await api.GET('/v1/threads/{thread_id}/messages', {
					params: {
						path: { thread_id: id },
						query: {
							skip: 0,
							limit: messagePageSize,
							sort_by: 'created_at',
							sort_dir: 'desc',
							group_task_runs: true,
							include_hidden: true,
						},
					},
				})
			)
			messageSkip += page.length
			messageHasMore = page.length > 0
			messages = [...page].reverse()
			await tick()
			messagesEl?.scrollTo({ top: messagesEl.scrollHeight })
		} catch (e: unknown) {
			messageError = errorMessage(e) || 'failed to load messages'
			messageHasMore = false
		} finally {
			isLoadingMessages = false
		}
	}

	async function loadOlderMessages() {
		if (!threadId) return
		if (!messageHasMore) return
		if (isLoadingMessages) return

		isLoadingMessages = true
		messageError = null
		const prevScrollHeight = messagesEl?.scrollHeight ?? 0
		const prevScrollTop = messagesEl?.scrollTop ?? 0

		try {
			const page = unwrap(
				await api.GET('/v1/threads/{thread_id}/messages', {
					params: {
						path: { thread_id: threadId },
						query: {
							skip: messageSkip,
							limit: messagePageSize,
							sort_by: 'created_at',
							sort_dir: 'desc',
							group_task_runs: true,
							include_hidden: true,
						},
					},
				})
			)
			if (page.length === 0) {
				messageHasMore = false
				return
			}

			messageSkip += page.length
			messages = [...page].reverse().concat(messages)
			if (messagesEl) {
				await tick()
				const newScrollHeight = messagesEl.scrollHeight
				messagesEl.scrollTop = prevScrollTop + (newScrollHeight - prevScrollHeight)
			}
		} catch (e: unknown) {
			messageError = errorMessage(e) || 'failed to load older messages'
		} finally {
			isLoadingMessages = false
		}
	}

	function onMessagesScroll() {
		if (!messagesEl) return
		if (messagesEl.scrollTop > 80) return
		void loadOlderMessages()
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!threadId) return

		isLoading = true
		error = null
		thread = null
		messages = []
		messageSkip = 0
		messageHasMore = true
		messageError = null
		activeTab = 'tree'
		allMessagesLoaded = false

		Promise.all([loadThreadMeta(threadId), loadLatestMessages(threadId)])
			.then(() => {
				void loadAllMessages()
			})
			.catch((e: unknown) => {
				error = errorMessage(e) || 'failed to load thread'
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

<Dialog.Root bind:open>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-auto max-w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<!-- header -->
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">thread details</Dialog.Title>
					<Dialog.Description class="mt-0.5 text-sm text-zinc-400">
						{threadId ?? ''}
					</Dialog.Description>
				</div>
				<div class="flex items-center gap-2">
					<!-- export dropdown -->
					{#if thread && messages.length > 0}
						<DropdownMenu.Root>
							<DropdownMenu.Trigger
								class="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
							>
								<Download class="h-3.5 w-3.5" />
								export
								<ChevronDown class="h-3 w-3" />
							</DropdownMenu.Trigger>
							<DropdownMenu.Portal>
								<DropdownMenu.Content
									class="z-60 min-w-45 rounded-xl border border-zinc-700 bg-zinc-900 p-1 shadow-xl"
									sideOffset={4}
								>
									<DropdownMenu.Item
										class="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
										onSelect={exportJson}
									>
										<FileJson class="h-3.5 w-3.5" />
										full thread (json)
									</DropdownMenu.Item>
									<DropdownMenu.Item
										class="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
										onSelect={exportMessagesOnly}
									>
										<FileJson class="h-3.5 w-3.5" />
										messages only (json)
									</DropdownMenu.Item>
									<DropdownMenu.Item
										class="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
										onSelect={exportPlainText}
									>
										<FileText class="h-3.5 w-3.5" />
										plain text
									</DropdownMenu.Item>
								</DropdownMenu.Content>
							</DropdownMenu.Portal>
						</DropdownMenu.Root>
					{/if}

					<button
						class="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
						onclick={close}
					>
						<X class="h-4 w-4" />
					</button>
				</div>
			</div>

			{#if isLoading}
				<div class="flex items-center justify-center p-12">
					<NokodoLoader />
				</div>
			{:else if error}
				<div class="p-4">
					<div
						class="rounded-xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				</div>
			{:else if thread}
				<div class="overflow-hidden p-4">
					<div class="flex flex-col gap-4 lg:flex-row lg:items-start">
						<!-- left panel: metadata -->
						<div class="w-full shrink-0 space-y-3 overflow-y-auto lg:w-72">
							<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-sm">
								<div class="font-medium">{thread.title ?? '(untitled)'}</div>
								<div class="mt-2 space-y-1 text-xs text-zinc-400">
									<div>id: {thread.id}</div>
									<div>owner: {thread.owner_id}</div>
									<div>archived: {thread.is_archived ? 'yes' : 'no'}</div>
									<div>deleted: {deletedAt(thread) ? 'yes' : 'no'}</div>
									<div>temporary: {thread.is_temporary ? 'yes' : 'no'}</div>
									{#if deletedAt(thread)}
										<div>
											deleted at: {new Date(
												deletedAt(thread)!
											).toLocaleString()}
										</div>
									{/if}
									<div>
										created: {new Date(thread.created_at).toLocaleString()}
									</div>
									<div>
										updated: {new Date(thread.updated_at).toLocaleString()}
									</div>
									<div>
										last activity: {new Date(
											thread.last_activity_at
										).toLocaleString()}
									</div>
								</div>
							</div>
						</div>

						<!-- right panel: tabbed content -->
						<div class="flex flex-col">
							<div
								class="flex flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900"
							>
								<!-- tab bar -->
								<div
									class="flex shrink-0 items-center gap-1 border-b border-zinc-800 px-4 py-2"
								>
									<button
										class="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs transition-colors {activeTab ===
										'messages'
											? 'bg-zinc-800 text-zinc-100'
											: 'text-zinc-400 hover:text-zinc-200'}"
										onclick={() => (activeTab = 'messages')}
									>
										<FileJson class="h-3.5 w-3.5" />
										messages
									</button>
									<button
										class="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs transition-colors {activeTab ===
										'tree'
											? 'bg-zinc-800 text-zinc-100'
											: 'text-zinc-400 hover:text-zinc-200'}"
										onclick={() => (activeTab = 'tree')}
									>
										<GitBranch class="h-3.5 w-3.5" />
										tree
									</button>
									<span class="ml-auto text-xs text-zinc-500">
										{messages.length} loaded{messageHasMore ? '+' : ''}
									</span>
								</div>

								<!-- messages tab -->
								{#if activeTab === 'messages'}
									<div
										class="max-h-[60vh] space-y-2 overflow-y-auto p-4"
										bind:this={messagesEl}
										onscroll={onMessagesScroll}
									>
										<div class="flex items-center justify-between gap-3">
											<Button
												variant="outline"
												class="rounded-xl"
												disabled={!messageHasMore || isLoadingMessages}
												onclick={loadOlderMessages}
											>
												{#if isLoadingMessages}
													loading...
												{:else if messageHasMore}
													load older
												{:else}
													no more
												{/if}
											</Button>
											{#if messageError}
												<div class="text-xs text-red-300">
													{messageError}
												</div>
											{/if}
										</div>

										{#if messages.length === 0 && !isLoadingMessages}
											<div
												class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
											>
												no messages
											</div>
										{/if}

										{#each messages as m (m.id)}
											<div
												class="rounded-xl border border-zinc-800 bg-zinc-950/50 p-3"
											>
												<div class="flex items-start justify-between gap-3">
													<div class="min-w-0 flex-1">
														<div class="truncate text-xs text-zinc-400">
															{m.sender_user_id
																? `user:${m.sender_user_id}`
																: m.sender_agent_id
																	? `agent:${m.sender_agent_id}`
																	: (m.type ?? 'message')}
														</div>
														<pre
															class="mt-2 overflow-auto font-mono text-xs break-all whitespace-pre-wrap text-zinc-100">{contentToText(
																m
															) || '(no text)'}</pre>
													</div>
													<div class="shrink-0 text-xs text-zinc-500">
														{new Date(m.created_at).toLocaleString()}
													</div>
												</div>
											</div>
										{/each}
									</div>
								{/if}

								<!-- tree tab -->
								{#if activeTab === 'tree'}
									{#if isLoadingMessages && messages.length === 0}
										<div class="flex items-center justify-center py-12">
											<NokodoLoader />
										</div>
									{:else if messages.length === 0}
										<div
											class="m-4 rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
										>
											no messages to visualize
										</div>
									{:else}
										{#if !allMessagesLoaded}
											<div class="px-4 pt-3 text-xs text-amber-400">
												loading all messages for tree... ({messages.length} so
												far)
											</div>
										{/if}
										<div>
											<ThreadFlowView
												{messages}
												currentMessageId={thread.current_message_id}
											/>
										</div>
									{/if}
								{/if}
							</div>
						</div>
					</div>
				</div>
			{:else}
				<div class="p-4">
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no thread selected
					</div>
				</div>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
