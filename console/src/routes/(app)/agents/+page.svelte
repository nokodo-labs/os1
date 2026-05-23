<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type Agent = Schemas['Agent']
	type AgentCreate = Schemas['AgentCreate']
	type AgentUpdate = Schemas['AgentUpdate']
	type Model = Schemas['Model']
	type PluginInfo = Schemas['PluginInfo']
	type Provider = Schemas['Provider']

	import AccessRulesButton from '$lib/components/AccessRulesButton.svelte'
	import AclModal from '$lib/components/AclModal.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ModelParamsEditor from '$lib/components/ModelParamsEditor.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import PromptVariablesLegend from '$lib/components/PromptVariablesLegend.svelte'
	import SearchableModelPicker from '$lib/components/SearchableModelPicker.svelte'
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
	import { Switch } from '$lib/components/ui/switch'
	import {
		ArrowDown,
		ArrowUp,
		Bell,
		BookOpen,
		Bot,
		Brain,
		CalendarDays,
		ChevronLeft,
		ChevronRight,
		CodeXml,
		Earth,
		Eye,
		FileText,
		Funnel as FilterIcon,
		FolderOpen,
		Image as ImageIcon,
		MessageSquare,
		Paperclip,
		Pencil,
		Plus,
		RefreshCw,
		Save,
		Search,
		Sparkles,
		Trash2,
		Wrench,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	const TEMPLATE_SYSTEM_PROMPT = `you are a helpful AI assistant.

today is {{ current_datetime_full }}.
user: {{ user_name }}.

<long_term_memory>{{ user_memories }}</long_term_memory>

<chat_context>{{ chat_context }}</chat_context>

{{ referenced_attachments }}`

	type SortKey = 'name' | 'created_at' | 'updated_at'
	type SortDir = 'asc' | 'desc'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'name', label: 'name' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'updated_at', label: 'updated at' },
	]

	let sortKey = $state<SortKey>('name')
	let sortDir = $state<SortDir>('asc')
	let searchQuery = $state('')
	let serverSearchQuery = $state('')
	let searchTimer: ReturnType<typeof setTimeout> | null = null
	let pageIndex = $state(0)
	let limit = $state(24)
	let hasNext = $state(false)
	let agentTotal = $state(0)
	let refreshToken = $state(0)
	let fetchRequestId = 0

	let agents = $state<Agent[]>([])
	let models = $state<Model[]>([])
	let providers = $state<Provider[]>([])
	let availableToolPlugins = $state<PluginInfo[]>([])
	let availableFilterPlugins = $state<PluginInfo[]>([])
	let availableHookPlugins = $state<PluginInfo[]>([])

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
	let formProfileImageValue = $state('')
	let configParams = $state<Record<string, unknown>>({})
	let formSteeringEnabled = $state(true)
	// preserve feature keys this ui does not edit yet.
	let originalFeatures = $state<Record<string, unknown>>({})

	type Section = 'overview' | 'model' | 'prompt' | 'plugins' | 'config'
	type PluginIconKind =
		| 'memory'
		| 'note'
		| 'reminder'
		| 'calendar'
		| 'file'
		| 'web'
		| 'search'
		| 'image'
		| 'code'
		| 'reveal'
		| 'attachment'
		| 'notification'
		| 'think'
		| 'chat'
		| 'time'
		| 'filter'
		| 'hook'
		| 'tool'
	type NativePluginInfo = {
		label: string
		description: string
		icon: PluginIconKind
	}
	type PluginMetadataKey = `${PluginInfo['type']}:${string}`
	let activeSection = $state<Section>('overview')
	const sections: Array<{ value: Section; label: string }> = [
		{ value: 'overview', label: 'overview' },
		{ value: 'model', label: 'model' },
		{ value: 'prompt', label: 'prompt' },
		{ value: 'plugins', label: 'plugins' },
		{ value: 'config', label: 'config' },
	]
	const defaultAgentPluginIds = [
		'chat_context',
		'file_resolve',
		'citation_index',
		'context_compaction',
	]

	function pluginMetadataKey(
		pluginType: PluginInfo['type'],
		pluginId: string
	): PluginMetadataKey {
		return `${pluginType}:${pluginId}`
	}

	const nativePluginInfo = new Map<PluginMetadataKey, NativePluginInfo>([
		[
			pluginMetadataKey('filter', 'chat_context'),
			{
				label: 'recall chats',
				description:
					'fills the chat_context prompt variable with relevant or recent conversation history.',
				icon: 'chat',
			},
		],
		[
			pluginMetadataKey('filter', 'file_resolve'),
			{
				label: 'resolve files',
				description:
					'loads attached file data from file ids so the model can see the actual image or file.',
				icon: 'file',
			},
		],
		[
			pluginMetadataKey('filter', 'citation_index'),
			{
				label: 'index citations',
				description:
					'adds numbered source markers to citeable tool results and exposes the source list to the model.',
				icon: 'search',
			},
		],
		[
			pluginMetadataKey('filter', 'context_compaction'),
			{
				label: 'compact context',
				description:
					'keeps long chats inside the model limit by using summaries, trimming history, and compacting old tool results.',
				icon: 'filter',
			},
		],
		[
			pluginMetadataKey('tool', 'resource_search'),
			{
				label: 'search resources',
				description:
					'searches chats, notes, reminders, calendar events, projects, and files.',
				icon: 'search',
			},
		],
		[
			pluginMetadataKey('tool', 'chat_get'),
			{
				label: 'read chats',
				description: 'searches, lists, and reads chats and chat messages.',
				icon: 'chat',
			},
		],
		[
			pluginMetadataKey('tool', 'think'),
			{
				label: 'think',
				description: 'lets the agent reason through a task before acting.',
				icon: 'think',
			},
		],
		[
			pluginMetadataKey('tool', 'agentic_web_search'),
			{
				label: 'agentic web search',
				description:
					'preferred for web questions. searches, reads, summarizes, and returns concise cited results.',
				icon: 'web',
			},
		],
		[
			pluginMetadataKey('tool', 'web_search'),
			{
				label: 'raw web search',
				description:
					'advanced fallback. returns raw results and snippets, which can use many tokens; prefer agentic web search.',
				icon: 'web',
			},
		],
		[
			pluginMetadataKey('tool', 'fetch_url'),
			{
				label: 'open webpages',
				description: 'reads a specific webpage by URL.',
				icon: 'web',
			},
		],
		[
			pluginMetadataKey('tool', 'memory_recall'),
			{
				label: 'recall memories',
				description: 'searches long-term memories available to the agent.',
				icon: 'memory',
			},
		],
		[
			pluginMetadataKey('tool', 'memory_create'),
			{
				label: 'save memories',
				description: 'stores useful long-term memory for future runs.',
				icon: 'memory',
			},
		],
		[
			pluginMetadataKey('tool', 'note_get'),
			{
				label: 'read notes',
				description: 'searches, lists, and reads notes.',
				icon: 'note',
			},
		],
		[
			pluginMetadataKey('tool', 'note_write'),
			{
				label: 'write notes',
				description: 'creates, updates, and deletes notes.',
				icon: 'note',
			},
		],
		[
			pluginMetadataKey('tool', 'project_get'),
			{
				label: 'read projects',
				description: 'searches, lists, and reads projects.',
				icon: 'file',
			},
		],
		[
			pluginMetadataKey('tool', 'calendar_event_get'),
			{
				label: 'read calendar',
				description:
					'searches calendar events or returns upcoming scheduled items from calendars and reminder lists.',
				icon: 'calendar',
			},
		],
		[
			pluginMetadataKey('tool', 'calendar_event_write'),
			{
				label: 'write calendar events',
				description: 'creates, updates, and deletes calendar events.',
				icon: 'calendar',
			},
		],
		[
			pluginMetadataKey('tool', 'reminder_get'),
			{
				label: 'read reminders',
				description:
					'searches reminders and reminder lists, or reads a specific reminder/list.',
				icon: 'reminder',
			},
		],
		[
			pluginMetadataKey('tool', 'reminder_write'),
			{
				label: 'write reminders',
				description: 'creates, updates, completes, and deletes reminders.',
				icon: 'reminder',
			},
		],
		[
			pluginMetadataKey('tool', 'file_get'),
			{
				label: 'read files',
				description: 'searches, lists, and reads files.',
				icon: 'file',
			},
		],
		[
			pluginMetadataKey('tool', 'file_edit'),
			{
				label: 'edit files',
				description: 'creates, updates, and deletes files.',
				icon: 'file',
			},
		],
		[
			pluginMetadataKey('tool', 'generate_image'),
			{
				label: 'create images',
				description: 'generates or edits images.',
				icon: 'image',
			},
		],
		[
			pluginMetadataKey('tool', 'generate_video'),
			{
				label: 'create videos',
				description: 'generates videos.',
				icon: 'image',
			},
		],
		[
			pluginMetadataKey('tool', 'generate_audio'),
			{
				label: 'create audio',
				description: 'generates audio clips.',
				icon: 'attachment',
			},
		],
		[
			pluginMetadataKey('tool', 'code_interpreter'),
			{
				label: 'run code',
				description: 'runs Python code in a sandbox for analysis and generated files.',
				icon: 'code',
			},
		],
		[
			pluginMetadataKey('tool', 'send_notification'),
			{
				label: 'send notifications',
				description: 'sends notifications to chat participants or a specific user.',
				icon: 'notification',
			},
		],
		[
			pluginMetadataKey('tool', 'reveal_attachment'),
			{
				label: 'reveal attachments',
				description: 'shows a generated or hidden attachment in the chat.',
				icon: 'reveal',
			},
		],
	])

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
	const pluginGroups = $derived.by(() =>
		[
			{
				label: 'tools',
				description: 'actions an agent can call while it is working.',
				plugins: availableToolPlugins,
			},
			{
				label: 'filters',
				description: 'context processors that shape messages before the model runs.',
				plugins: orderedPlugins(availableFilterPlugins),
			},
			{
				label: 'hooks',
				description: 'post-processing hooks that run around agent activity.',
				plugins: availableHookPlugins,
			},
		].filter((group) => group.plugins.length > 0)
	)

	const profileImagePreviewSrc = $derived.by(() => {
		const value = formProfileImageValue.trim()
		return profileImageInputKind(value) === 'url' ? value : ''
	})

	const visibleAgents = $derived(agents)

	function setSort(next: SortKey) {
		if (sortKey === next) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc'
		} else {
			sortKey = next
			sortDir = 'asc'
		}
		pageIndex = 0
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
		pageIndex = 0
	}

	function scheduleSearch() {
		pageIndex = 0
		if (searchTimer) clearTimeout(searchTimer)
		searchTimer = setTimeout(() => {
			serverSearchQuery = searchQuery.trim()
		}, 250)
	}

	function profileImageInputKind(value: string): 'empty' | 'url' | 'file' {
		const normalized = value.trim()
		if (!normalized) return 'empty'
		if (/^(https?:\/\/|data:image\/|blob:|\/)/i.test(normalized)) return 'url'
		return 'file'
	}

	function profileImageModeLabel(value: string): string {
		switch (profileImageInputKind(value)) {
			case 'url':
				return 'url'
			case 'file':
				return 'file id'
			default:
				return 'empty'
		}
	}

	function pluginMetadata(plugin: PluginInfo): NativePluginInfo | null {
		return nativePluginInfo.get(pluginMetadataKey(plugin.type, plugin.id)) ?? null
	}

	function isDefaultAgentPlugin(pluginId: string): boolean {
		return defaultAgentPluginIds.includes(pluginId)
	}

	function defaultAgentPluginOrder(pluginId: string): number {
		const index = defaultAgentPluginIds.indexOf(pluginId)
		return index === -1 ? Number.MAX_SAFE_INTEGER : index
	}

	function orderedPlugins(plugins: PluginInfo[]): PluginInfo[] {
		return [...plugins].sort((left, right) => {
			const leftOrder = defaultAgentPluginOrder(left.id)
			const rightOrder = defaultAgentPluginOrder(right.id)
			if (leftOrder !== rightOrder) return leftOrder - rightOrder
			return pluginDisplayName(left).localeCompare(pluginDisplayName(right))
		})
	}

	function pluginDisplayName(plugin: PluginInfo): string {
		const nativeInfo = pluginMetadata(plugin)
		if (nativeInfo) return nativeInfo.label
		return (plugin.name || plugin.id).replaceAll('_', ' ')
	}

	function pluginDescription(plugin: PluginInfo): string {
		const nativeInfo = pluginMetadata(plugin)
		if (nativeInfo) return nativeInfo.description
		if (plugin.type === 'tool') return 'lets the agent call an action during a run.'
		const description = plugin.description?.trim()
		if (description) return description
		if (plugin.type === 'filter') return 'shapes conversation context before model calls.'
		return 'runs additional processing around agent activity.'
	}

	function pluginIconKind(plugin: PluginInfo): PluginIconKind {
		const nativeInfo = pluginMetadata(plugin)
		if (nativeInfo) return nativeInfo.icon
		if (plugin.type === 'filter') return 'filter'
		if (plugin.type === 'hook') return 'hook'
		const id = plugin.id.toLowerCase()
		if (id.includes('memory')) return 'memory'
		if (id.includes('note')) return 'note'
		if (id.includes('reminder')) return 'reminder'
		if (id.includes('calendar')) return 'calendar'
		if (id.includes('file')) return 'file'
		if (id.includes('search') || id.includes('url')) return 'web'
		if (id.includes('image')) return 'image'
		if (id.includes('code')) return 'code'
		if (id.includes('reveal')) return 'reveal'
		if (id.includes('attachment')) return 'attachment'
		if (id.includes('notification')) return 'notification'
		if (id.includes('think')) return 'think'
		if (id.includes('chat')) return 'chat'
		if (id.includes('timestamp')) return 'time'
		return 'tool'
	}

	async function fetchData() {
		const request = {
			id: ++fetchRequestId,
			pageIndex,
			limit,
			sortKey,
			sortDir,
			serverSearchQuery,
			refreshToken,
		}
		isFetching = true
		error = null
		const q = request.serverSearchQuery || undefined
		try {
			const [
				agentsData,
				agentsCount,
				modelsData,
				providersData,
				toolPluginsData,
				filterPluginsData,
				hookPluginsData,
			] = await Promise.all([
				api
					.GET('/v1/agents', {
						params: {
							query: {
								skip: request.pageIndex * request.limit,
								limit: request.limit,
								sort_by: request.sortKey,
								sort_dir: request.sortDir,
								q,
							},
						},
					})
					.then((r) => unwrap(r)),
				api.GET('/v1/agents/count', { params: { query: { q } } }).then((r) => unwrap(r)),
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
					.GET('/v1/plugins/available', {
						params: { query: { plugin_type: 'hook' } },
					})
					.then((r) => unwrap(r)),
			])
			if (request.id !== fetchRequestId) return
			agents = agentsData
			agentTotal = agentsCount
			hasNext = (request.pageIndex + 1) * request.limit < agentsCount
			models = modelsData
			providers = providersData
			availableToolPlugins = toolPluginsData
			availableFilterPlugins = filterPluginsData
			availableHookPlugins = hookPluginsData
		} catch (e) {
			if (request.id !== fetchRequestId) return
			console.error('failed to load agents/models/plugins', e)
			error = 'failed to load agents'
		} finally {
			if (request.id === fetchRequestId) isFetching = false
		}
	}

	$effect(() => {
		void fetchData()
	})

	function openCreateModal() {
		modalMode = 'create'
		editingId = null
		formName = ''
		formDescription = ''
		formSystemPrompt = ''
		formModelId = ''
		formPluginIds = [...defaultAgentPluginIds]
		formProfileImageValue = ''
		configParams = {}
		formSteeringEnabled = true
		originalFeatures = {}
		submitError = null
		activeSection = 'overview'
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
		formProfileImageValue = agent.profile_image_file_id ?? agent.profile_image_url ?? ''
		const agentConfig = (agent.config ?? {}) as Record<string, unknown>
		const agentModel = models.find((m) => m.id === agent.model_id)
		const mt = agentModel?.model_type ?? 'chat_model'
		configParams = (agentConfig[mt] ?? {}) as Record<string, unknown>
		const features = (agentConfig.features ?? {}) as Record<string, unknown> & {
			steering?: { enabled?: boolean }
		}
		formSteeringEnabled = features.steering?.enabled ?? true
		originalFeatures = { ...features }
		submitError = null
		activeSection = 'overview'
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
			formProfileImageValue = typeof reader.result === 'string' ? reader.result : ''
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
			console.error('failed to delete agent', err)
			submitError = err instanceof Error ? err.message : 'failed to delete agent'
		} finally {
			isLoading = false
		}
	}

	function buildConfigPayload(): Record<string, unknown> {
		const config: Record<string, unknown> = {}
		if (selectedModelType && Object.keys(configParams).length > 0) {
			config[selectedModelType] = configParams
		}
		// merge over originalFeatures so unknown/future feature keys round-trip
		// untouched while we only update the knobs the UI exposes.
		config.features = {
			...originalFeatures,
			steering: { enabled: formSteeringEnabled },
		}
		return config
	}

	async function handleSubmit(e: Event) {
		e.preventDefault()
		isLoading = true
		submitError = null

		try {
			const normalizedProfileImage = formProfileImageValue.trim()
			const profileImageKind = profileImageInputKind(normalizedProfileImage)
			const profile_image_file_id =
				profileImageKind === 'file' ? normalizedProfileImage : null
			const profile_image_url = profileImageKind === 'url' ? normalizedProfileImage : null

			if (modalMode === 'create') {
				const config = buildConfigPayload()
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
				const config = buildConfigPayload()
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
				modalMode === 'create' ? 'failed to create agent' : 'failed to save agent',
				err
			)
			submitError = formatSubmitError(err)
		} finally {
			isLoading = false
		}
	}
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">agents</h2>
			<p class="text-zinc-400">create and manage agents.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search agents..."
					bind:value={searchQuery}
					oninput={scheduleSearch}
					class="w-full pl-8 sm:w-50 lg:w-75"
				/>
			</div>
			<div class="flex w-full items-center gap-2 sm:w-auto">
				<Select value={sortKey} onValueChange={(v: string) => setSort(v as SortKey)}>
					<SelectTrigger class="w-full flex-1 rounded-xl sm:w-40">
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
					class="shrink-0 rounded-xl px-3"
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
			</div>
			<div class="flex w-full items-center gap-2 sm:w-auto">
				<Button onclick={openCreateModal} class="flex-1 gap-2 rounded-xl sm:flex-none">
					<Plus class="h-4 w-4" />
					add agent
				</Button>
				<Button
					variant="outline"
					class="flex-1 rounded-xl sm:flex-none"
					onclick={() => (refreshToken += 1)}
					disabled={isFetching}
				>
					<RefreshCw class="mr-2 h-4 w-4 {isFetching ? 'animate-spin' : ''}" />
					{isFetching ? 'loading...' : 'refresh'}
				</Button>
			</div>
		</div>
	</div>

	<div class="flex flex-col gap-6">
		{#if isFetching}
			<div class="flex flex-col items-center justify-center gap-4 py-16">
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
			<div class="flex items-center justify-end">
				<div class="flex items-center gap-2">
					<Button
						variant="outline"
						class="rounded-xl"
						onclick={() => {
							pageIndex = Math.max(0, pageIndex - 1)
						}}
						disabled={pageIndex === 0 || isFetching}
					>
						<ChevronLeft class="mr-1.5 h-4 w-4" />
						prev
					</Button>
					<span class="text-xs text-zinc-400 tabular-nums">
						page {pageIndex + 1}{agentTotal > 0
							? ` · ${agents.length} of ${agentTotal}`
							: ''}
					</span>
					<Button
						variant="outline"
						class="rounded-xl"
						onclick={() => {
							pageIndex += 1
						}}
						disabled={!hasNext || isFetching}
					>
						next
						<ChevronRight class="ml-1.5 h-4 w-4" />
					</Button>
				</div>
			</div>
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each visibleAgents as agent (agent.id)}
					<Card
						class="flex shrink-0 flex-col overflow-hidden rounded-2xl border-zinc-800 bg-zinc-900 transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
					>
						<CardHeader class="border-b border-zinc-800/50 px-4 py-4">
							<div class="flex items-start justify-between gap-4">
								<div class="flex min-w-0 flex-1 items-start gap-3">
									<div
										class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400"
									>
										<Bot class="h-4 w-4" />
									</div>
									<div class="min-w-0 flex-1">
										<CardTitle class="truncate text-base"
											>{agent.name}</CardTitle
										>
										{#if agent.description}
											<CardDescription class="mt-1 line-clamp-2 text-xs">
												{agent.description}
											</CardDescription>
										{/if}
									</div>
								</div>
								<div class="flex shrink-0 gap-1">
									<AccessRulesButton
										variant="ghost"
										size="icon"
										class="h-7 w-7 text-zinc-500 hover:text-zinc-300"
										onclick={() => openAclModal(agent.id)}
									/>
									<Button
										variant="ghost"
										size="icon"
										class="h-7 w-7 text-zinc-500 hover:text-zinc-300"
										onclick={() => openEditModal(agent)}
										title="edit agent"
									>
										<Pencil class="h-3.5 w-3.5" />
									</Button>
								</div>
							</div>
						</CardHeader>
						<CardContent class="flex flex-1 flex-col justify-end px-4 py-4">
							<div class="flex flex-col gap-2 text-xs text-zinc-500">
								<div class="flex items-center justify-between gap-2">
									<span class="shrink-0 font-medium text-zinc-600">model</span>
									<span class="truncate font-medium text-zinc-300">
										{getModelLabel(agent.model_id)}
									</span>
								</div>
								{#if agent.plugin_ids && agent.plugin_ids.length > 0}
									<div class="flex items-center justify-between gap-2">
										<span class="shrink-0 font-medium text-zinc-600"
											>plugins</span
										>
										<span
											class="inline-flex items-center rounded-md bg-zinc-800/50 px-2 py-0.5 font-medium text-zinc-300"
										>
											{agent.plugin_ids.length}
										</span>
									</div>
								{/if}
							</div>
						</CardContent>
					</Card>
				{/each}

				{#if agents.length === 0 && serverSearchQuery}
					<div
						class="col-span-full rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no agents match your search
					</div>
				{/if}

				{#if agents.length === 0 && !serverSearchQuery}
					<EmptyState message="no agents yet." hint="create an agent to get started." />
				{/if}
			</div>
		{/if}
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
			class="fixed top-1/2 left-1/2 z-50 flex h-[min(760px,calc(100vh-2rem))] w-[min(960px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">
						{modalMode === 'create' ? 'create agent' : 'edit agent'}
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
						aria-label="agent sections"
					>
						{#each sections as s (s.value)}
							<button
								type="button"
								onclick={() => (activeSection = s.value)}
								class="shrink-0 rounded-lg px-3 py-1.5 text-left text-sm transition-colors {activeSection ===
								s.value
									? 'bg-zinc-800 text-zinc-100'
									: 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'}"
								aria-current={activeSection === s.value ? 'page' : undefined}
							>
								{s.label}
							</button>
						{/each}
					</nav>

					<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
						{#if activeSection === 'overview'}
							{#if modalMode === 'edit' && editingId}
								<div class="space-y-1">
									<Label class="text-xs text-zinc-500">id</Label>
									<p class="font-mono text-xs text-zinc-400 select-all">
										{editingId}
									</p>
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
								<Label for="profile_image">profile image (optional)</Label>
								<div class="flex flex-col gap-2 sm:flex-row">
									<Input
										id="profile_image"
										bind:value={formProfileImageValue}
										placeholder="https://..., data:image..., or file id"
										class="min-w-0 rounded-xl"
									/>
									<input
										id="profile_image_upload"
										type="file"
										accept="image/svg+xml,.svg"
										onchange={handleSvgFileChange}
										class="sr-only"
									/>
									<Label
										for="profile_image_upload"
										class="inline-flex h-10 shrink-0 cursor-pointer items-center justify-center rounded-xl border border-zinc-800 px-3 text-sm text-zinc-300 hover:bg-zinc-900"
									>
										upload svg
									</Label>
								</div>
								<p class="text-xs text-zinc-500">
									current mode: {profileImageModeLabel(formProfileImageValue)}.
								</p>
							</div>

							{#if profileImagePreviewSrc}
								<div
									class="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-950/40 p-3"
								>
									<img
										src={profileImagePreviewSrc}
										alt="agent profile preview"
										class="h-10 w-10 rounded-lg bg-zinc-800 object-contain"
									/>
									<div class="text-xs text-zinc-500">preview</div>
								</div>
							{/if}
						{:else if activeSection === 'model'}
							<div class="space-y-2">
								<Label for="model">model (optional)</Label>
								<SearchableModelPicker
									items={chatModels.map((m) => ({
										value: m.id,
										label: m.display_name || m.name || m.id,
										sublabel: modelFullLabel(m).replace(
											`${m.display_name || m.name || m.id} · `,
											''
										),
									}))}
									value={formModelId}
									placeholder="none"
									searchPlaceholder="search models..."
									allowClear={true}
									clearLabel="none"
									emptyLabel="no models match your search"
									onChange={(v) => (formModelId = v)}
								/>
							</div>

							{#if selectedModelType}
								<div class="border-t border-zinc-800 pt-4">
									<ModelParamsEditor
										modelType={selectedModelType}
										bind:params={configParams}
									/>
								</div>
							{:else}
								<p class="text-xs text-zinc-500">
									select a model to configure parameters.
								</p>
							{/if}
						{:else if activeSection === 'prompt'}
							<div class="space-y-2">
								<div class="flex items-center justify-between">
									<Label for="system_prompt">system prompt (optional)</Label>
									<div class="flex items-center gap-1">
										<Button
											type="button"
											variant="ghost"
											size="sm"
											class="h-7 gap-1 text-xs text-zinc-400 hover:text-zinc-200"
											onclick={() =>
												(formSystemPrompt = TEMPLATE_SYSTEM_PROMPT)}
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
									rows={14}
									placeholder="you are ..."
									class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm"
								></textarea>
							</div>
						{:else if activeSection === 'plugins'}
							{#each pluginGroups as group (group.label)}
								<section class="space-y-3">
									<header class="space-y-1">
										<h3 class="text-xs font-semibold text-zinc-500">
											{group.label}
										</h3>
										<p class="text-xs text-zinc-500">{group.description}</p>
									</header>
									<div class="grid gap-3 lg:grid-cols-2">
										{#each group.plugins as plugin (plugin.id)}
											{@const iconKind = pluginIconKind(plugin)}
											<div
												class="rounded-xl border p-4 transition-colors {formPluginIds.includes(
													plugin.id
												)
													? 'border-violet-500/50 bg-violet-500/10'
													: 'border-zinc-800 bg-zinc-950/40'}"
											>
												<div class="flex items-start justify-between gap-3">
													<div class="flex min-w-0 gap-3">
														<div
															class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-zinc-900 text-zinc-300"
														>
															{#if iconKind === 'memory'}
																<Brain class="h-4 w-4" />
															{:else if iconKind === 'note'}
																<FileText class="h-4 w-4" />
															{:else if iconKind === 'reminder'}
																<Bell class="h-4 w-4" />
															{:else if iconKind === 'calendar'}
																<CalendarDays class="h-4 w-4" />
															{:else if iconKind === 'file'}
																<FolderOpen class="h-4 w-4" />
															{:else if iconKind === 'web'}
																<Earth class="h-4 w-4" />
															{:else if iconKind === 'search'}
																<Search class="h-4 w-4" />
															{:else if iconKind === 'image'}
																<ImageIcon class="h-4 w-4" />
															{:else if iconKind === 'code'}
																<CodeXml class="h-4 w-4" />
															{:else if iconKind === 'reveal'}
																<Eye class="h-4 w-4" />
															{:else if iconKind === 'attachment'}
																<Paperclip class="h-4 w-4" />
															{:else if iconKind === 'notification'}
																<Bell class="h-4 w-4" />
															{:else if iconKind === 'think'}
																<Brain class="h-4 w-4" />
															{:else if iconKind === 'chat'}
																<MessageSquare class="h-4 w-4" />
															{:else if iconKind === 'time'}
																<CalendarDays class="h-4 w-4" />
															{:else if iconKind === 'filter'}
																<FilterIcon class="h-4 w-4" />
															{:else if iconKind === 'hook'}
																<Sparkles class="h-4 w-4" />
															{:else}
																<Wrench class="h-4 w-4" />
															{/if}
														</div>
														<div class="min-w-0 space-y-1">
															<div
																class="flex flex-wrap items-center gap-2"
															>
																<div
																	class="text-sm font-medium wrap-anywhere text-zinc-100"
																>
																	{pluginDisplayName(plugin)}
																</div>
																{#if plugin.is_native}
																	<span
																		class="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-400"
																	>
																		native
																	</span>
																{/if}
																{#if isDefaultAgentPlugin(plugin.id)}
																	<span
																		class="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-300"
																	>
																		default
																	</span>
																{/if}
															</div>
															<p
																class="text-xs leading-5 wrap-anywhere text-zinc-500"
															>
																{pluginDescription(plugin)}
															</p>
														</div>
													</div>
													<Switch
														checked={formPluginIds.includes(plugin.id)}
														onCheckedChange={() =>
															togglePlugin(plugin.id)}
													/>
												</div>
											</div>
										{/each}
									</div>
								</section>
							{/each}

							{#if pluginGroups.length === 0}
								<p class="text-xs text-zinc-500">no plugins are registered.</p>
							{/if}
						{:else if activeSection === 'config'}
							<section class="space-y-3">
								<header class="space-y-1">
									<h3 class="text-xs font-semibold text-zinc-500">features</h3>
									<p class="text-xs text-zinc-500">
										toggle high-level capabilities for this agent.
									</p>
								</header>
								<div class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
									<div class="flex items-start justify-between gap-4">
										<div class="space-y-1">
											<Label for="steering-toggle">steering</Label>
											<p class="text-xs text-zinc-500">
												allow users to interrupt and steer this agent
												mid-run via the chat input. when off, the agent runs
												to completion without interruption.
											</p>
										</div>
										<Switch
											id="steering-toggle"
											bind:checked={formSteeringEnabled}
										/>
									</div>
								</div>
							</section>
						{/if}
					</div>
				</div>

				<div
					class="flex shrink-0 flex-col gap-3 border-t border-zinc-800 px-6 py-4 sm:flex-row sm:items-center sm:justify-between"
				>
					<div class="flex flex-col gap-2 sm:flex-row">
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
							<AccessRulesButton
								type="button"
								disabled={isLoading}
								onclick={() => {
									showModal = false
									openAclModal(editingId!)
								}}
							/>
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

<AclModal
	bind:open={showAclModal}
	resourceType="agent"
	resourceId={aclAgentId}
	title="agent access rules"
/>

<PromptVariablesLegend bind:open={showVariablesLegend} />
