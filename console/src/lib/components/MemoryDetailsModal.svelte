<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'

	type Memory = Schemas['Memory']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

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

		api.GET('/v1/memories/{memory_id}', { params: { path: { memory_id: memoryId } } })
			.then((r) => unwrap(r))
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

<Dialog.Root bind:open>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2rem)] min-w-80 -translate-x-1/2 -translate-y-1/2 flex-col overflow-auto rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">memory details</Dialog.Title>
					<Dialog.Description class="mt-0.5 text-sm text-zinc-400">
						{memoryId ?? ''}
					</Dialog.Description>
				</div>
				<button
					class="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
					onclick={close}
				>
					<X class="h-4 w-4" />
				</button>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto p-6">
				{#if isLoading}
					<div class="flex items-center justify-center py-12">
						<NokodoLoader />
					</div>
				{:else if error}
					<div
						class="rounded-xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				{:else if memory}
					<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
						<div class="space-y-3 lg:col-span-1">
							<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-sm">
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
								<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
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
							<div class="rounded-xl border border-zinc-800 bg-zinc-900">
								<div class="border-b border-zinc-800 px-4 py-3">
									<div class="text-sm font-medium">content</div>
									<div class="text-xs text-zinc-500">
										raw text with visible special characters
									</div>
								</div>
								<div class="max-h-[55vh] overflow-y-auto p-4">
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
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
