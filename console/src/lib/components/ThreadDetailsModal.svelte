<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Message, type Thread } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { tick } from 'svelte'

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

	const messagePageSize = 60

	type ThreadWithDeletedAt = Thread & { deleted_at?: string | null }

	function deletedAt(thread: Thread): string | null {
		return (thread as ThreadWithDeletedAt).deleted_at ?? null
	}

	function close() {
		open = false
		onClose?.()
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
		if (!messagesEl) return

		isLoadingMessages = true
		messageError = null
		const prevScrollHeight = messagesEl.scrollHeight
		const prevScrollTop = messagesEl.scrollTop

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
			await tick()
			const newScrollHeight = messagesEl.scrollHeight
			messagesEl.scrollTop = prevScrollTop + (newScrollHeight - prevScrollHeight)
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

		Promise.all([loadThreadMeta(threadId), loadLatestMessages(threadId)])
			.catch((e: unknown) => {
				error = errorMessage(e) || 'failed to load thread'
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

{#if open}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
		<Card class="w-full max-w-7xl rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
				<div>
					<CardTitle>thread details</CardTitle>
					<CardDescription>{threadId ?? ''}</CardDescription>
					<div class="mt-1 text-xs text-zinc-500">
						special chars: ⏎ = newline, → = tab
					</div>
				</div>
				<Button variant="outline" class="rounded-xl" onclick={close}>close</Button>
			</CardHeader>
			<CardContent class="space-y-4">
				{#if isLoading}
					<div class="flex items-center justify-center py-12">
						<NokodoLoader />
					</div>
				{:else if error}
					<div
						class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				{:else if thread}
					<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
						<div class="space-y-3 lg:col-span-1">
							<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-sm">
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

						<div class="lg:col-span-2">
							<div class="rounded-xl border border-zinc-800 bg-zinc-950">
								<div class="border-b border-zinc-800 px-4 py-3">
									<div class="text-sm font-medium">messages</div>
									<div class="text-xs text-zinc-500">
										{messages.length} loaded
									</div>
								</div>
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
												loading…
											{:else if messageHasMore}
												load older
											{:else}
												no more
											{/if}
										</Button>
										{#if messageError}
											<div class="text-xs text-red-300">{messageError}</div>
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
											class="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3"
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
														class="mt-2 max-h-96 overflow-auto font-mono text-xs break-all whitespace-pre-wrap text-zinc-100">{contentToText(
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
							</div>
						</div>
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no thread selected
					</div>
				{/if}
			</CardContent>
		</Card>
	</div>
{/if}
