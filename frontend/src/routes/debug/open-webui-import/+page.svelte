<script lang="ts">
	import { resolve } from '$app/paths'
	import { api } from '$lib/api/client'
	import { eventStreamClient, streamTask, type StreamMessage } from '$lib/api/streaming'
	import type { components } from '$lib/api/types'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import type { SelectorOption } from '$lib/components/primitives'
	import { ActionButton, Selector, Switch } from '$lib/components/primitives'
	import { onMount } from 'svelte'

	type ApiTask = components['schemas']['Task']
	type ChatImportMode = 'batched' | 'bulk'

	type OpenWebUIDeployment = {
		name: string
		description: string
		origin: string
	}

	let deployments = $state<OpenWebUIDeployment[]>([])
	let selectedOrigin = $state('')
	let credential = $state('')
	let includeChats = $state(true)
	let includeMemories = $state(true)
	let includeNotes = $state(true)
	let includeArchivedChats = $state(false)
	let chatImportMode = $state<ChatImportMode>('batched')
	let loadingSources = $state(false)
	let starting = $state(false)
	let error = $state<string | null>(null)
	let task = $state<ApiTask | null>(null)
	let taskStreamController: AbortController | null = null
	let taskStreamId: string | null = null

	const OPEN_WEBUI_IMPORT_TASK = 'integrations.open_webui.import'

	const deploymentOptions = $derived<SelectorOption[]>(
		deployments.map((deployment) => ({
			value: deployment.origin,
			label: deployment.name,
			description: deployment.description,
		}))
	)

	const modeOptions: SelectorOption[] = [
		{
			value: 'batched',
			label: 'batched refs + concurrent chat fetch',
			description: 'lightweight list, then 24 chat detail requests at a time',
		},
		{
			value: 'bulk',
			label: 'bulk export endpoint',
			description: '/chats/all and optional /chats/all/archived',
		},
	]

	const taskActive = $derived(task?.status === 'pending' || task?.status === 'running')
	const busy = $derived(starting || taskActive)
	const progress = $derived(Math.max(0, Math.min(100, task?.progress ?? 0)))
	const result = $derived(task?.result && typeof task.result === 'object' ? task.result : null)

	function applyTask(nextTask: ApiTask): void {
		task = nextTask
		starting = false
		watchTask(nextTask)
	}

	function isActiveTask(value: ApiTask): boolean {
		return value.status === 'pending' || value.status === 'running'
	}

	function stopTaskStream(taskId?: string): void {
		if (taskId && taskStreamId !== taskId) return
		taskStreamController?.abort()
		taskStreamController = null
		taskStreamId = null
	}

	function watchTask(value: ApiTask): void {
		if (!isActiveTask(value)) {
			stopTaskStream(value.id)
			return
		}
		if (taskStreamId === value.id) return
		stopTaskStream()
		const controller = new AbortController()
		taskStreamController = controller
		taskStreamId = value.id
		void consumeTaskStream(value.id, controller)
	}

	async function consumeTaskStream(taskId: string, controller: AbortController): Promise<void> {
		try {
			for await (const delta of streamTask(taskId, controller.signal)) {
				if (delta.task !== null) applyTask(delta.task)
			}
		} catch {
			// websocket task events remain subscribed as a live fallback.
		} finally {
			if (taskStreamController === controller) {
				taskStreamController = null
				taskStreamId = null
			}
		}
	}

	async function loadSources() {
		loadingSources = true
		error = null
		const { data, error: apiError } = await api.GET('/v1/integrations/open-webui/sources', {})
		if (apiError) {
			error = 'failed to load Open WebUI sources'
		} else {
			deployments = data?.deployments ?? []
			selectedOrigin = selectedOrigin || deployments[0]?.origin || ''
		}
		loadingSources = false
	}

	async function startImport() {
		if (!selectedOrigin || !credential || busy) return
		starting = true
		error = null
		task = null
		const { data, error: apiError } = await api.POST(
			'/v1/integrations/open-webui/import/task',
			{
				body: {
					deployment_origin: selectedOrigin,
					jwt: credential,
					include_chats: includeChats,
					include_memories: includeMemories,
					include_notes: includeNotes,
					include_archived_chats: includeArchivedChats,
					chat_import_mode: chatImportMode,
				},
			}
		)
		if (apiError || !data) {
			error = 'failed to start import task'
			starting = false
			return
		}
		applyTask(data as ApiTask)
		credential = ''
		starting = false
	}

	function taskMetadata(value: ApiTask | null): Record<string, unknown> {
		return (value?.metadata_ ?? {}) as Record<string, unknown>
	}

	function isOpenWebUIImportTask(value: ApiTask | null): boolean {
		const metadata = taskMetadata(value)
		return (
			metadata.task_name === OPEN_WEBUI_IMPORT_TASK && metadata.integration === 'open_webui'
		)
	}

	function taskFromMessage(message: StreamMessage): ApiTask | null {
		const data = message.data as { task?: unknown } | undefined
		const value = data?.task as ApiTask | undefined
		return value?.id ? value : null
	}

	function handleTaskEvent(message: StreamMessage): void {
		if (!message.type.startsWith('task.')) return
		const nextTask = taskFromMessage(message)
		if (nextTask === null || !isOpenWebUIImportTask(nextTask)) return
		if (task !== null && nextTask.id !== task.id) return
		applyTask(nextTask)
	}

	onMount(() => {
		void loadSources()
		const unsubscribe = eventStreamClient.subscribe(handleTaskEvent)
		return () => {
			unsubscribe()
			stopTaskStream()
		}
	})
</script>

<div class="mx-auto w-full max-w-4xl px-6 pt-10 pb-24">
	<a href={resolve('/debug')} class="text-foreground/55 hover:text-foreground text-sm transition">
		back to debug
	</a>

	<div class="mt-6 flex flex-col gap-2">
		<h1 class="text-xl font-semibold">Open WebUI import debug</h1>
		<p class="text-muted-foreground text-sm">
			start an import task with an explicit chat fetch mode.
		</p>
	</div>

	<div class="mt-6 space-y-4">
		{#if error}
			<div
				class="rounded-container border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
			>
				{error}
			</div>
		{/if}

		<div class="rounded-container border-foreground/10 bg-foreground/4 space-y-4 border p-4">
			<div>
				<div class="text-foreground/55 mb-2 text-xs font-medium">deployment</div>
				<Selector
					options={deploymentOptions}
					value={selectedOrigin}
					onchange={(value) => (selectedOrigin = value)}
					ariaLabel="choose Open WebUI deployment"
				/>
				{#if loadingSources}
					<div class="text-foreground/50 mt-2 text-xs">loading sources</div>
				{/if}
			</div>

			<div>
				<label
					class="text-foreground/55 mb-2 block text-xs font-medium"
					for="owui-debug-key"
				>
					Open WebUI key
				</label>
				<input
					id="owui-debug-key"
					type="password"
					autocomplete="off"
					class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border px-4 py-2.5 text-sm transition-colors outline-none"
					placeholder="paste key or JWT"
					bind:value={credential}
					disabled={busy}
				/>
			</div>

			<div>
				<div class="text-foreground/55 mb-2 text-xs font-medium">chat fetch mode</div>
				<Selector
					options={modeOptions}
					value={chatImportMode}
					onchange={(value) => (chatImportMode = value as ChatImportMode)}
					ariaLabel="choose chat import mode"
				/>
			</div>

			<div class="grid gap-3 sm:grid-cols-4">
				<div
					class="border-foreground/10 bg-foreground/4 rounded-container flex items-center justify-between gap-3 border p-3 text-sm"
				>
					<div id="owui-debug-chats-label" class="text-foreground/75">chats</div>
					<Switch
						size="sm"
						bind:checked={includeChats}
						disabled={busy}
						ariaLabelledbyId="owui-debug-chats-label"
					/>
				</div>
				<div
					class="border-foreground/10 bg-foreground/4 rounded-container flex items-center justify-between gap-3 border p-3 text-sm"
				>
					<div id="owui-debug-memories-label" class="text-foreground/75">memories</div>
					<Switch
						size="sm"
						bind:checked={includeMemories}
						disabled={busy}
						ariaLabelledbyId="owui-debug-memories-label"
					/>
				</div>
				<div
					class="border-foreground/10 bg-foreground/4 rounded-container flex items-center justify-between gap-3 border p-3 text-sm"
				>
					<div id="owui-debug-notes-label" class="text-foreground/75">notes</div>
					<Switch
						size="sm"
						bind:checked={includeNotes}
						disabled={busy}
						ariaLabelledbyId="owui-debug-notes-label"
					/>
				</div>
				<div
					class="border-foreground/10 bg-foreground/4 rounded-container flex items-center justify-between gap-3 border p-3 text-sm"
				>
					<div id="owui-debug-archived-label" class="text-foreground/75">archived</div>
					<Switch
						size="sm"
						bind:checked={includeArchivedChats}
						disabled={busy}
						ariaLabelledbyId="owui-debug-archived-label"
					/>
				</div>
			</div>

			<ActionButton
				variant="secondary"
				class="w-full"
				disabled={busy ||
					!selectedOrigin ||
					!credential ||
					(!includeChats && !includeMemories && !includeNotes)}
				onclick={startImport}
			>
				{#if busy}
					<ShimmerText className="inline-block"
						>{task?.stage ?? 'starting import'}</ShimmerText
					>
				{:else}
					start import task
				{/if}
			</ActionButton>
		</div>

		{#if task}
			<div
				class="rounded-container border-foreground/10 bg-foreground/4 space-y-3 border p-4"
			>
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<div class="text-foreground/90 text-sm font-semibold">{task.status}</div>
						<div class="text-foreground/55 text-xs">{task.id}</div>
					</div>
					<div class="text-foreground/65 text-sm">{progress}%</div>
				</div>
				<div class="bg-foreground/10 h-2 overflow-hidden rounded-full">
					<div
						class="bg-foreground/70 h-full rounded-full transition-all"
						style={`width: ${progress}%`}
					></div>
				</div>
				<div class="text-foreground/65 text-sm">{task.stage ?? 'no stage'}</div>
				{#if result}
					<pre
						class="rounded-container bg-foreground/5 text-foreground/75 max-h-72 overflow-auto p-3 text-xs">{JSON.stringify(
							result,
							null,
							2
						)}</pre>
				{/if}
			</div>
		{/if}
	</div>
</div>
