<script lang="ts">
	import { browser } from '$app/environment'
	import { ThreadsService, type Message, type Thread } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'

	type Props = {
		open: boolean
		threadId: string | null
		onClose?: () => void
	}

	let { open = $bindable(false), threadId, onClose }: Props = $props()

	let thread = $state<Thread | null>(null)
	let isLoading = $state(false)
	let error = $state<string | null>(null)

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

	function contentToText(message: Message) {
		const parts = message.content ?? []
		const rendered = parts
			.map((part) => {
				if (typeof (part as any)?.text === 'string') return (part as any).text
				if ((part as any)?.data) return JSON.stringify((part as any).data, null, 2)
				if (typeof (part as any)?.reason === 'string')
					return `refusal: ${(part as any).reason}`
				if ((part as any)?.url) return `attachment: ${(part as any).url}`
				if ((part as any)?.filename) return `attachment: ${(part as any).filename}`
				return ''
			})
			.filter(Boolean)
		// Join with newlines and apply debug rendering
		const raw = rendered.join('\n\n')
		return renderDebugText(raw)
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!threadId) return

		isLoading = true
		error = null
		thread = null

		ThreadsService.getThreadThreadsThreadIdGet(threadId, true)
			.then((t) => {
				thread = t
			})
			.catch((e: any) => {
				error = e?.message ?? 'failed to load thread'
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
									<div>temporary: {thread.is_temporary ? 'yes' : 'no'}</div>
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
										{thread.messages?.length ?? 0} messages
									</div>
								</div>
								<div class="max-h-[60vh] space-y-2 overflow-y-auto p-4">
									{#if !thread.messages || thread.messages.length === 0}
										<div
											class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
										>
											no messages
										</div>
									{/if}

									{#each thread.messages ?? [] as m (m.id)}
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
