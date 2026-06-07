<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'
	import {
		ChevronLeft,
		ChevronRight,
		CircleAlert,
		Database,
		FileText,
		Network,
		Plus,
		RefreshCw,
		Save,
		Search,
		Trash2,
		Wrench,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type MCPAuthType = Schemas['MCPAuthType']
	type MCPCapabilityType = Schemas['MCPCapabilityType']
	type MCPDiscoveredPrompt = Schemas['MCPDiscoveredPrompt']
	type MCPDiscoveredResource = Schemas['MCPDiscoveredResource']
	type MCPDiscoveredTool = Schemas['MCPDiscoveredTool']
	type MCPServer = Schemas['MCPServer']
	type MCPServerCreate = Schemas['MCPServerCreate']
	type MCPServerUpdate = Schemas['MCPServerUpdate']
	type MCPSurfaceConfig = Schemas['MCPSurfaceConfig']

	type Section = 'properties' | 'tools' | 'resources' | 'prompts'
	type ModalMode = 'create' | 'edit'

	const sections: Array<{ value: Section; label: string }> = [
		{ value: 'properties', label: 'properties' },
		{ value: 'tools', label: 'tools' },
		{ value: 'resources', label: 'resources' },
		{ value: 'prompts', label: 'prompts' },
	]

	let servers = $state<MCPServer[]>([])
	let isFetching = $state(true)
	let isLoading = $state(false)
	let isDiscovering = $state(false)
	let error = $state<string | null>(null)
	let submitError = $state<string | null>(null)
	let searchQuery = $state('')
	let pageIndex = $state(0)
	let limit = $state(24)
	let showModal = $state(false)
	let modalMode = $state<ModalMode>('create')
	let activeSection = $state<Section>('properties')
	let editingId = $state<string | null>(null)
	let savingCapabilityId = $state<string | null>(null)

	let formName = $state('')
	let formDescription = $state('')
	let formUrl = $state('')
	let formAuthType = $state<MCPAuthType>('none')
	let formAccessToken = $state('')
	let formEnabled = $state(true)
	let formTools = $state(true)
	let formResources = $state(false)
	let formPrompts = $state(false)

	const filteredServers = $derived.by(() => {
		const q = searchQuery.trim().toLowerCase()
		if (!q) return servers
		return servers.filter((server) => {
			const name = server.name.toLowerCase()
			const description = server.description?.toLowerCase() ?? ''
			const url = server.url?.toLowerCase() ?? ''
			return name.includes(q) || description.includes(q) || url.includes(q)
		})
	})
	const visibleServers = $derived(
		filteredServers.slice(pageIndex * limit, (pageIndex + 1) * limit)
	)
	const hasNext = $derived((pageIndex + 1) * limit < filteredServers.length)
	const selectedServer = $derived(
		editingId === null ? null : (servers.find((server) => server.id === editingId) ?? null)
	)

	$effect(() => {
		void loadServers()
	})

	function resetForm(): void {
		formName = ''
		formDescription = ''
		formUrl = ''
		formAuthType = 'none'
		formAccessToken = ''
		formEnabled = true
		formTools = true
		formResources = false
		formPrompts = false
	}

	function openCreateModal(): void {
		modalMode = 'create'
		editingId = null
		activeSection = 'properties'
		resetForm()
		submitError = null
		showModal = true
	}

	function openEditModal(server: MCPServer): void {
		modalMode = 'edit'
		editingId = server.id
		activeSection = 'properties'
		formName = server.name
		formDescription = server.description ?? ''
		formUrl = server.url ?? ''
		formAuthType = server.auth_type
		formAccessToken = ''
		formEnabled = server.enabled
		formTools = server.capabilities?.tools ?? true
		formResources = server.capabilities?.resources ?? false
		formPrompts = server.capabilities?.prompts ?? false
		submitError = null
		showModal = true
	}

	function closeModal(): void {
		showModal = false
	}

	async function loadServers(): Promise<void> {
		isFetching = true
		error = null
		try {
			servers = unwrap(await api.GET('/v1/integrations/mcp/servers'))
		} catch (err) {
			console.error('failed to load MCP servers', err)
			error = 'failed to load MCP servers'
		} finally {
			isFetching = false
		}
	}

	function replaceServer(server: MCPServer): void {
		servers = servers.map((item) => (item.id === server.id ? server : item))
	}

	function capabilityPayload(): MCPSurfaceConfig {
		return {
			tools: formTools,
			resources: formResources,
			prompts: formPrompts,
			sampling: false,
		}
	}

	function normalizedUrl(): string | null {
		const trimmed = formUrl.trim()
		return trimmed ? trimmed : null
	}

	function normalizedDescription(): string | null {
		const trimmed = formDescription.trim()
		return trimmed ? trimmed : null
	}

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault()
		isLoading = true
		submitError = null
		try {
			if (modalMode === 'create') {
				const payload: MCPServerCreate = {
					name: formName.trim(),
					description: normalizedDescription(),
					scope: 'global',
					transport: 'streamable_http',
					url: normalizedUrl(),
					command: null,
					args: [],
					env: {},
					auth_type: formAuthType,
					headers: {},
					enabled: formEnabled,
					capabilities: capabilityPayload(),
					config: {},
					access_token: formAccessToken.trim() || null,
				}
				const created = unwrap(
					await api.POST('/v1/integrations/mcp/servers', { body: payload })
				)
				servers = [created, ...servers]
			} else if (editingId !== null) {
				const payload: MCPServerUpdate = {
					name: formName.trim(),
					description: normalizedDescription(),
					transport: 'streamable_http',
					url: normalizedUrl(),
					command: null,
					args: [],
					env: {},
					auth_type: formAuthType,
					headers: {},
					enabled: formEnabled,
					capabilities: capabilityPayload(),
				}
				const token = formAccessToken.trim()
				if (token) payload.access_token = token
				const updated = unwrap(
					await api.PATCH('/v1/integrations/mcp/servers/{server_id}', {
						params: { path: { server_id: editingId } },
						body: payload,
					})
				)
				replaceServer(updated)
			}
			showModal = false
		} catch (err) {
			console.error('failed to save MCP server', err)
			submitError = err instanceof Error ? err.message : 'failed to save MCP server'
		} finally {
			isLoading = false
		}
	}

	async function handleDelete(): Promise<void> {
		if (editingId === null) return
		if (!confirm('are you sure you want to delete this MCP server?')) return
		const serverId = editingId
		isLoading = true
		submitError = null
		try {
			unwrap(
				await api.DELETE('/v1/integrations/mcp/servers/{server_id}', {
					params: { path: { server_id: serverId } },
				})
			)
			servers = servers.filter((server) => server.id !== serverId)
			showModal = false
		} catch (err) {
			console.error('failed to delete MCP server', err)
			submitError = err instanceof Error ? err.message : 'failed to delete MCP server'
		} finally {
			isLoading = false
		}
	}

	async function discoverSelectedServer(): Promise<void> {
		if (editingId === null) return
		const serverId = editingId
		isDiscovering = true
		submitError = null
		try {
			const result = unwrap(
				await api.POST('/v1/integrations/mcp/servers/{server_id}/discover', {
					params: { path: { server_id: serverId } },
				})
			)
			replaceServer(result.server)
			if (result.server.status === 'error') {
				submitError =
					result.server.last_error ?? 'discovery failed: the server could not be reached'
			}
		} catch (err) {
			console.error('failed to discover MCP server', err)
			submitError = err instanceof Error ? err.message : 'failed to discover MCP server'
		} finally {
			isDiscovering = false
		}
	}

	async function toggleCapability(
		capabilityType: MCPCapabilityType,
		capabilityId: string,
		enabled: boolean
	): Promise<void> {
		if (editingId === null) return
		const key = `${capabilityType}:${capabilityId}`
		savingCapabilityId = key
		submitError = null
		try {
			const updated = unwrap(
				await api.PATCH(
					'/v1/integrations/mcp/servers/{server_id}/capabilities/{capability_type}/{capability_id}',
					{
						params: {
							path: {
								server_id: editingId,
								capability_type: capabilityType,
								capability_id: capabilityId,
							},
						},
						body: { enabled },
					}
				)
			)
			replaceServer(updated)
		} catch (err) {
			console.error('failed to update MCP capability', err)
			submitError = err instanceof Error ? err.message : 'failed to update MCP capability'
		} finally {
			savingCapabilityId = null
		}
	}

	function statusClass(server: MCPServer): string {
		switch (server.status) {
			case 'ready':
				return 'bg-emerald-500/10 text-emerald-300'
			case 'error':
				return 'bg-red-500/10 text-red-300'
			default:
				return 'bg-zinc-800 text-zinc-300'
		}
	}

	function capabilityCount(server: MCPServer): string {
		const tools = server.discovered_tools?.length ?? 0
		const resources = server.discovered_resources?.length ?? 0
		const prompts = server.discovered_prompts?.length ?? 0
		return `${tools} tools · ${resources} resources · ${prompts} prompts`
	}

	function enabledToolCount(server: MCPServer): number {
		return (server.discovered_tools ?? []).filter((tool) => tool.enabled).length
	}

	function enabledResourceCount(server: MCPServer): number {
		return (server.discovered_resources ?? []).filter((resource) => resource.enabled).length
	}

	function enabledPromptCount(server: MCPServer): number {
		return (server.discovered_prompts ?? []).filter((prompt) => prompt.enabled).length
	}

	function formatDate(value: string | null | undefined): string {
		if (!value) return 'never'
		return new Intl.DateTimeFormat(undefined, {
			dateStyle: 'medium',
			timeStyle: 'short',
		}).format(new Date(value))
	}

	function capabilitySaving(type: MCPCapabilityType, id: string): boolean {
		return savingCapabilityId === `${type}:${id}`
	}

	function toolDescription(tool: MCPDiscoveredTool): string {
		return tool.description.trim() || tool.normalized_name
	}

	function resourceDescription(resource: MCPDiscoveredResource): string {
		return resource.description.trim() || resource.uri
	}

	function promptDescription(prompt: MCPDiscoveredPrompt): string {
		return prompt.description.trim() || prompt.command
	}
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">MCP</h2>
			<p class="text-zinc-400">manage MCP servers and discovered resources.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
			<div class="relative w-full sm:w-72">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search MCP servers..."
					bind:value={searchQuery}
					oninput={() => (pageIndex = 0)}
					class="w-full rounded-xl pl-8"
				/>
			</div>
			<Button onclick={openCreateModal} class="gap-2 rounded-xl">
				<Plus class="h-4 w-4" />
				add MCP server
			</Button>
			<Button
				variant="outline"
				class="gap-2 rounded-xl"
				onclick={loadServers}
				disabled={isFetching}
			>
				<RefreshCw class="h-4 w-4 {isFetching ? 'animate-spin' : ''}" />
				refresh
			</Button>
		</div>
	</div>

	{#if isFetching}
		<div class="flex flex-col items-center justify-center gap-4 py-16">
			<NokodoLoader expanded={true} />
		</div>
	{:else if error}
		<div
			class="rounded-2xl border border-red-900/50 bg-red-900/10 p-6 text-center text-red-400"
		>
			<p>{error}</p>
			<Button variant="outline" class="mt-4 rounded-xl" onclick={loadServers}>retry</Button>
		</div>
	{:else}
		<div class="flex items-center justify-end">
			<div class="flex items-center gap-2">
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => (pageIndex = Math.max(0, pageIndex - 1))}
					disabled={pageIndex === 0}
				>
					<ChevronLeft class="mr-1.5 h-4 w-4" />
					prev
				</Button>
				<span class="text-xs text-zinc-400 tabular-nums">
					{filteredServers.length > 0
						? `items ${pageIndex * limit + 1}–${pageIndex * limit + visibleServers.length} of ${filteredServers.length}`
						: ''}
				</span>
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => (pageIndex += 1)}
					disabled={!hasNext}
				>
					next
					<ChevronRight class="ml-1.5 h-4 w-4" />
				</Button>
			</div>
		</div>

		<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
			{#each visibleServers as server (server.id)}
				<Card
					class="flex shrink-0 cursor-pointer flex-col overflow-hidden rounded-2xl border-zinc-800 bg-zinc-900 transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
					onclick={() => openEditModal(server)}
					onkeydown={(event) => {
						if (event.key === 'Enter' || event.key === ' ') {
							event.preventDefault()
							openEditModal(server)
						}
					}}
					role="button"
					tabindex={0}
				>
					<CardHeader class="border-b border-zinc-800/50 px-4 py-4">
						<div class="flex items-start justify-between gap-4">
							<div class="flex min-w-0 flex-1 items-start gap-3">
								<div
									class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-300"
								>
									<Network class="h-4 w-4" />
								</div>
								<div class="min-w-0 flex-1">
									<CardTitle class="truncate text-base">{server.name}</CardTitle>
									<div class="mt-1 flex flex-wrap items-center gap-1.5">
										<span
											class="rounded-full px-2 py-0.5 text-[11px] {statusClass(
												server
											)}"
										>
											{server.status}
										</span>
										<span
											class="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-400"
										>
											{server.scope}
										</span>
										{#if !server.enabled}
											<span
												class="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-300"
											>
												disabled
											</span>
										{/if}
									</div>
								</div>
							</div>
						</div>
					</CardHeader>
					<CardContent class="flex flex-1 flex-col gap-3 px-4 py-4 text-xs text-zinc-500">
						{#if server.description}
							<p class="line-clamp-2 leading-5">{server.description}</p>
						{/if}
						<div class="space-y-2">
							<div class="flex items-center justify-between gap-2">
								<span class="shrink-0 font-medium text-zinc-600">url</span>
								<span class="truncate font-mono text-zinc-300"
									>{server.url ?? 'none'}</span
								>
							</div>
							<div class="flex items-center justify-between gap-2">
								<span class="shrink-0 font-medium text-zinc-600">discovered</span>
								<span class="truncate text-zinc-300">{capabilityCount(server)}</span
								>
							</div>
							<div class="flex items-center justify-between gap-2">
								<span class="shrink-0 font-medium text-zinc-600">updated</span>
								<span class="truncate text-zinc-300"
									>{formatDate(server.last_discovered_at)}</span
								>
							</div>
						</div>
						{#if server.last_error}
							<div class="flex gap-2 rounded-xl bg-red-500/10 p-2 text-red-300">
								<CircleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />
								<span class="line-clamp-2">{server.last_error}</span>
							</div>
						{/if}
					</CardContent>
				</Card>
			{/each}

			{#if filteredServers.length === 0 && searchQuery.trim()}
				<div
					class="col-span-full rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no MCP servers match your search
				</div>
			{/if}

			{#if servers.length === 0 && !searchQuery.trim()}
				<EmptyState message="no MCP servers yet." hint="add a server to start discovery." />
			{/if}
		</div>
	{/if}
</div>

<Dialog.Root
	bind:open={showModal}
	onOpenChange={(open) => {
		if (!open) closeModal()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			data-dialog-content
			class="fixed top-1/2 left-1/2 z-50 flex h-[min(760px,calc(100vh-2rem))] w-[min(980px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">
						{modalMode === 'create' ? 'add MCP server' : 'MCP server properties'}
					</Dialog.Title>
				</div>
				<Button variant="ghost" size="icon" class="rounded-xl" onclick={closeModal}>
					<X class="h-4 w-4" />
				</Button>
			</div>

			<form onsubmit={handleSubmit} class="flex min-h-0 flex-1 flex-col">
				{#if submitError}
					<div class="mx-6 mt-4 rounded-lg bg-red-900/20 p-3 text-sm text-red-400">
						{submitError}
					</div>
				{/if}

				<div class="grid min-h-0 flex-1 grid-cols-1 sm:grid-cols-[180px_1fr]">
					<nav
						class="flex shrink-0 gap-1 overflow-x-auto border-b border-zinc-800 px-3 py-3 sm:flex-col sm:gap-1 sm:overflow-x-visible sm:border-r sm:border-b-0 sm:py-4"
						aria-label="MCP server sections"
					>
						{#each sections as section (section.value)}
							<button
								type="button"
								onclick={() => (activeSection = section.value)}
								class="shrink-0 rounded-lg px-3 py-1.5 text-left text-sm transition-colors {activeSection ===
								section.value
									? 'bg-zinc-800 text-zinc-100'
									: 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'}"
							>
								{section.label}
							</button>
						{/each}
					</nav>

					<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
						{#if activeSection === 'properties'}
							{#if modalMode === 'edit' && selectedServer}
								<div
									class="grid gap-3 rounded-xl border border-zinc-800 bg-zinc-950/40 p-3 text-xs text-zinc-500 sm:grid-cols-3"
								>
									<div>
										<div class="font-medium text-zinc-600">status</div>
										<div class="mt-1">
											<span
												class="rounded-full px-2 py-0.5 text-[11px] {statusClass(
													selectedServer
												)}"
											>
												{selectedServer.status}
											</span>
										</div>
									</div>
									<div>
										<div class="font-medium text-zinc-600">scope</div>
										<div class="mt-1 text-zinc-300">{selectedServer.scope}</div>
									</div>
									<div>
										<div class="font-medium text-zinc-600">credentials</div>
										<div class="mt-1 text-zinc-300">
											{selectedServer.has_credentials ? 'stored' : 'none'}
										</div>
									</div>
									<div>
										<div class="font-medium text-zinc-600">last discovery</div>
										<div class="mt-1 text-zinc-300">
											{formatDate(selectedServer.last_discovered_at)}
										</div>
									</div>
								</div>
								{#if selectedServer.status === 'error' && selectedServer.last_error}
									<div
										class="rounded-xl border border-red-900/40 bg-red-900/20 p-3 text-xs text-red-300"
									>
										<div class="font-medium text-red-400">last error</div>
										<div class="mt-1 wrap-break-word">
											{selectedServer.last_error}
										</div>
									</div>
								{/if}
							{/if}

							<div class="space-y-2">
								<Label for="mcp-name">name</Label>
								<Input
									id="mcp-name"
									bind:value={formName}
									required
									class="rounded-xl"
								/>
							</div>

							<div class="space-y-2">
								<Label for="mcp-description">description (optional)</Label>
								<textarea
									id="mcp-description"
									bind:value={formDescription}
									rows={3}
									class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
								></textarea>
							</div>

							<div class="space-y-2">
								<Label for="mcp-url">streamable HTTP URL</Label>
								<Input
									id="mcp-url"
									bind:value={formUrl}
									placeholder="https://example.com/mcp"
									class="rounded-xl"
								/>
							</div>

							<div class="grid gap-4 sm:grid-cols-2">
								<div class="space-y-2">
									<Label>auth</Label>
									<Select
										value={formAuthType}
										onValueChange={(value: string) =>
											(formAuthType = value as MCPAuthType)}
									>
										<SelectTrigger class="w-full rounded-xl">
											<span>{formAuthType}</span>
										</SelectTrigger>
										<SelectContent>
											<SelectItem value="none">none</SelectItem>
											<SelectItem value="bearer">bearer</SelectItem>
											<SelectItem value="oauth_2.1">OAuth 2.1</SelectItem>
										</SelectContent>
									</Select>
								</div>
								<div class="space-y-2">
									<Label for="mcp-token">access token (secret)</Label>
									<Input
										id="mcp-token"
										type="password"
										bind:value={formAccessToken}
										placeholder={modalMode === 'edit'
											? 'leave blank to keep current token'
											: ''}
										autocomplete="off"
										class="rounded-xl"
									/>
								</div>
							</div>

							<div class="grid gap-3 sm:grid-cols-2">
								<div class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
									<div class="flex items-start justify-between gap-4">
										<div class="space-y-1">
											<Label for="mcp-enabled">server enabled</Label>
											<p class="text-xs text-zinc-500">
												allow runtime calls from this server.
											</p>
										</div>
										<Switch id="mcp-enabled" bind:checked={formEnabled} />
									</div>
								</div>
								<div class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
									<div class="flex items-start justify-between gap-4">
										<div class="space-y-1">
											<Label for="mcp-tools">tools</Label>
											<p class="text-xs text-zinc-500">
												publish discovered tools as plugins.
											</p>
										</div>
										<Switch id="mcp-tools" bind:checked={formTools} />
									</div>
								</div>
								<div class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
									<div class="flex items-start justify-between gap-4">
										<div class="space-y-1">
											<Label for="mcp-resources">resources</Label>
											<p class="text-xs text-zinc-500">
												keep resource snapshots available.
											</p>
										</div>
										<Switch
											id="mcp-resources"
											bind:checked={formResources}
											disabled={selectedServer?.scope === 'user'}
										/>
									</div>
								</div>
								<div class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
									<div class="flex items-start justify-between gap-4">
										<div class="space-y-1">
											<Label for="mcp-prompts">prompts</Label>
											<p class="text-xs text-zinc-500">
												publish discovered prompts to the prompt catalog.
											</p>
										</div>
										<Switch
											id="mcp-prompts"
											bind:checked={formPrompts}
											disabled={selectedServer?.scope === 'user'}
										/>
									</div>
								</div>
							</div>
						{:else if activeSection === 'tools'}
							{#if selectedServer && selectedServer.discovered_tools?.length}
								<div class="space-y-3">
									<div class="text-xs text-zinc-500">
										{enabledToolCount(selectedServer)} of {selectedServer
											.discovered_tools.length} enabled
									</div>
									{#each selectedServer.discovered_tools as tool (tool.id)}
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4"
										>
											<div class="flex items-start justify-between gap-4">
												<div class="flex min-w-0 gap-3">
													<div
														class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-zinc-900 text-zinc-300"
													>
														<Wrench class="h-4 w-4" />
													</div>
													<div class="min-w-0 space-y-1">
														<div
															class="text-sm font-medium wrap-anywhere text-zinc-100"
														>
															{tool.name}
														</div>
														<p
															class="text-xs leading-5 wrap-anywhere text-zinc-500"
														>
															{toolDescription(tool)}
														</p>
													</div>
												</div>
												<Switch
													checked={tool.enabled}
													disabled={capabilitySaving('tool', tool.id)}
													onCheckedChange={(enabled: boolean) =>
														toggleCapability('tool', tool.id, enabled)}
												/>
											</div>
										</div>
									{/each}
								</div>
							{:else}
								<p class="text-sm text-zinc-500">no tools discovered.</p>
							{/if}
						{:else if activeSection === 'resources'}
							{#if selectedServer && selectedServer.discovered_resources?.length}
								<div class="space-y-3">
									<div class="text-xs text-zinc-500">
										{enabledResourceCount(selectedServer)} of {selectedServer
											.discovered_resources.length} enabled
									</div>
									{#each selectedServer.discovered_resources as resource (resource.id)}
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4"
										>
											<div class="flex items-start justify-between gap-4">
												<div class="flex min-w-0 gap-3">
													<div
														class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-zinc-900 text-zinc-300"
													>
														<Database class="h-4 w-4" />
													</div>
													<div class="min-w-0 space-y-1">
														<div
															class="text-sm font-medium wrap-anywhere text-zinc-100"
														>
															{resource.name}
														</div>
														<p
															class="text-xs leading-5 wrap-anywhere text-zinc-500"
														>
															{resourceDescription(resource)}
														</p>
														{#if resource.mime_type}
															<div class="text-[11px] text-zinc-600">
																{resource.mime_type}
															</div>
														{/if}
													</div>
												</div>
												<Switch
													checked={resource.enabled}
													disabled={capabilitySaving(
														'resource',
														resource.id
													)}
													onCheckedChange={(enabled: boolean) =>
														toggleCapability(
															'resource',
															resource.id,
															enabled
														)}
												/>
											</div>
										</div>
									{/each}
								</div>
							{:else}
								<p class="text-sm text-zinc-500">no resources discovered.</p>
							{/if}
						{:else if activeSection === 'prompts'}
							{#if selectedServer && selectedServer.discovered_prompts?.length}
								<div class="space-y-3">
									<div class="text-xs text-zinc-500">
										{enabledPromptCount(selectedServer)} of {selectedServer
											.discovered_prompts.length} enabled
									</div>
									{#each selectedServer.discovered_prompts as prompt (prompt.id)}
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4"
										>
											<div class="flex items-start justify-between gap-4">
												<div class="flex min-w-0 gap-3">
													<div
														class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-zinc-900 text-zinc-300"
													>
														<FileText class="h-4 w-4" />
													</div>
													<div class="min-w-0 space-y-1">
														<div
															class="text-sm font-medium wrap-anywhere text-zinc-100"
														>
															{prompt.name}
														</div>
														<p
															class="text-xs leading-5 wrap-anywhere text-zinc-500"
														>
															{promptDescription(prompt)}
														</p>
													</div>
												</div>
												<Switch
													checked={prompt.enabled}
													disabled={capabilitySaving('prompt', prompt.id)}
													onCheckedChange={(enabled: boolean) =>
														toggleCapability(
															'prompt',
															prompt.id,
															enabled
														)}
												/>
											</div>
										</div>
									{/each}
								</div>
							{:else}
								<p class="text-sm text-zinc-500">no prompts discovered.</p>
							{/if}
						{/if}
					</div>
				</div>

				<div
					class="flex shrink-0 flex-col gap-3 border-t border-zinc-800 px-6 py-4 sm:flex-row sm:items-center sm:justify-between"
				>
					<div class="flex flex-col gap-2 sm:flex-row">
						{#if modalMode === 'edit' && editingId !== null}
							<Button
								type="button"
								variant="outline"
								class="gap-2 rounded-xl"
								disabled={isLoading || isDiscovering}
								onclick={discoverSelectedServer}
							>
								<RefreshCw class="h-4 w-4 {isDiscovering ? 'animate-spin' : ''}" />
								{isDiscovering ? 'discovering...' : 'discover'}
							</Button>
							<Button
								type="button"
								variant="outline"
								class="gap-2 rounded-xl text-red-400 hover:text-red-300"
								disabled={isLoading || isDiscovering}
								onclick={handleDelete}
							>
								<Trash2 class="h-4 w-4" />
								delete
							</Button>
						{/if}
					</div>
					<div class="flex flex-col gap-2 sm:flex-row sm:justify-end">
						<Button
							type="submit"
							class="gap-2 rounded-xl"
							disabled={isLoading || !formName.trim()}
						>
							{#if isLoading}
								<RefreshCw class="h-4 w-4 animate-spin" />
								saving...
							{:else}
								<Save class="h-4 w-4" />
								save
							{/if}
						</Button>
					</div>
				</div>
			</form>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
