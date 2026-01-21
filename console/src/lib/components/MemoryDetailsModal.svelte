<script lang="ts">
	import { browser } from '$app/environment'
	import { MemoriesService, type Memory } from '$lib/api'
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
		memoryId: string | null
		onClose?: () => void
	}

	let { open = $bindable(false), memoryId, onClose }: Props = $props()

	let memory = $state<Memory | null>(null)
	let isLoading = $state(false)
	let error = $state<string | null>(null)

	function close() {
		open = false
		onClose?.()
	}

	/**
	 * Render content with visible special characters for debugging.
	 * Shows \n, \r, \t as escaped sequences.
	 */
	function renderDebugText(text: string): string {
		return text
			.replace(/\r\n/g, '⏎\r\n')
			.replace(/\n/g, '⏎\n')
			.replace(/\r/g, '↵\r')
			.replace(/\t/g, '→\t')
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!memoryId) return

		isLoading = true
		error = null
		memory = null

		MemoriesService.getMemoryMemoriesMemoryIdGet(memoryId)
			.then((m) => {
				memory = m
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : String(e)
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

{#if open}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
		<Card class="w-full max-w-5xl rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
				<div>
					<CardTitle>memory details</CardTitle>
					<CardDescription>{memoryId ?? ''}</CardDescription>
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
				{:else if memory}
					<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
						<div class="space-y-3 lg:col-span-1">
							<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-sm">
								<div class="font-medium">
									{memory.category ?? '(no category)'}
								</div>
								<div class="mt-2 space-y-1 text-xs text-zinc-400">
									<div>id: {memory.id}</div>
									<div>user: {memory.user_id}</div>
									{#if memory.source_message_id}
										<div>source message: {memory.source_message_id}</div>
									{/if}
									{#if memory.confidence !== null && memory.confidence !== undefined}
										<div>
											confidence: {(memory.confidence * 100).toFixed(1)}%
										</div>
									{/if}
									<div>
										created: {new Date(memory.created_at).toLocaleString()}
									</div>
									<div>
										updated: {new Date(memory.updated_at).toLocaleString()}
									</div>
									{#if memory.last_accessed_at}
										<div>
											last accessed: {new Date(
												memory.last_accessed_at
											).toLocaleString()}
										</div>
									{/if}
								</div>
							</div>

							{#if memory.metadata_ && Object.keys(memory.metadata_).length > 0}
								<div class="rounded-xl border border-zinc-800 bg-zinc-950 p-3">
									<div class="text-sm font-medium">metadata</div>
									<pre
										class="mt-2 max-h-40 overflow-auto font-mono text-xs text-zinc-400">{JSON.stringify(
											memory.metadata_,
											null,
											2
										)}</pre>
								</div>
							{/if}
						</div>

						<div class="lg:col-span-2">
							<div class="rounded-xl border border-zinc-800 bg-zinc-950">
								<div class="border-b border-zinc-800 px-4 py-3">
									<div class="text-sm font-medium">content</div>
									<div class="text-xs text-zinc-500">
										raw text with visible special characters
									</div>
								</div>
								<div class="max-h-[60vh] overflow-y-auto p-4">
									<pre
										class="font-mono text-sm break-all whitespace-pre-wrap text-zinc-100">{renderDebugText(
											memory.content
										)}</pre>
								</div>
							</div>
						</div>
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no memory selected
					</div>
				{/if}
			</CardContent>
		</Card>
	</div>
{/if}
