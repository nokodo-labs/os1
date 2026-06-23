<script lang="ts">
	import { api } from '$lib/api/client'
	import { eventStreamClient, streamTask, type StreamMessage } from '$lib/api/streaming'
	import type { components } from '$lib/api/types'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import FloppyDisk from '$lib/components/icons/FloppyDisk.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import QuestionMarkCircle from '$lib/components/icons/QuestionMarkCircle.svelte'
	import Refresh from '$lib/components/icons/Refresh.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import type { DropdownSelectOption, SelectorOption } from '$lib/components/primitives'
	import { ActionButton, DropdownSelect, Selector, Switch } from '$lib/components/primitives'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { faviconCandidates, faviconUrl } from '$lib/utils/favicons'
	import { onMount } from 'svelte'

	type ApiTask = components['schemas']['Task']
	type MCPCapabilityType = components['schemas']['MCPCapabilityType']
	type MCPDiscoveredTool = components['schemas']['MCPDiscoveredTool']
	type MCPServer = components['schemas']['MCPServer']
	type MCPServerCreate = components['schemas']['MCPServerCreate']
	type MCPServerUpdate = components['schemas']['MCPServerUpdate']
	type TaskStatus = components['schemas']['TaskStatus']

	type OpenWebUIDeployment = {
		name: string
		description: string
		origin: string
	}

	type OpenWebUISources = {
		enabled: boolean
		deployments: OpenWebUIDeployment[]
	}

	type OpenWebUIImportSummary = {
		deployment_origin: string
		chats_imported: number
		chats_skipped: number
		messages_imported: number
		projects_imported: number
		projects_skipped: number
		files_imported: number
		files_skipped: number
		memories_imported: number
		memories_skipped: number
		notes_imported: number
		notes_skipped: number
		errors: string[]
	}

	let selectedOrigin = $state('')
	let credential = $state('')
	let includeChats = $state(true)
	let includeMemories = $state(true)
	let includeNotes = $state(true)
	let includeArchivedChats = $state(false)
	let importChoicesOpen = $state(false)
	let sourcesEnabled = $state(false)
	let deployments = $state<OpenWebUIDeployment[]>([])
	let sourcesLoaded = $state(false)
	let sourcesError = $state<string | null>(null)
	let startingImport = $state(false)
	let importTask = $state<ApiTask | null>(null)
	let importError = $state<string | null>(null)
	let importResult = $state<OpenWebUIImportSummary | null>(null)
	let showHowTo = $state(false)
	let importTaskStreamController: AbortController | null = null
	let importTaskStreamId: string | null = null
	let openWebUIFaviconIndex = $state(0)
	let mcpServers = $state<MCPServer[]>([])
	let mcpServersLoaded = $state(false)
	let mcpServersError = $state<string | null>(null)
	let mcpCanManage = $state(true)
	let mcpModalOpen = $state(false)
	let mcpModalMode = $state<'create' | 'edit'>('create')
	let mcpEditingId = $state<string | null>(null)
	let mcpName = $state('')
	let mcpDescription = $state('')
	let mcpUrl = $state('')
	let mcpAuthType = $state<'none' | 'bearer'>('none')
	let mcpAccessToken = $state('')
	let mcpEnabled = $state(true)
	let mcpSaving = $state(false)
	let mcpDiscovering = $state(false)
	let mcpSubmitError = $state<string | null>(null)
	let mcpSavingToolId = $state<string | null>(null)

	const OPEN_WEBUI_IMPORT_TASK = 'integrations.open_webui.import'

	const selectedDeployment = $derived(
		deployments.find((deployment) => deployment.origin === selectedOrigin) ?? null
	)
	const userMcpServers = $derived.by(() => {
		const currentUserId = session.currentUserId
		return mcpServers.filter(
			(server) =>
				server.scope === 'user' &&
				(currentUserId === null || server.owner_user_id === currentUserId)
		)
	})
	const selectedMcpServer = $derived(
		mcpEditingId === null
			? null
			: (userMcpServers.find((server) => server.id === mcpEditingId) ?? null)
	)
	const selectedMcpTools = $derived(selectedMcpServer?.discovered_tools ?? [])
	const selectedMcpEnabledToolCount = $derived(
		selectedMcpTools.filter((tool) => tool.enabled).length
	)

	const deploymentOptions = $derived<SelectorOption[]>(
		deployments.map((deployment) => ({
			value: deployment.origin,
			label: deployment.name,
			description: deployment.description,
			iconUrls: faviconCandidates(deployment.origin),
		}))
	)
	const mcpAuthOptions: DropdownSelectOption[] = [
		{ value: 'none', label: 'none', description: 'no authentication' },
		{ value: 'bearer', label: 'bearer token', description: 'send an authorization token' },
	]
	const importTaskActive = $derived(
		importTask?.status === 'pending' || importTask?.status === 'running'
	)
	const importBusy = $derived(startingImport || importTaskActive)
	const importProgress = $derived(
		Math.max(0, Math.min(100, importTask?.progress ?? (startingImport ? 0 : 0)))
	)
	const importStage = $derived(importTask?.stage ?? (startingImport ? 'starting import' : ''))
	const importTaskStatus = $derived(statusLabel(importTask?.status))
	const selectedImportChoices = $derived.by(() => {
		const choices: string[] = []
		if (includeChats) choices.push(includeArchivedChats ? 'chats including archived' : 'chats')
		if (includeMemories) choices.push('memories')
		if (includeNotes) choices.push('notes')
		return choices
	})
	const selectedImportSummary = $derived(
		selectedImportChoices.length > 0 ? selectedImportChoices.join(', ') : 'nothing selected'
	)
	const canStartImport = $derived(
		Boolean(
			selectedOrigin && credential.trim() && selectedImportChoices.length > 0 && !importBusy
		)
	)
	const importSkippedCount = $derived(
		importResult
			? importResult.chats_skipped +
					importResult.projects_skipped +
					importResult.files_skipped +
					importResult.memories_skipped +
					importResult.notes_skipped
			: 0
	)
	const importStatusText = $derived(
		startingImport
			? 'starting import'
			: importStage
				? `${importTaskStatus} - ${importStage}`
				: importTaskStatus
	)

	const pendingIntegrations = [
		{
			name: 'Gemini',
			origin: 'https://gemini.google.com',
			description: 'import conversations from Gemini',
		},
		{
			name: 'ChatGPT',
			origin: 'https://chatgpt.com',
			description: 'import conversations from ChatGPT',
		},
		{
			name: 'Claude',
			origin: 'https://claude.com',
			description: 'import conversations from Claude',
		},
	] as const

	const openWebUIFaviconCandidates = faviconCandidates('https://openwebui.com')
	const openWebUIFaviconUrl = $derived(openWebUIFaviconCandidates[openWebUIFaviconIndex])

	function markOpenWebUIFaviconFailed(): void {
		if (openWebUIFaviconIndex < openWebUIFaviconCandidates.length - 1) {
			openWebUIFaviconIndex += 1
		}
	}

	async function loadSources() {
		sourcesError = null
		const { data, error } = await api.GET('/v1/integrations/open-webui/sources', {})
		if (error || !data) {
			sourcesError = 'failed to load Open WebUI deployments'
			sourcesLoaded = true
			return
		}
		const sources = data as unknown as OpenWebUISources
		sourcesEnabled = Boolean(sources.enabled)
		deployments = sources.deployments.map((deployment) => ({
			name: String(deployment.name),
			description: String(deployment.description),
			origin: String(deployment.origin).replace(/\/$/, ''),
		}))
		if (!deployments.some((deployment) => deployment.origin === selectedOrigin)) {
			selectedOrigin = deployments[0]?.origin ?? ''
		}
		sourcesLoaded = true
	}

	async function loadMcpServers() {
		mcpServersError = null
		const { data, error, response } = await api.GET('/v1/integrations/mcp/servers')
		if (error || !data) {
			mcpCanManage = response.status !== 403 && response.status !== 404
			mcpServersError =
				response.status === 403 || response.status === 404
					? 'MCP servers are not available for your account'
					: 'failed to load MCP servers'
			mcpServersLoaded = true
			return
		}
		mcpCanManage = true
		mcpServers = data
		mcpServersLoaded = true
	}

	function replaceMcpServer(server: MCPServer): void {
		mcpServers = mcpServers.map((item) => (item.id === server.id ? server : item))
	}

	function openCreateMcpModal(): void {
		mcpModalMode = 'create'
		mcpEditingId = null
		mcpName = ''
		mcpDescription = ''
		mcpUrl = ''
		mcpAuthType = 'none'
		mcpAccessToken = ''
		mcpEnabled = true
		mcpSubmitError = null
		mcpModalOpen = true
	}

	function openEditMcpModal(server: MCPServer): void {
		mcpModalMode = 'edit'
		mcpEditingId = server.id
		mcpName = server.name
		mcpDescription = server.description ?? ''
		mcpUrl = server.url ?? ''
		mcpAuthType = server.auth_type === 'bearer' ? 'bearer' : 'none'
		mcpAccessToken = ''
		mcpEnabled = server.enabled
		mcpSubmitError = null
		mcpModalOpen = true
	}

	function mcpDescriptionValue(): string | null {
		const trimmed = mcpDescription.trim()
		return trimmed ? trimmed : null
	}

	function mcpUrlValue(): string | null {
		const trimmed = mcpUrl.trim()
		return trimmed ? trimmed : null
	}

	async function saveMcpServer(): Promise<void> {
		if (!mcpName.trim() || mcpSaving) return
		mcpSaving = true
		mcpSubmitError = null
		try {
			if (mcpModalMode === 'create') {
				const payload: MCPServerCreate = {
					name: mcpName.trim(),
					description: mcpDescriptionValue(),
					scope: 'user',
					transport: 'streamable_http',
					url: mcpUrlValue(),
					command: null,
					args: [],
					env: {},
					auth_type: mcpAuthType,
					headers: {},
					enabled: mcpEnabled,
					capabilities: {
						tools: true,
						resources: false,
						prompts: false,
						sampling: false,
					},
					config: {},
					access_token: mcpAccessToken.trim() || null,
				}
				const { data, error } = await api.POST('/v1/integrations/mcp/servers', {
					body: payload,
				})
				if (error || !data) throw new Error('failed to add MCP server')
				mcpServers = [data, ...mcpServers]
				mcpEditingId = data.id
				mcpModalMode = 'edit'
			} else if (mcpEditingId !== null) {
				const payload: MCPServerUpdate = {
					name: mcpName.trim(),
					description: mcpDescriptionValue(),
					transport: 'streamable_http',
					url: mcpUrlValue(),
					command: null,
					args: [],
					env: {},
					auth_type: mcpAuthType,
					headers: {},
					enabled: mcpEnabled,
					capabilities: {
						tools: true,
						resources: false,
						prompts: false,
						sampling: false,
					},
				}
				const token = mcpAccessToken.trim()
				if (token) payload.access_token = token
				const { data, error } = await api.PATCH(
					'/v1/integrations/mcp/servers/{server_id}',
					{
						params: { path: { server_id: mcpEditingId } },
						body: payload,
					}
				)
				if (error || !data) throw new Error('failed to save MCP server')
				replaceMcpServer(data)
			}
			mcpAccessToken = ''
		} catch (err) {
			mcpSubmitError = err instanceof Error ? err.message : 'failed to save MCP server'
		} finally {
			mcpSaving = false
		}
	}

	async function discoverMcpServer(): Promise<void> {
		if (mcpEditingId === null || mcpDiscovering) return
		mcpDiscovering = true
		mcpSubmitError = null
		try {
			const { data, error } = await api.POST(
				'/v1/integrations/mcp/servers/{server_id}/discover',
				{
					params: { path: { server_id: mcpEditingId } },
				}
			)
			if (error || !data) throw new Error('failed to discover MCP tools')
			replaceMcpServer(data.server)
		} catch (err) {
			mcpSubmitError = err instanceof Error ? err.message : 'failed to discover MCP tools'
		} finally {
			mcpDiscovering = false
		}
	}

	async function deleteMcpServer(): Promise<void> {
		if (mcpEditingId === null || mcpSaving) return
		if (!confirm('delete this MCP server?')) return
		const serverId = mcpEditingId
		mcpSaving = true
		mcpSubmitError = null
		try {
			const { error } = await api.DELETE('/v1/integrations/mcp/servers/{server_id}', {
				params: { path: { server_id: serverId } },
			})
			if (error) throw new Error('failed to delete MCP server')
			mcpServers = mcpServers.filter((server) => server.id !== serverId)
			mcpModalOpen = false
		} catch (err) {
			mcpSubmitError = err instanceof Error ? err.message : 'failed to delete MCP server'
		} finally {
			mcpSaving = false
		}
	}

	async function toggleMcpTool(tool: MCPDiscoveredTool, enabled: boolean): Promise<void> {
		if (mcpEditingId === null) return
		const capabilityType: MCPCapabilityType = 'tool'
		mcpSavingToolId = tool.id
		mcpSubmitError = null
		try {
			const { data, error } = await api.PATCH(
				'/v1/integrations/mcp/servers/{server_id}/capabilities/{capability_type}/{capability_id}',
				{
					params: {
						path: {
							server_id: mcpEditingId,
							capability_type: capabilityType,
							capability_id: tool.id,
						},
					},
					body: { enabled },
				}
			)
			if (error || !data) throw new Error('failed to update MCP tool')
			replaceMcpServer(data)
		} catch (err) {
			mcpSubmitError = err instanceof Error ? err.message : 'failed to update MCP tool'
		} finally {
			mcpSavingToolId = null
		}
	}

	function mcpToolDescription(tool: MCPDiscoveredTool): string {
		return tool.description.trim() || tool.normalized_name
	}

	function applyImportTask(task: ApiTask | null): void {
		importTask = task
		if (task === null) {
			stopImportTaskStream()
			return
		}
		startingImport = false
		if (task.status === 'complete') {
			importResult = summaryFromTask(task)
			importError = null
		} else if (task.status === 'failed') {
			importError = taskErrorMessage(task)
		} else if (task.status === 'cancelled') {
			importError = 'import cancelled'
		} else {
			importError = null
		}
		watchImportTask(task)
	}

	function isActiveTask(task: ApiTask): boolean {
		return task.status === 'pending' || task.status === 'running'
	}

	function stopImportTaskStream(taskId?: string): void {
		if (taskId && importTaskStreamId !== taskId) return
		importTaskStreamController?.abort()
		importTaskStreamController = null
		importTaskStreamId = null
	}

	function watchImportTask(task: ApiTask): void {
		if (!isActiveTask(task)) {
			stopImportTaskStream(task.id)
			return
		}
		if (importTaskStreamId === task.id) return
		stopImportTaskStream()
		const controller = new AbortController()
		importTaskStreamController = controller
		importTaskStreamId = task.id
		void consumeImportTaskStream(task.id, controller)
	}

	async function consumeImportTaskStream(
		taskId: string,
		controller: AbortController
	): Promise<void> {
		try {
			for await (const delta of streamTask(taskId, controller.signal)) {
				if (delta.task !== null) applyImportTask(delta.task)
			}
		} catch {
			// websocket task events remain subscribed as a live fallback.
		} finally {
			if (importTaskStreamController === controller) {
				importTaskStreamController = null
				importTaskStreamId = null
			}
		}
	}

	async function loadLatestImportTask() {
		const { data, error } = await api.GET('/v1/tasks', {
			params: {
				query: {
					sort_by: 'updated_at',
					sort_dir: 'desc',
					limit: 50,
				},
			},
		})
		if (!error && data) {
			const task = data.find((item) => isOpenWebUIImportTask(item)) ?? null
			applyImportTask(task)
		}
	}

	async function runImport() {
		if (importBusy) return
		const trimmedCredential = credential.trim()
		if (!selectedOrigin || !trimmedCredential) {
			importError = 'choose a deployment and paste your Open WebUI key'
			return
		}
		if (selectedImportChoices.length === 0) {
			importError = 'choose at least one thing to import'
			return
		}
		startingImport = true
		importError = null
		importResult = null
		const { data, error, response } = await api.POST(
			'/v1/integrations/open-webui/import/task',
			{
				body: {
					deployment_origin: selectedOrigin,
					jwt: trimmedCredential,
					include_chats: includeChats,
					include_memories: includeMemories,
					include_notes: includeNotes,
					include_archived_chats: includeChats && includeArchivedChats,
					chat_import_mode: 'batched',
				},
			}
		)
		if (error || !data) {
			const detail = (error as { detail?: unknown })?.detail
			importError =
				typeof detail === 'string'
					? detail
					: response?.status === 401
						? 'Open WebUI rejected that key'
						: response?.status === 502
							? 'cannot reach that Open WebUI deployment'
							: 'could not start import'
			startingImport = false
			return
		}
		const task = data as ApiTask
		applyImportTask(task)
		startingImport = false
	}

	function taskMetadata(task: ApiTask | null): Record<string, unknown> {
		return (task?.metadata_ ?? {}) as Record<string, unknown>
	}

	function isOpenWebUIImportTask(task: ApiTask | null): boolean {
		const metadata = taskMetadata(task)
		return (
			metadata.task_name === OPEN_WEBUI_IMPORT_TASK && metadata.integration === 'open_webui'
		)
	}

	function taskFromMessage(message: StreamMessage): ApiTask | null {
		const data = message.data as { task?: unknown } | undefined
		const task = data?.task as ApiTask | undefined
		return task?.id ? task : null
	}

	function handleTaskEvent(message: StreamMessage): void {
		if (!message.type.startsWith('task.')) return
		const task = taskFromMessage(message)
		if (task === null || !isOpenWebUIImportTask(task)) return
		applyImportTask(task)
	}

	function statusLabel(status: TaskStatus | undefined): string {
		if (status === 'pending') return 'queued'
		if (status === 'running') return 'importing'
		if (status === 'complete') return 'complete'
		if (status === 'failed') return 'failed'
		if (status === 'cancelled') return 'cancelled'
		return 'idle'
	}

	function resultObject(task: ApiTask | null): Record<string, unknown> | null {
		const result = task?.result
		return result && typeof result === 'object' && !Array.isArray(result)
			? (result as Record<string, unknown>)
			: null
	}

	function numberResult(result: Record<string, unknown>, key: keyof OpenWebUIImportSummary) {
		const value = result[key]
		return typeof value === 'number' ? value : 0
	}

	function summaryFromTask(task: ApiTask | null): OpenWebUIImportSummary | null {
		const result = resultObject(task)
		if (!result || typeof result.deployment_origin !== 'string') return null
		const errors = Array.isArray(result.errors)
			? result.errors.filter((error): error is string => typeof error === 'string')
			: []
		return {
			deployment_origin: result.deployment_origin,
			chats_imported: numberResult(result, 'chats_imported'),
			chats_skipped: numberResult(result, 'chats_skipped'),
			messages_imported: numberResult(result, 'messages_imported'),
			projects_imported: numberResult(result, 'projects_imported'),
			projects_skipped: numberResult(result, 'projects_skipped'),
			files_imported: numberResult(result, 'files_imported'),
			files_skipped: numberResult(result, 'files_skipped'),
			memories_imported: numberResult(result, 'memories_imported'),
			memories_skipped: numberResult(result, 'memories_skipped'),
			notes_imported: numberResult(result, 'notes_imported'),
			notes_skipped: numberResult(result, 'notes_skipped'),
			errors,
		}
	}

	function taskErrorMessage(task: ApiTask | null): string {
		const result = resultObject(task)
		const message = result?.message
		if (typeof message === 'string' && message.trim()) return message
		return task?.stage || 'import failed'
	}

	function openSelectedDeployment() {
		if (!selectedDeployment) return
		window.open(selectedDeployment.origin, '_blank', 'noopener,noreferrer')
	}

	onMount(() => {
		void loadSources()
		void loadMcpServers()
		void loadLatestImportTask()
		const unsubscribe = eventStreamClient.subscribe(handleTaskEvent)
		return () => {
			unsubscribe()
			stopImportTaskStream()
		}
	})
</script>

<SettingsSectionLayout
	icon={GlobeAlt}
	label="integrations"
	description="import data from other tools"
>
	<div class="space-y-4">
		<section class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<header>
				<div class="flex min-w-0 items-start gap-3">
					<div
						class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden"
					>
						{#if openWebUIFaviconUrl}
							<img
								src={openWebUIFaviconUrl}
								alt=""
								class="h-7 w-7 object-contain"
								onerror={markOpenWebUIFaviconFailed}
							/>
						{:else}
							<GlobeAlt class="text-foreground/70 h-5 w-5" />
						{/if}
					</div>
					<div class="min-w-0">
						<div class="text-foreground/90 text-base font-semibold">Open WebUI</div>
						<div class="text-foreground/55 mt-1 text-sm">
							import chats, memories, and notes from configured deployments.
						</div>
					</div>
				</div>
			</header>

			<div class="mt-5 space-y-4">
				{#if !sourcesLoaded}
					<div class="text-foreground/55 text-sm">
						<ShimmerText className="inline-block">loading deployments</ShimmerText>
					</div>
				{:else if sourcesError}
					<div
						class="rounded-container border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
					>
						{sourcesError}
					</div>
				{:else if !sourcesEnabled}
					<div class="text-foreground/60 text-sm">
						Open WebUI import is disabled by your administrator.
					</div>
				{:else if deployments.length === 0}
					<div class="text-foreground/60 text-sm">
						no Open WebUI deployments are configured. ask your administrator to add one.
					</div>
				{:else}
					<div>
						<div class="text-foreground/55 mb-2 block text-xs font-medium">
							choose a deployment
						</div>
						<Selector
							options={deploymentOptions}
							value={selectedOrigin}
							onchange={(value) => (selectedOrigin = value)}
							ariaLabel="choose Open WebUI deployment"
						/>
					</div>

					<form
						class="space-y-3"
						onsubmit={(event) => {
							event.preventDefault()
							void runImport()
						}}
						autocomplete="off"
					>
						<div>
							<div class="mb-1.5 flex items-center justify-between gap-3">
								<label
									class="text-foreground/55 block text-xs font-medium"
									for="open-webui-key"
								>
									Open WebUI key
								</label>
								<button
									type="button"
									class="text-foreground/55 hover:text-foreground flex cursor-pointer items-center gap-1.5 border-none bg-transparent text-xs transition-colors"
									onclick={() => (showHowTo = true)}
								>
									<QuestionMarkCircle class="h-3.5 w-3.5" />
									where is this?
								</button>
							</div>
							<input
								id="open-webui-key"
								type="password"
								autocomplete="off"
								class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border px-4 py-2.5 text-sm transition-colors outline-none"
								placeholder="paste your Open WebUI API key or JWT"
								bind:value={credential}
								disabled={importBusy}
							/>
							<p class="text-foreground/45 mt-1.5 text-xs">
								your key is used only for this import and is never stored.
							</p>
						</div>

						<div
							class="border-foreground/10 bg-foreground/4 rounded-container border p-3 text-sm"
						>
							<button
								type="button"
								class="flex w-full cursor-pointer items-center justify-between gap-3 border-none bg-transparent text-left"
								onclick={() => (importChoicesOpen = !importChoicesOpen)}
								aria-expanded={importChoicesOpen}
							>
								<div class="min-w-0">
									<div class="text-foreground/80 font-medium">import choices</div>
									<div class="text-foreground/45 mt-0.5 truncate text-xs">
										{selectedImportSummary}
									</div>
								</div>
								<ChevronDown
									class="text-foreground/50 h-4 w-4 shrink-0 transition-transform duration-200 {importChoicesOpen
										? ''
										: '-rotate-90'}"
								/>
							</button>

							{#if importChoicesOpen}
								<div class="mt-3 grid gap-2">
									<div
										class="border-foreground/10 bg-foreground/4 rounded-container hover:bg-foreground/6 flex items-center justify-between gap-3 border p-3 transition-colors"
									>
										<div class="min-w-0">
											<div
												id="open-webui-chats-label"
												class="text-foreground/75"
											>
												include chats
											</div>
										</div>
										<Switch
											size="sm"
											bind:checked={includeChats}
											disabled={importBusy}
											ariaLabelledbyId="open-webui-chats-label"
										/>
									</div>

									<div
										class="border-foreground/10 bg-foreground/4 rounded-container hover:bg-foreground/6 flex items-center justify-between gap-3 border p-3 transition-colors"
									>
										<div class="min-w-0">
											<div
												id="open-webui-memories-label"
												class="text-foreground/75"
											>
												include memories
											</div>
										</div>
										<Switch
											size="sm"
											bind:checked={includeMemories}
											disabled={importBusy}
											ariaLabelledbyId="open-webui-memories-label"
										/>
									</div>

									<div
										class="border-foreground/10 bg-foreground/4 rounded-container hover:bg-foreground/6 flex items-center justify-between gap-3 border p-3 transition-colors"
									>
										<div class="min-w-0">
											<div
												id="open-webui-notes-label"
												class="text-foreground/75"
											>
												include notes
											</div>
										</div>
										<Switch
											size="sm"
											bind:checked={includeNotes}
											disabled={importBusy}
											ariaLabelledbyId="open-webui-notes-label"
										/>
									</div>

									<div
										class="border-foreground/10 bg-foreground/4 rounded-container hover:bg-foreground/6 flex items-center justify-between gap-3 border p-3 transition-colors"
									>
										<div class="min-w-0">
											<div
												id="open-webui-archived-label"
												class="text-foreground/75"
											>
												include archived chats
											</div>
										</div>
										<Switch
											size="sm"
											bind:checked={includeArchivedChats}
											disabled={importBusy || !includeChats}
											ariaLabelledbyId="open-webui-archived-label"
										/>
									</div>
								</div>
							{/if}
						</div>

						<div
							class="rounded-container border-foreground/14 bg-foreground/5 border p-3 text-sm"
						>
							<ActionButton
								variant="secondary"
								class="w-full"
								disabled={!canStartImport}
								onclick={runImport}
							>
								<Download class="h-4 w-4" />
								{#if importBusy}
									<ShimmerText className="inline-block">importing</ShimmerText>
								{:else if importResult}
									import again
								{:else if importError}
									try again
								{:else}
									import selected data
								{/if}
							</ActionButton>

							{#if importBusy || importError || importResult}
								<div class="mt-3 space-y-3">
									{#if importBusy}
										<div>
											<div class="flex items-center justify-between gap-3">
												<div
													class="text-foreground/70 min-w-0 truncate text-xs"
												>
													{importStatusText}
												</div>
												<div class="text-foreground/55 shrink-0 text-xs">
													{importProgress}%
												</div>
											</div>
											<div
												class="bg-foreground/10 mt-2 h-2 overflow-hidden rounded-full"
												role="progressbar"
												aria-valuemin="0"
												aria-valuemax="100"
												aria-valuenow={importProgress}
											>
												<div
													class="h-full rounded-full bg-(--accent-primary) transition-all duration-300"
													style={`width: ${importProgress}%`}
												></div>
											</div>
										</div>
									{/if}

									{#if importError}
										<div
											class="rounded-container border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
										>
											{importError}
										</div>
									{/if}

									{#if importResult}
										<div>
											<div class="text-foreground/90 font-semibold">
												import complete
											</div>
											<div
												class="text-foreground/65 mt-1.5 grid gap-1 text-xs sm:grid-cols-2"
											>
												<div>{importResult.chats_imported} chats</div>
												<div>{importResult.messages_imported} messages</div>
												<div>{importResult.projects_imported} projects</div>
												<div>{importResult.files_imported} files</div>
												<div>{importResult.memories_imported} memories</div>
												<div>{importResult.notes_imported} notes</div>
												<div>{importSkippedCount} skipped</div>
											</div>
											{#if importResult.errors.length > 0}
												<div class="mt-2 text-xs text-amber-300/85">
													{importResult.errors.length} warnings
												</div>
											{/if}
										</div>
									{/if}
								</div>
							{/if}
						</div>
					</form>
				{/if}
			</div>
		</section>

		<section class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<header>
				<div class="flex min-w-0 items-start gap-3">
					<div
						class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden"
					>
						<Wrench class="text-foreground/70 h-6 w-6" />
					</div>
					<div class="min-w-0">
						<div class="text-foreground/90 text-base font-semibold">MCP servers</div>
						<div class="text-foreground/55 mt-1 text-sm">
							connect tools from servers you trust.
						</div>
					</div>
				</div>
			</header>

			<div class="mt-5 space-y-3">
				{#if !mcpServersLoaded}
					<div class="text-foreground/55 text-sm">
						<ShimmerText className="inline-block">loading MCP servers</ShimmerText>
					</div>
				{:else if mcpServersError}
					<div
						class="rounded-container border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200"
					>
						{mcpServersError}
					</div>
				{:else if userMcpServers.length === 0}
					<EmptyState label="no MCP servers" compact={true}>
						{#snippet icon()}
							<Wrench class="h-5 w-5" />
						{/snippet}
					</EmptyState>
				{:else}
					<div class="space-y-2">
						{#each userMcpServers as server (server.id)}
							<button
								type="button"
								class="border-foreground/10 bg-foreground/4 hover:bg-foreground/7 rounded-container flex w-full cursor-pointer items-center justify-between gap-3 border p-3 text-left transition-colors"
								onclick={() => openEditMcpModal(server)}
							>
								<div class="min-w-0">
									<div class="text-foreground/88 truncate text-sm font-medium">
										{server.name}
									</div>
									<div class="text-foreground/45 mt-0.5 truncate text-xs">
										{server.discovered_tools?.filter((tool) => tool.enabled)
											.length ?? 0} enabled tools · {server.status}
									</div>
								</div>
								<div class="flex shrink-0 items-center gap-2">
									<span
										class="rounded-pill bg-foreground/8 text-foreground/55 px-2 py-1 text-xs"
									>
										{server.enabled ? 'on' : 'off'}
									</span>
								</div>
							</button>
						{/each}
					</div>
				{/if}

				<ActionButton
					variant="secondary"
					class="dark:border-foreground dark:bg-foreground dark:text-background dark:hover:bg-foreground/90 w-full"
					disabled={!mcpCanManage || !mcpServersLoaded}
					onclick={openCreateMcpModal}
				>
					<Plus class="h-4 w-4" />
					add new MCP server
				</ActionButton>
			</div>
		</section>

		<div class="grid gap-4 sm:grid-cols-3">
			{#each pendingIntegrations as integration (integration.name)}
				<section
					class="rounded-container liquid-glass liquid-glass--frosted p-5 opacity-75"
				>
					<div class="flex items-start gap-3">
						<div
							class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden"
						>
							<img
								src={faviconUrl(integration.origin)}
								alt=""
								class="h-7 w-7 object-contain"
							/>
						</div>
						<div class="min-w-0">
							<div class="text-foreground/85 text-base font-semibold">
								{integration.name}
							</div>
							<div class="text-foreground/50 mt-1 text-sm">
								{integration.description}
							</div>
							<div class="text-foreground/42 mt-3 text-xs">coming soon</div>
						</div>
					</div>
				</section>
			{/each}
		</div>
	</div>
</SettingsSectionLayout>

<BaseModal
	open={mcpModalOpen}
	title={mcpModalMode === 'create' ? 'add MCP server' : 'MCP server properties'}
	onClose={() => (mcpModalOpen = false)}
	widthClassName="max-w-2xl"
>
	<form
		class="space-y-4 text-sm"
		onsubmit={(event) => {
			event.preventDefault()
			void saveMcpServer()
		}}
	>
		{#if mcpSubmitError}
			<div
				class="rounded-container border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
			>
				{mcpSubmitError}
			</div>
		{/if}

		<div
			class="rounded-container border-foreground/12 bg-foreground/5 flex items-start gap-3 border p-4"
		>
			<div
				class="rounded-container flex h-10 w-10 shrink-0 items-center justify-center bg-cyan-500/12 text-cyan-300"
			>
				<Wrench class="h-5 w-5" />
			</div>
			<div class="min-w-0">
				<div class="text-foreground/90 font-semibold">
					{mcpModalMode === 'create'
						? 'new server'
						: (selectedMcpServer?.name ?? 'server')}
				</div>
				<div class="text-foreground/50 mt-1 text-xs">
					{selectedMcpTools.length} tools · {selectedMcpEnabledToolCount} enabled
				</div>
			</div>
		</div>

		<div class="grid gap-3 sm:grid-cols-2">
			<div>
				<label
					class="text-foreground/55 mb-1.5 block pl-4 text-xs font-medium"
					for="mcp-name"
				>
					name
				</label>
				<input
					id="mcp-name"
					class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border px-4 py-2.5 text-sm transition-colors outline-none"
					bind:value={mcpName}
					placeholder="my tool server"
					required
				/>
			</div>
			<div>
				<label
					class="text-foreground/55 mb-1.5 block pl-4 text-xs font-medium"
					for="mcp-auth"
				>
					auth
				</label>
				<DropdownSelect
					options={mcpAuthOptions}
					value={mcpAuthType}
					onchange={(value) => (mcpAuthType = value === 'bearer' ? 'bearer' : 'none')}
					ariaLabel="MCP authentication"
				/>
			</div>
		</div>

		<div>
			<label class="text-foreground/55 mb-1.5 block pl-4 text-xs font-medium" for="mcp-url">
				streamable HTTP URL
			</label>
			<input
				id="mcp-url"
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border px-4 py-2.5 text-sm transition-colors outline-none"
				bind:value={mcpUrl}
				placeholder="https://example.com/mcp"
			/>
		</div>

		<div>
			<label class="text-foreground/55 mb-1.5 block pl-4 text-xs font-medium" for="mcp-token">
				access token
			</label>
			<input
				id="mcp-token"
				type="password"
				autocomplete="off"
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 w-full border px-4 py-2.5 text-sm transition-colors outline-none"
				bind:value={mcpAccessToken}
				placeholder={mcpModalMode === 'edit'
					? 'leave blank to keep current token'
					: 'paste bearer token'}
			/>
		</div>

		<div>
			<label
				class="text-foreground/55 mb-1.5 block pl-3 text-xs font-medium"
				for="mcp-description"
			>
				description
			</label>
			<textarea
				id="mcp-description"
				class="rounded-popup border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 focus:border-foreground/20 focus:bg-foreground/8 min-h-22 w-full border px-4 py-3 text-sm transition-colors outline-none"
				bind:value={mcpDescription}
				placeholder="what this server is for"
			></textarea>
		</div>

		<div
			class="border-foreground/10 bg-foreground/4 rounded-container flex items-center justify-between gap-3 border p-3"
		>
			<div class="min-w-0">
				<div id="mcp-enabled-label" class="text-foreground/80 font-medium">enabled</div>
			</div>
			<Switch bind:checked={mcpEnabled} ariaLabelledbyId="mcp-enabled-label" />
		</div>

		{#if mcpModalMode === 'edit'}
			<div class="border-foreground/10 border-t pt-4">
				<div class="flex items-center justify-between gap-3">
					<div>
						<div class="text-foreground/86 font-semibold">discovered tools</div>
						<div class="text-foreground/45 mt-0.5 text-xs">
							{selectedMcpEnabledToolCount} enabled
						</div>
					</div>
					<ActionButton
						variant="secondary"
						disabled={mcpDiscovering || mcpSaving}
						onclick={discoverMcpServer}
					>
						<Refresh class="h-4 w-4 {mcpDiscovering ? 'animate-spin' : ''}" />
						{#if mcpDiscovering}
							<ShimmerText className="inline-block">discovering</ShimmerText>
						{:else}
							discover
						{/if}
					</ActionButton>
				</div>

				{#if selectedMcpTools.length > 0}
					<div class="mt-3 space-y-2">
						{#each selectedMcpTools as tool (tool.id)}
							<div
								class="border-foreground/10 bg-foreground/4 rounded-container flex items-center justify-between gap-3 border p-3"
							>
								<div class="min-w-0">
									<div class="text-foreground/82 truncate text-sm font-medium">
										{tool.name}
									</div>
									<div class="text-foreground/45 mt-0.5 line-clamp-2 text-xs">
										{mcpToolDescription(tool)}
									</div>
								</div>
								<Switch
									checked={tool.enabled}
									disabled={mcpSavingToolId === tool.id}
									onchange={() => toggleMcpTool(tool, !tool.enabled)}
								/>
							</div>
						{/each}
					</div>
				{:else}
					<div class="text-foreground/55 mt-3 text-sm">no tools discovered yet.</div>
				{/if}
			</div>
		{/if}

		<div class="flex flex-col gap-2 pt-1 sm:flex-row sm:items-center sm:justify-between">
			<div>
				{#if mcpModalMode === 'edit'}
					<button
						type="button"
						class="rounded-pill inline-flex cursor-pointer items-center justify-center gap-2 border border-red-500/25 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-300 transition-colors hover:bg-red-500/15"
						disabled={mcpSaving}
						onclick={deleteMcpServer}
					>
						<Trash class="h-4 w-4" />
						delete
					</button>
				{/if}
			</div>
			<div class="flex justify-end gap-2">
				<ActionButton disabled={mcpSaving || !mcpName.trim()} onclick={saveMcpServer}>
					{#if mcpSaving}
						<ShimmerText className="inline-block">saving</ShimmerText>
					{:else}
						<FloppyDisk class="h-4 w-4" />
						save
					{/if}
				</ActionButton>
			</div>
		</div>
	</form>
</BaseModal>

<BaseModal
	open={showHowTo}
	title="how to get your Open WebUI key"
	description="Open WebUI exposes an account API key that works as a bearer credential for imports."
	onClose={() => (showHowTo = false)}
>
	<div class="space-y-4 text-sm">
		<div class="rounded-container bg-foreground/5 p-4">
			<div class="text-foreground/90 font-semibold">quick path</div>
			<ol class="text-foreground/70 mt-3 list-decimal space-y-2 pl-5">
				<li>
					open {selectedDeployment?.name ?? 'your Open WebUI deployment'} and sign in.
				</li>
				<li>open your profile menu, then open settings.</li>
				<li>go to account and find the API Key section.</li>
				<li>if there is no key yet, choose create new secret key.</li>
				<li>copy the key and paste it here. do not include the word Bearer.</li>
			</ol>
		</div>

		<div class="rounded-container border-foreground/12 bg-foreground/3 border p-4">
			<div class="text-foreground/90 font-semibold">not seeing API Key?</div>
			<p class="text-foreground/62 mt-2 leading-relaxed">
				Open WebUI can hide API keys unless an admin enables them. ask the deployment admin
				to enable API keys in Open WebUI admin settings.
			</p>
		</div>

		<div class="flex justify-end gap-2 pt-1">
			{#if selectedDeployment}
				<button
					type="button"
					class="rounded-pill border-foreground/10 bg-foreground/10 text-foreground/90 hover:border-foreground/15 hover:bg-foreground/15 inline-flex items-center justify-center gap-2 border px-4 py-2 text-sm font-medium transition-all duration-150"
					onclick={openSelectedDeployment}
				>
					<GlobeAlt class="h-4 w-4" />
					open Open WebUI
				</button>
			{/if}
			<ActionButton variant="ghost" onclick={() => (showHowTo = false)}>
				<Check class="h-4 w-4" />
				done
			</ActionButton>
		</div>
	</div>
</BaseModal>
