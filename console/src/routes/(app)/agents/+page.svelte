<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type Agent = Schemas['Agent']
	type AgentCreate = Schemas['AgentCreate']
	type AgentUpdate = Schemas['AgentUpdate']
	type Model = Schemas['Model']
	type PluginInfo = Schemas['PluginInfo']
	type Prompt = Schemas['Prompt']
	type Provider = Schemas['Provider']

	import AclModal from '$lib/components/AclModal.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ModelParamsEditor from '$lib/components/ModelParamsEditor.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import PromptVariablesLegend from '$lib/components/PromptVariablesLegend.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import {
		ArrowDown,
		ArrowUp,
		BookOpen,
		FileText,
		Pencil,
		Plus,
		Search,
		Shield,
		Trash2,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'
	import { onMount } from 'svelte'

	const TEMPLATE_SYSTEM_PROMPT = `you are a helpful AI assistant.

today is {{ current_datetime_full }}.
user: {{ user_name }}.

<long_term_memory>{{ user_memories }}</long_term_memory>

<chat_context>{{ chat_context }}</chat_context>

{{ referenced_attachments }}`

	type SortKey = 'name' | 'model' | 'plugins'
	type SortDir = 'asc' | 'desc'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'name', label: 'name' },
		{ value: 'model', label: 'model' },
		{ value: 'plugins', label: 'plugins' },
	]

	let sortKey = $state<SortKey>('name')
	let sortDir = $state<SortDir>('asc')
	let searchQuery = $state('')

	let agents = $state<Agent[]>([])
	let models = $state<Model[]>([])
	let providers = $state<Provider[]>([])
	let availableToolPlugins = $state<PluginInfo[]>([])
	let availableFilterPlugins = $state<PluginInfo[]>([])
	let legendPrompts = $state<Prompt[]>([])

	let showModal = $state(false)
	let modalMode = $state<'create' | 'edit'>('create')
	let editingId = $state<string | null>(null)
	let isFetching = $state(true)
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let submitError = $state<string | null>(null)

	let showAclModal = $state(false)
	let aclAgentId = $state('')
	let showVariablesLegend = $state(false)

	let formName = $state('')
	let formDescription = $state('')
	let formSystemPrompt = $state('')
	let formModelId = $state<string>('')
	let formPluginIds = $state<string[]>([])
	let formProfileImageUrl = $state('')
	let formProfileImageFileId = $state('')
	let configParams = $state<Record<string, unknown>>({})

	let selectedModelType = $derived.by(() => {
		if (!formModelId) return null
		const m = models.find((m) => m.id === formModelId)
		return (m?.model_type ?? null) as
			| 'chat_model'
			| 'embedding'
			| 'image'
			| 'audio'
			| 'video'
			| null
	})

	const chatModels = $derived(models.filter((m) => m.model_type === 'chat_model'))

	const filteredAgents = $derived.by(() => {
		let result = agents
		if (searchQuery.trim()) {
			const q = searchQuery.toLowerCase()
			result = result.filter(
				(a) =>
					(a.name ?? '').toLowerCase().includes(q) ||
					(a.description ?? '').toLowerCase().includes(q) ||
					a.id.toLowerCase().includes(q)
			)
		}
		const dir = sortDir === 'asc' ? 1 : -1
		return [...result].sort((a, b) => {
			switch (sortKey) {
				case 'name':
					return (a.name ?? '').localeCompare(b.name ?? '') * dir
				case 'model':
					return getModelLabel(a.model_id).localeCompare(getModelLabel(b.model_id)) * dir
				case 'plugins':
					return ((a.plugin_ids?.length ?? 0) - (b.plugin_ids?.length ?? 0)) * dir
				default:
					return 0
			}
		})
	})

	function setSort(next: SortKey) {
		if (sortKey === next) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc'
		} else {
			sortKey = next
			sortDir = 'asc'
		}
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
	}

	async function fetchData() {
		isFetching = true
		error = null
		try {
			const [
				agentsData,
				modelsData,
				providersData,
				toolPluginsData,
				filterPluginsData,
				promptsData,
			] = await Promise.all([
				api.GET('/v1/agents').then((r) => unwrap(r)),
				api.GET('/v1/models').then((r) => unwrap(r)),
				api.GET('/v1/providers').then((r) => unwrap(r)),
				api
					.GET('/v1/plugins/available', {
						params: { query: { plugin_type: 'tool' } },
					})
					.then((r) => unwrap(r)),
				api
					.GET('/v1/plugins/available', {
						params: { query: { plugin_type: 'filter' } },
					})
					.then((r) => unwrap(r)),
				api
					.GET('/v1/prompts', { params: { query: { limit: 200 } } })
					.then((r) => unwrap(r)),
			])
			agents = agentsData
			models = modelsData
			providers = providersData
			availableToolPlugins = toolPluginsData
			availableFilterPlugins = filterPluginsData
			legendPrompts = promptsData
		} catch (e) {
			console.error('Failed to load agents/models/plugins', e)
			error = 'failed to load agents'
		} finally {
			isFetching = false
		}
	}

	onMount(() => {
		fetchData()
	})

	function openCreateModal() {
		modalMode = 'create'
		editingId = null
		formName = ''
		formDescription = ''
		formSystemPrompt = ''
		formModelId = ''
		formPluginIds = []
		formProfileImageUrl = ''
		formProfileImageFileId = ''
		configParams = {}
		submitError = null
		showModal = true
	}

	function openEditModal(agent: Agent) {
		modalMode = 'edit'
		editingId = agent.id
		formName = agent.name ?? ''
		formDescription = agent.description ?? ''
		formSystemPrompt = agent.system_prompt ?? ''
		formModelId = agent.model_id ?? ''
		formPluginIds = agent.plugin_ids ?? []
		formProfileImageUrl = agent.profile_image_url ?? ''
		formProfileImageFileId = agent.profile_image_file_id ?? ''
		const agentConfig = (agent.config ?? {}) as Record<string, Record<string, unknown>>
		const agentModel = models.find((m) => m.id === agent.model_id)
		const mt = agentModel?.model_type ?? 'chat_model'
		configParams = agentConfig[mt] ?? {}
		submitError = null
		showModal = true
	}

	function closeModal() {
		showModal = false
	}

	async function handleSvgFileChange(e: Event) {
		const input = e.target as HTMLInputElement
		const file = input.files?.[0]
		if (!file) return
		if (file.type !== 'image/svg+xml' && !file.name.toLowerCase().endsWith('.svg')) {
			submitError = 'only svg files are supported for agent profile images'
			return
		}

		submitError = null
		const reader = new FileReader()
		reader.onload = () => {
			formProfileImageUrl = typeof reader.result === 'string' ? reader.result : ''
			formProfileImageFileId = ''
		}
		reader.onerror = () => {
			submitError = 'failed to read svg file'
		}
		reader.readAsDataURL(file)
	}

	function modelFullLabel(m: Model): string {
		const name = m.display_name || m.name || m.id
		const provider = providers.find((p) => p.id === m.provider_id)
		const providerName = provider?.name || m.provider_id
		const adapterType = provider?.adapter_type
		const modelAdapter = m.adapter
		const adapterPart = adapterType
			? modelAdapter && modelAdapter !== adapterType
				? `${adapterType}/${modelAdapter}`
				: adapterType
			: (modelAdapter ?? null)
		return [name, providerName, adapterPart].filter(Boolean).join(' · ')
	}

	function getModelLabel(modelId: string | null | undefined) {
		if (!modelId) return 'none'
		const m = models.find((m) => m.id === modelId)
		return m ? modelFullLabel(m) : modelId
	}

	function togglePlugin(pluginId: string) {
		if (formPluginIds.includes(pluginId)) {
			formPluginIds = formPluginIds.filter((id) => id !== pluginId)
		} else {
			formPluginIds = [...formPluginIds, pluginId]
		}
	}

	function formatSubmitError(err: unknown): string {
		if (err instanceof Error && err.message) return err.message
		return modalMode === 'create' ? 'failed to create agent' : 'failed to save agent'
	}

	function openAclModal(agentId: string) {
		aclAgentId = agentId
		showAclModal = true
	}

	async function handleDelete() {
		if (!editingId) return
		if (!confirm('are you sure you want to delete this agent?')) return
		isLoading = true
		submitError = null
		try {
			await api.DELETE('/v1/agents/{agent_id}', {
				params: { path: { agent_id: editingId } },
			})
			showModal = false
			await fetchData()
		} catch (err: unknown) {
			console.error('Failed to delete agent', err)
			submitError = err instanceof Error ? err.message : 'failed to delete agent'
		} finally {
			isLoading = false
		}
	}

	async function handleSubmit(e: Event) {
		e.preventDefault()
		isLoading = true
		submitError = null

		try {
			const normalizedProfileImageFileId = formProfileImageFileId.trim()
			const normalizedProfileImageUrl = formProfileImageUrl.trim()
			const profile_image_file_id = normalizedProfileImageFileId
				? normalizedProfileImageFileId
				: null
			const profile_image_url = profile_image_file_id
				? null
				: normalizedProfileImageUrl
					? normalizedProfileImageUrl
					: null

			if (modalMode === 'create') {
				const config =
					selectedModelType && Object.keys(configParams).length > 0
						? { [selectedModelType]: configParams }
						: {}
				const payload: AgentCreate = {
					name: formName.trim(),
					description: formDescription.trim() ? formDescription.trim() : null,
					system_prompt: formSystemPrompt.trim() ? formSystemPrompt.trim() : null,
					model_id: formModelId ? formModelId : null,
					plugin_ids: formPluginIds,
					config,
					profile_image_file_id,
					profile_image_url,
				}
				unwrap(await api.POST('/v1/agents', { body: payload }))
			} else if (editingId) {
				const config =
					selectedModelType && Object.keys(configParams).length > 0
						? { [selectedModelType]: configParams }
						: {}
				const payload: AgentUpdate = {
					name: formName.trim(),
					description: formDescription.trim() ? formDescription.trim() : null,
					system_prompt: formSystemPrompt.trim() ? formSystemPrompt.trim() : null,
					model_id: formModelId ? formModelId : null,
					plugin_ids: formPluginIds,
					config,
					profile_image_file_id,
					profile_image_url,
				}
				unwrap(
					await api.PATCH('/v1/agents/{agent_id}', {
						params: { path: { agent_id: editingId } },
						body: payload,
					})
				)
			}

			showModal = false
			await fetchData()
		} catch (err: unknown) {
			console.error(
				modalMode === 'create' ? 'Failed to create agent' : 'Failed to save agent',
				err
			)
			submitError = formatSubmitError(err)
		} finally {
			isLoading = false
		}
	}
</script>

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">agents</h2>
			<p class="text-zinc-400">create and manage agents.</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<div class="relative">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search agents..."
					bind:value={searchQuery}
					class="h-9 w-50 pl-8 lg:w-75"
				/>
			</div>
			<Select value={sortKey} onValueChange={(v: string) => setSort(v as SortKey)}>
				<SelectTrigger class="w-40 rounded-xl">
					<span class="truncate text-left">
						{sortOptions.find((o) => o.value === sortKey)?.label ?? sortKey}
					</span>
				</SelectTrigger>
				<SelectContent>
					{#each sortOptions as opt (opt.value)}
						<SelectItem value={opt.value}>{opt.label}</SelectItem>
					{/each}
				</SelectContent>
			</Select>
			<Button
				variant="outline"
				class="rounded-xl px-3"
				onclick={() => toggleSortDir()}
				disabled={isFetching}
				title="toggle sort direction"
				aria-label="toggle sort direction"
			>
				{#if sortDir === 'asc'}
					<ArrowUp class="h-4 w-4" />
				{:else}
					<ArrowDown class="h-4 w-4" />
				{/if}
			</Button>
			<Button onclick={openCreateModal} class="gap-2 rounded-xl">
				<Plus class="h-4 w-4" />
				add agent
			</Button>
			<Button
				variant="outline"
				class="rounded-xl"
				onclick={() => fetchData()}
				disabled={isFetching}
			>
				{isFetching ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	<div class="min-h-0 flex-1 overflow-y-auto">
		<div class="flex min-h-0 flex-1 flex-col gap-6">
			{#if isFetching}
				<div class="flex min-h-0 flex-1 flex-col items-center justify-center gap-4">
					<NokodoLoader expanded={true} />
				</div>
			{:else if error}
				<div
					class="rounded-2xl border border-red-900/50 bg-red-900/10 p-6 text-center text-red-400"
				>
					<p>{error}</p>
					<Button variant="outline" class="mt-4" onclick={fetchData}>Retry</Button>
				</div>
			{:else}
				<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
					{#each filteredAgents as agent (agent.id)}
						<Card
							class="overflow-hidden rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100"
						>
							<CardHeader>
								<div class="flex items-start justify-between">
									<div class="min-w-0 flex-1">
										<CardTitle class="truncate">{agent.name}</CardTitle>
										{#if agent.description}
											<CardDescription class="line-clamp-2"
												>{agent.description}</CardDescription
											>
										{/if}
									</div>
									<div class="flex shrink-0 gap-1">
										<Button
											variant="ghost"
											size="icon"
											class="h-8 w-8 text-zinc-500"
											onclick={() => openAclModal(agent.id)}
											title="access rules"
										>
											<Shield class="h-4 w-4" />
										</Button>
										<Button
											variant="ghost"
											size="icon"
											class="h-8 w-8 text-zinc-500"
											onclick={() => openEditModal(agent)}
											title="edit agent"
										>
											<Pencil class="h-4 w-4" />
										</Button>
									</div>
								</div>
							</CardHeader>
							<CardContent>
								<div class="space-y-1 text-sm text-zinc-400">
									<div class="flex justify-between gap-2">
										<span class="shrink-0">model:</span>
										<span class="truncate">{getModelLabel(agent.model_id)}</span
										>
									</div>
									{#if agent.plugin_ids && agent.plugin_ids.length > 0}
										<div class="flex justify-between">
											<span>plugins:</span>
											<span class="truncate">{agent.plugin_ids.length}</span>
										</div>
									{/if}
								</div>
							</CardContent>
						</Card>
					{/each}

					{#if filteredAgents.length === 0 && agents.length > 0}
						<div
							class="col-span-full rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
						>
							no agents match your search
						</div>
					{/if}

					{#if agents.length === 0}
						<EmptyState
							message="no agents yet."
							hint="create an agent to get started."
						/>
					{/if}
				</div>
			{/if}
		</div>
	</div>
</div>

<Dialog.Root
	bind:open={showModal}
	onOpenChange={(v) => {
		if (!v) closeModal()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[90vh] w-[min(512px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">
						{modalMode === 'create' ? 'create agent' : 'edit agent'}
					</Dialog.Title>
					<Dialog.Description class="text-sm text-zinc-400">
						define prompting + attach a model (optional).
					</Dialog.Description>
				</div>
				<Button variant="ghost" size="icon" class="rounded-xl" onclick={closeModal}>
					<X class="h-4 w-4" />
				</Button>
			</div>
			<form onsubmit={handleSubmit} class="flex min-h-0 flex-1 flex-col">
				<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
					{#if submitError}
						<div class="rounded-lg bg-red-900/20 p-3 text-sm text-red-400">
							{submitError}
						</div>
					{/if}

					{#if modalMode === 'edit' && editingId}
						<div class="space-y-1">
							<Label class="text-xs text-zinc-500">id</Label>
							<p class="font-mono text-xs text-zinc-400 select-all">{editingId}</p>
						</div>
					{/if}

					<div class="space-y-2">
						<Label for="name">name</Label>
						<Input
							id="name"
							bind:value={formName}
							required
							placeholder="e.g. nokodo coder"
							class="rounded-xl"
						/>
					</div>

					<div class="space-y-2">
						<Label for="profile_image_url">profile image url (optional)</Label>
						<Input
							id="profile_image_url"
							bind:value={formProfileImageUrl}
							placeholder="https://... or data:image/svg+xml;base64,..."
							class="rounded-xl"
						/>
						<p class="text-xs text-zinc-500">
							use a direct url, or upload an svg below to embed it as a data url.
						</p>
					</div>

					<div class="space-y-2">
						<Label for="profile_image_svg">upload svg (optional)</Label>
						<Input
							id="profile_image_svg"
							type="file"
							accept="image/svg+xml,.svg"
							onchange={handleSvgFileChange}
							class="rounded-xl"
						/>
					</div>

					<div class="space-y-2">
						<Label for="profile_image_file_id">profile image file id (optional)</Label>
						<Input
							id="profile_image_file_id"
							bind:value={formProfileImageFileId}
							placeholder="file_..."
							class="rounded-xl"
						/>
						<p class="text-xs text-zinc-500">if set, this overrides the url field.</p>
					</div>

					{#if formProfileImageUrl.trim()}
						<div
							class="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-950/40 p-3"
						>
							<img
								src={formProfileImageUrl}
								alt="agent profile preview"
								class="h-10 w-10 rounded-lg bg-zinc-800 object-contain"
							/>
							<div class="text-xs text-zinc-500">preview</div>
						</div>
					{/if}

					<div class="space-y-2">
						<Label for="model">model (optional)</Label>
						<Select
							value={formModelId}
							onValueChange={(v: string) => (formModelId = v)}
						>
							<SelectTrigger class="rounded-xl">
								<span class="truncate text-left">
									{formModelId ? getModelLabel(formModelId) : 'none'}
								</span>
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="">none</SelectItem>
								{#each chatModels as model (model.id)}
									<SelectItem value={model.id}>{modelFullLabel(model)}</SelectItem
									>
								{/each}
							</SelectContent>
						</Select>
					</div>

					{#if selectedModelType}
						<div class="border-t border-zinc-800 pt-4">
							<ModelParamsEditor
								modelType={selectedModelType}
								bind:params={configParams}
							/>
						</div>
					{/if}

					<div class="space-y-2">
						<Label for="description">description (optional)</Label>
						<textarea
							id="description"
							bind:value={formDescription}
							rows={3}
							placeholder="what does this agent do?"
							class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
						></textarea>
					</div>

					<div class="space-y-2">
						<div class="flex items-center justify-between">
							<Label for="system_prompt">system prompt (optional)</Label>
							<div class="flex items-center gap-1">
								<Button
									type="button"
									variant="ghost"
									size="sm"
									class="h-7 gap-1 text-xs text-zinc-400 hover:text-zinc-200"
									onclick={() => (formSystemPrompt = TEMPLATE_SYSTEM_PROMPT)}
								>
									<FileText class="h-3.5 w-3.5" />
									use template
								</Button>
								<Button
									type="button"
									variant="ghost"
									size="sm"
									class="h-7 gap-1 text-xs text-zinc-400 hover:text-zinc-200"
									onclick={() => (showVariablesLegend = true)}
								>
									<BookOpen class="h-3.5 w-3.5" />
									variables
								</Button>
							</div>
						</div>
						<textarea
							id="system_prompt"
							bind:value={formSystemPrompt}
							rows={6}
							placeholder="you are ..."
							class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm"
						></textarea>
					</div>

					{#if availableToolPlugins.length > 0}
						<div class="space-y-2">
							<Label>tools</Label>
							<div
								class="max-h-32 space-y-1 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950 p-3"
							>
								{#each availableToolPlugins as tool (tool.id)}
									<label
										class="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 hover:bg-zinc-800"
									>
										<input
											type="checkbox"
											checked={formPluginIds.includes(tool.id)}
											onchange={() => togglePlugin(tool.id)}
											class="h-4 w-4 rounded border-zinc-700 bg-zinc-900"
										/>
										<span class="text-sm">{tool.name}</span>
										{#if tool.is_native}
											<span
												class="rounded bg-zinc-700 px-1 text-xs text-zinc-400"
												>native</span
											>
										{/if}
									</label>
								{/each}
							</div>
						</div>
					{/if}

					{#if availableFilterPlugins.length > 0}
						<div class="space-y-2">
							<Label>filters</Label>
							<div
								class="max-h-32 space-y-1 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950 p-3"
							>
								{#each availableFilterPlugins as filter (filter.id)}
									<label
										class="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 hover:bg-zinc-800"
									>
										<input
											type="checkbox"
											checked={formPluginIds.includes(filter.id)}
											onchange={() => togglePlugin(filter.id)}
											class="h-4 w-4 rounded border-zinc-700 bg-zinc-900"
										/>
										<span class="text-sm">{filter.name}</span>
										{#if filter.is_native}
											<span
												class="rounded bg-zinc-700 px-1 text-xs text-zinc-400"
												>native</span
											>
										{/if}
									</label>
								{/each}
							</div>
						</div>
					{/if}
				</div>
				<div class="flex shrink-0 justify-between gap-2 border-t border-zinc-800 px-6 py-4">
					<div class="flex gap-2">
						{#if modalMode === 'edit' && editingId}
							<Button
								type="button"
								variant="outline"
								class="gap-2 rounded-xl text-red-400 hover:text-red-300"
								disabled={isLoading}
								onclick={handleDelete}
							>
								<Trash2 class="h-4 w-4" />
								delete
							</Button>
							<Button
								type="button"
								variant="outline"
								class="gap-2 rounded-xl"
								disabled={isLoading}
								onclick={() => {
									showModal = false
									openAclModal(editingId!)
								}}
							>
								<Shield class="h-4 w-4" />
								access rules
							</Button>
						{/if}
					</div>
					<div class="flex gap-2">
						<Button
							type="button"
							variant="outline"
							class="rounded-xl"
							disabled={isLoading}
							onclick={closeModal}
						>
							cancel
						</Button>
						<Button
							type="submit"
							class="rounded-xl"
							disabled={isLoading || !formName.trim()}
						>
							{#if isLoading}
								{modalMode === 'create' ? 'creating…' : 'saving…'}
							{:else}
								{modalMode === 'create' ? 'create agent' : 'save changes'}
							{/if}
						</Button>
					</div>
				</div>
			</form>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<AclModal
	bind:open={showAclModal}
	resourceType="agent"
	resourceId={aclAgentId}
	title="agent access rules"
/>

<PromptVariablesLegend bind:open={showVariablesLegend} prompts={legendPrompts} />
