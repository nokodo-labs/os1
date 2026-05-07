<script lang="ts">
	import { api, unwrap } from '$lib/api'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Play, Wrench, X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		onComplete?: () => void
	}

	let { open = $bindable(false), onComplete }: Props = $props()

	let batchSize = $state('')
	let maxLookbackDays = $state('')
	let minInactivityHours = $state('')
	let isRunningBackfill = $state(false)
	let backfillError = $state<string | null>(null)
	let backfillResult = $state<unknown>(null)

	function close() {
		open = false
		backfillError = null
	}

	function numberOrUndefined(value: string): number | undefined {
		const trimmed = value.trim()
		if (!trimmed) return undefined
		const parsed = Number(trimmed)
		return Number.isFinite(parsed) ? parsed : undefined
	}

	function resultText(value: unknown): string {
		if (value === null || value === undefined) return ''
		return JSON.stringify(value, null, 2)
	}

	async function runThreadMaintenanceBackfill() {
		isRunningBackfill = true
		backfillError = null
		backfillResult = null
		try {
			const loaded = unwrap(
				await api.POST('/v1/threads/maintenance-backfill/run', {
					params: {
						query: {
							batch_size: numberOrUndefined(batchSize),
							max_lookback_days: numberOrUndefined(maxLookbackDays),
							min_inactivity_hours: numberOrUndefined(minInactivityHours),
						},
					},
				})
			)
			backfillResult = loaded
			onComplete?.()
		} catch (err) {
			backfillError = err instanceof Error ? err.message : 'failed to start manual task'
		} finally {
			isRunningBackfill = false
		}
	}
</script>

<Dialog.Root
	bind:open
	onOpenChange={(next) => {
		if (!next) close()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-[min(780px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-xl"
		>
			<div
				class="flex shrink-0 items-start justify-between gap-4 border-b border-zinc-800 px-5 py-4"
			>
				<div class="min-w-0">
					<Dialog.Title class="text-base font-semibold">manual task kickoff</Dialog.Title>
					<Dialog.Description class="mt-1 text-sm text-zinc-400">
						start one bounded admin task run on demand.
					</Dialog.Description>
				</div>
				<Button variant="ghost" size="icon" class="rounded-xl" onclick={close}>
					<X class="h-4 w-4" />
				</Button>
			</div>

			<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
				<section class="rounded-xl border border-zinc-800 bg-zinc-900">
					<div class="flex items-start gap-3 px-4 py-4">
						<div
							class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-zinc-950 text-zinc-300"
						>
							<Wrench class="h-4 w-4" />
						</div>
						<div class="min-w-0 flex-1">
							<h3 class="text-sm font-medium text-zinc-100">
								thread maintenance backfill
							</h3>
							<p class="mt-1 text-xs text-zinc-500">
								dispatch one retroactive sweep for inactive threads with incomplete
								metadata.
							</p>
						</div>
					</div>

					<div class="grid gap-4 border-t border-zinc-800 px-4 py-4 md:grid-cols-3">
						<div class="space-y-2">
							<Label for="manual_backfill_batch_size">batch size</Label>
							<Input
								id="manual_backfill_batch_size"
								type="number"
								min="1"
								max="200"
								placeholder="settings default"
								bind:value={batchSize}
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="manual_backfill_lookback">lookback days</Label>
							<Input
								id="manual_backfill_lookback"
								type="number"
								min="1"
								max="365"
								placeholder="settings default"
								bind:value={maxLookbackDays}
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="manual_backfill_inactivity">min inactivity hours</Label>
							<Input
								id="manual_backfill_inactivity"
								type="number"
								min="1"
								max="720"
								placeholder="settings default"
								bind:value={minInactivityHours}
								class="rounded-xl"
							/>
						</div>
					</div>

					{#if backfillError}
						<div
							class="border-t border-red-900/50 bg-red-900/10 px-4 py-3 text-sm text-red-200"
						>
							{backfillError}
						</div>
					{/if}

					{#if backfillResult !== null}
						<div class="border-t border-zinc-800">
							<div class="px-4 py-3 text-sm font-medium text-zinc-100">result</div>
							<pre
								class="max-h-72 overflow-auto px-4 pb-4 font-mono text-xs whitespace-pre-wrap text-zinc-300">{resultText(
									backfillResult
								)}</pre>
						</div>
					{/if}

					<div class="flex justify-end border-t border-zinc-800 px-4 py-4">
						<Button onclick={runThreadMaintenanceBackfill} disabled={isRunningBackfill}>
							<Play class="mr-1.5 h-4 w-4" />
							{isRunningBackfill ? 'running...' : 'run batch'}
						</Button>
					</div>
				</section>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
