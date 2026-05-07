<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type Model = Schemas['Model']
	type ModelCreate = Schemas['ModelCreate']
	type ModelUpdate = Schemas['ModelUpdate']
	type Provider = Schemas['Provider']

	import EmptyState from '$lib/components/EmptyState.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'
	import {
		ArrowDown,
		ArrowUp,
		Cpu,
		Pencil,
		Plus,
		RefreshCw,
		Search,
		Trash2,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'
	import { onMount } from 'svelte'

	type ModelCreateForm = ModelCreate & { adapter?: string | null }

	type ModelSortKey = 'name' | 'model_type' | 'provider' | 'enabled'
	type SortDir = 'asc' | 'desc'

	const modelSortOptions: Array<{ value: ModelSortKey; label: string }> = [
		{ value: 'name', label: 'name' },
		{ value: 'model_type', label: 'type' },
		{ value: 'provider', label: 'provider' },
		{ value: 'enabled', label: 'enabled' },
	]

	let modelSortKey = $state<ModelSortKey>('name')
	let modelSortDir = $state<SortDir>('asc')

	const ALL_MODALITIES = ['text', 'images', 'audio', 'video'] as const
	type InputModality = (typeof ALL_MODALITIES)[number]

	const DEFAULT_MODALITIES: Record<string, InputModality[]> = {
		chat_model: ['text', 'images'],
		embedding: ['text'],
		image: ['text', 'images'],
		audio: ['text', 'audio'],
		video: ['text', 'images', 'video'],
	}

	let models = $state<Model[]>([])
	let providers = $state<Provider[]>([])
	let showModal = $state(false)
	let modalMode = $state<'create' | 'edit'>('create')
	let isLoading = $state(false)
	let isFetching = $state(true)
	let editingId = $state<string | null>(null)
	let error = $state<string | null>(null)
	let submitError = $state<string | null>(null)
	let searchQuery = $state('')
	let inputModalities = $state<InputModality[]>(['text', 'images'])

	const hasProviders = $derived(providers.length > 0)
	const addModelDisabledReason = 'add a provider to enable model creation.'
	const emptyStateNoProvidersMessage = 'no providers configured yet.'
	const emptyStateNoProvidersHint = 'add a provider first to create models.'
	const emptyStateNoModelsMessage = 'no models configured yet.'

	const filteredModels = $derived.by(() => {
		let result = models.filter((m) => {
			const q = searchQuery.toLowerCase()
			return (
				m.name.toLowerCase().includes(q) ||
				(m.display_name && m.display_name.toLowerCase().includes(q)) ||
				m.id.toLowerCase().includes(q)
			)
		})
		const dir = modelSortDir === 'asc' ? 1 : -1
		return [...result].sort((a, b) => {
			switch (modelSortKey) {
				case 'name':
					return (a.display_name || a.name).localeCompare(b.display_name || b.name) * dir
				case 'model_type':
					return a.model_type.localeCompare(b.model_type) * dir
				case 'provider':
					return (
						getProviderName(a.provider_id).localeCompare(
							getProviderName(b.provider_id)
						) * dir
					)
				case 'enabled':
					return (Number(a.enabled) - Number(b.enabled)) * dir
				default:
					return 0
			}
		})
	})

	function setModelSort(next: ModelSortKey) {
		if (modelSortKey === next) {
			modelSortDir = modelSortDir === 'asc' ? 'desc' : 'asc'
		} else {
			modelSortKey = next
			modelSortDir = 'asc'
		}
	}

	function toggleModelSortDir() {
		modelSortDir = modelSortDir === 'asc' ? 'desc' : 'asc'
	}

	// Form state
	let formState = $state<ModelCreateForm>({
		name: '',
		display_name: '',
		model_type: 'chat_model',
		adapter: null,
		provider_id: '',
		enabled: true,
		is_autofetched: false,
	})

	// Optional numeric fields are modeled as strings so they can be blank.
	let contextWindowInput = $state<string>('')
	let inputCostInput = $state<string>('')
	let outputCostInput = $state<string>('')

	let providerKey = $derived(formState.provider_id ? getProviderKey(formState.provider_id) : null)
	let adapterOptions = $derived(getAdapterOptions(providerKey, formState.model_type))

	// types supported per provider (based on available adapters)
	const PROVIDER_MODEL_TYPES: Partial<Record<string, Model['model_type'][]>> = {
		openai: ['chat_model', 'embedding', 'image'],
		anthropic: ['chat_model'],
		google: ['chat_model', 'image'],
		ollama: ['chat_model', 'embedding'],
	}
	const ALL_MODEL_TYPES: Model['model_type'][] = [
		'chat_model',
		'embedding',
		'image',
		'audio',
		'video',
	]
	let availableModelTypes = $derived(
		providerKey && PROVIDER_MODEL_TYPES[providerKey]
			? (PROVIDER_MODEL_TYPES[providerKey] as Model['model_type'][])
			: ALL_MODEL_TYPES
	)

	$effect(() => {
		if (showModal) {
			// reset model type if not available for current provider
			if (!availableModelTypes.includes(formState.model_type)) {
				formState.model_type = availableModelTypes[0] ?? 'chat_model'
			}
		}
	})

	$effect(() => {
		if (showModal) {
			// auto-select adapter; when current adapter is invalid for the new type, pick first
			const currentValid =
				formState.adapter && adapterOptions.find((o) => o.value === formState.adapter)
			if (!currentValid && adapterOptions.length > 0) {
				formState.adapter = adapterOptions[0].value
			} else if (adapterOptions.length === 0) {
				formState.adapter = null
			}
		}
	})

	// update default modalities when model type changes during creation
	$effect(() => {
		if (showModal && modalMode === 'create') {
			const defaults = DEFAULT_MODALITIES[formState.model_type]
			if (defaults) {
				inputModalities = [...defaults]
			}
		}
	})

	async function fetchData() {
		isFetching = true
		try {
			const [modelsData, providersData] = await Promise.all([
				api.GET('/v1/models').then((r) => unwrap(r)),
				api.GET('/v1/providers').then((r) => unwrap(r)),
			])
			models = modelsData
			providers = providersData
		} catch (e) {
			console.error('Failed to fetch data', e)
			error = 'Failed to load models'
		} finally {
			isFetching = false
		}
	}

	onMount(() => {
		fetchData()
	})

	function openCreateModal() {
		if (!hasProviders) return
		modalMode = 'create'
		formState = {
			name: '',
			display_name: '',
			model_type: 'chat_model',
			adapter: null,
			provider_id: providers.length > 0 ? providers[0].id : '',
			enabled: true,
			is_autofetched: false,
		}
		contextWindowInput = ''
		inputCostInput = ''
		outputCostInput = ''
		inputModalities = [...(DEFAULT_MODALITIES['chat_model'] ?? ['text'])]
		showModal = true
		submitError = null
	}

	function openEditModal(model: Model) {
		modalMode = 'edit'
		editingId = model.id
		const adapter = model.adapter ?? null
		formState = {
			name: model.name,
			display_name: model.display_name || '',
			model_type: model.model_type,
			adapter,
			provider_id: model.provider_id,
			enabled: model.enabled,
			is_autofetched: model.is_autofetched,
		}
		contextWindowInput =
			model.context_window === null || model.context_window === undefined
				? ''
				: String(model.context_window)
		inputCostInput =
			model.input_cost === null || model.input_cost === undefined
				? ''
				: String(model.input_cost)
		outputCostInput =
			model.output_cost === null || model.output_cost === undefined
				? ''
				: String(model.output_cost)
		inputModalities = [
			...(model.input_modalities ?? DEFAULT_MODALITIES[model.model_type] ?? ['text']),
		]
		showModal = true
		submitError = null
	}

	function parseOptionalNumber(value: string): number | null {
		const trimmed = value.trim()
		if (!trimmed) return null
		const parsed = Number(trimmed)
		return Number.isFinite(parsed) ? parsed : null
	}

	async function handleSubmit(e: Event) {
		e.preventDefault()
		isLoading = true
		submitError = null

		if (modalMode === 'create' && !formState.provider_id) {
			submitError = 'a provider is required to create a model.'
			isLoading = false
			return
		}

		try {
			if (modalMode === 'create') {
				const createPayload: ModelCreate = {
					name: formState.name.trim(),
					display_name: formState.display_name?.trim() || null,
					model_type: formState.model_type,
					adapter: formState.adapter ?? null,
					provider_id: formState.provider_id,
					enabled: formState.enabled,
					is_autofetched: formState.is_autofetched,
					input_modalities: inputModalities,
				}
				const contextWindow = parseOptionalNumber(contextWindowInput)
				const inputCost = parseOptionalNumber(inputCostInput)
				const outputCost = parseOptionalNumber(outputCostInput)
				if (contextWindow !== null) createPayload.context_window = contextWindow
				if (inputCost !== null) createPayload.input_cost = inputCost
				if (outputCost !== null) createPayload.output_cost = outputCost
				unwrap(await api.POST('/v1/models', { body: createPayload }))
			} else if (editingId) {
				const updatePayload: ModelUpdate = {
					name: formState.name.trim(),
					display_name: formState.display_name?.trim() || null,
					model_type: formState.model_type,
					adapter: formState.adapter ?? null,
					enabled: formState.enabled,
					is_autofetched: formState.is_autofetched,
					input_modalities: inputModalities,
					context_window: parseOptionalNumber(contextWindowInput),
					input_cost: parseOptionalNumber(inputCostInput),
					output_cost: parseOptionalNumber(outputCostInput),
				}
				unwrap(
					await api.PATCH('/v1/models/{model_id}', {
						params: { path: { model_id: editingId } },
						body: updatePayload,
					})
				)
			}
			showModal = false
			await fetchData()
		} catch (e: unknown) {
			console.error('Failed to save model', e)
			submitError = e instanceof Error ? e.message : String(e)
		} finally {
			isLoading = false
		}
	}

	async function handleDeleteFromModal() {
		if (!editingId) return
		if (!confirm('Are you sure you want to delete this model?')) return
		isLoading = true
		try {
			unwrap(
				await api.DELETE('/v1/models/{model_id}', {
					params: { path: { model_id: editingId } },
				})
			)
			showModal = false
			await fetchData()
		} catch (e) {
			console.error('Failed to delete model', e)
			submitError = 'Failed to delete model'
		} finally {
			isLoading = false
		}
	}

	async function handleDelete(id: string) {
		if (!confirm('Are you sure you want to delete this model?')) return
		try {
			unwrap(
				await api.DELETE('/v1/models/{model_id}', { params: { path: { model_id: id } } })
			)
			await fetchData()
		} catch (e) {
			console.error('Failed to delete model', e)
			alert('Failed to delete model')
		}
	}

	function getProviderName(id: string) {
		const p = providers.find((p) => p.id === id)
		return p ? p.name : id
	}

	function getProviderKey(providerId: string): string | null {
		const p = providers.find((p) => p.id === providerId)
		if (!p) return null
		const raw = p.adapter_type || ''
		const key = raw.split('.', 1)[0].trim()
		return key || null
	}

	function getModelTypeLabel(modelType: Model['model_type']) {
		switch (modelType) {
			case 'chat_model':
				return 'chat model'
			case 'image':
				return 'image'
			case 'embedding':
				return 'embedding'
			case 'audio':
				return 'audio'
			case 'video':
				return 'video'
			default:
				return modelType
		}
	}

	function getAdapterOptions(providerKey: string | null, modelType: Model['model_type']) {
		if (!providerKey) return []
		if (modelType === 'chat_model') {
			if (providerKey === 'openai') {
				return [
					{ value: 'chat_completions', label: 'chat completions' },
					{ value: 'responses', label: 'responses api' },
				]
			}
			if (providerKey === 'google') {
				return [{ value: 'generate_content', label: 'generate content' }]
			}
			if (providerKey === 'anthropic') {
				return [{ value: 'messages', label: 'messages' }]
			}
			if (providerKey === 'ollama') {
				return [{ value: 'chat', label: 'chat' }]
			}
		}
		if (modelType === 'embedding') {
			if (providerKey === 'openai' || providerKey === 'ollama') {
				return [{ value: 'embedding', label: 'embedding' }]
			}
		}
		if (modelType === 'image') {
			if (providerKey === 'openai') {
				return [{ value: 'images', label: 'openai images (dall-e / gpt-image)' }]
			}
			if (providerKey === 'google') {
				return [
					{ value: 'predict_images', label: 'imagen (predict api)' },
					{
						value: 'generate_content_images',
						label: 'gemini (generate content)',
					},
				]
			}
		}
		return []
	}

	function toggleModality(modality: InputModality) {
		if (inputModalities.includes(modality)) {
			inputModalities = inputModalities.filter((m) => m !== modality)
		} else {
			inputModalities = [...inputModalities, modality]
		}
	}
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">models</h2>
			<p class="text-zinc-400">manage your AI models.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="relative w-full sm:w-auto sm:flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
				/>
				<Input
					type="search"
					placeholder="search models..."
					bind:value={searchQuery}
					class="w-full pl-8 sm:w-50 lg:w-75"
				/>
			</div>
			<div class="flex w-full items-center gap-2 sm:w-auto">
				<Select
					value={modelSortKey}
					onValueChange={(v: string) => setModelSort(v as ModelSortKey)}
				>
					<SelectTrigger class="w-full flex-1 rounded-xl sm:w-40">
						<span class="truncate text-left">
							{modelSortOptions.find((o) => o.value === modelSortKey)?.label ??
								modelSortKey}
						</span>
					</SelectTrigger>
					<SelectContent>
						{#each modelSortOptions as opt (opt.value)}
							<SelectItem value={opt.value}>{opt.label}</SelectItem>
						{/each}
					</SelectContent>
				</Select>
				<Button
					variant="outline"
					class="shrink-0 rounded-xl px-3"
					onclick={() => toggleModelSortDir()}
					disabled={isFetching}
					title="toggle sort direction"
					aria-label="toggle sort direction"
				>
					{#if modelSortDir === 'asc'}
						<ArrowUp class="h-4 w-4" />
					{:else}
						<ArrowDown class="h-4 w-4" />
					{/if}
				</Button>
			</div>
			<div class="flex w-full items-center gap-2 sm:w-auto">
				{#if hasProviders}
					<Button onclick={openCreateModal} class="flex-1 gap-2 rounded-xl sm:flex-none">
						<Plus class="h-4 w-4" />
						add model
					</Button>
				{:else}
					<span title={addModelDisabledReason} class="flex-1 sm:flex-none">
						<Button onclick={openCreateModal} disabled class="w-full gap-2 rounded-xl">
							<Plus class="h-4 w-4" />
							add model
						</Button>
					</span>
				{/if}
				<Button
					variant="outline"
					class="flex-1 rounded-xl sm:flex-none"
					onclick={() => fetchData()}
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
			<div class="flex flex-col items-center justify-center py-16">
				<NokodoLoader />
			</div>
		{:else if error}
			<div class="rounded-md bg-red-500/10 p-4 text-red-500">
				{error}
			</div>
		{:else}
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each filteredModels as model (model.id)}
					<Card
						class="flex shrink-0 flex-col overflow-hidden rounded-2xl border-zinc-800 bg-zinc-900 transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
					>
						<CardHeader class="border-b border-zinc-800/50 px-4 py-4">
							<div class="flex items-start justify-between gap-4">
								<div class="flex min-w-0 flex-1 items-start gap-3">
									<div
										class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-pink-500/10 text-pink-400"
									>
										<Cpu class="h-4 w-4" />
									</div>
									<div class="min-w-0 flex-1">
										<CardTitle class="truncate text-base"
											>{model.display_name || model.name}</CardTitle
										>
										<div
											class="mt-1 flex items-center gap-1.5 text-xs text-zinc-400"
										>
											<span class="truncate"
												>{getProviderName(model.provider_id)}</span
											>
											<span>•</span>
											<span class="truncate"
												>{getModelTypeLabel(model.model_type)}</span
											>
										</div>
									</div>
								</div>
								<div class="flex shrink-0 gap-1">
									<Button
										variant="ghost"
										size="icon"
										class="h-7 w-7 text-zinc-500 hover:text-zinc-300"
										onclick={() => openEditModal(model)}
									>
										<Pencil class="h-3.5 w-3.5" />
									</Button>
									<Button
										variant="ghost"
										size="icon"
										class="h-7 w-7 text-zinc-500 hover:text-red-400"
										onclick={() => handleDelete(model.id)}
									>
										<Trash2 class="h-3.5 w-3.5" />
									</Button>
								</div>
							</div>
						</CardHeader>
						<CardContent class="flex flex-1 flex-col justify-end px-4 py-4">
							<div class="flex items-center justify-between gap-2">
								<div class="flex items-center gap-2">
									<div
										class={`h-2 w-2 rounded-full ${model.enabled ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]'}`}
									></div>
									<span
										class="text-xs font-medium tracking-wider text-zinc-400 uppercase"
									>
										{model.enabled ? 'enabled' : 'disabled'}
									</span>
								</div>
								{#if model.is_autofetched}
									<span
										class="inline-flex items-center rounded-md bg-zinc-800/50 px-2 py-0.5 text-[10px] font-medium tracking-wider text-zinc-300 uppercase"
									>
										autofetched
									</span>
								{/if}
							</div>
						</CardContent>
					</Card>
				{/each}

				{#if models.length === 0}
					{#if !hasProviders}
						<EmptyState
							message={emptyStateNoProvidersMessage}
							hint={emptyStateNoProvidersHint}
						/>
					{:else}
						<EmptyState message={emptyStateNoModelsMessage} />
					{/if}
				{/if}
			</div>
		{/if}
	</div>
</div>

<Dialog.Root
	bind:open={showModal}
	onOpenChange={(open) => {
		if (!open) showModal = false
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
					<Dialog.Title class="text-lg font-semibold"
						>{modalMode === 'create' ? 'add model' : 'edit model'}</Dialog.Title
					>
					<p class="text-sm text-zinc-400">configure model details</p>
				</div>
				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8 rounded-lg"
					onclick={() => (showModal = false)}
				>
					<X class="h-4 w-4" />
				</Button>
			</div>
			<form onsubmit={handleSubmit} class="flex min-h-0 flex-1 flex-col">
				<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
					{#if submitError}
						<div class="rounded-md bg-red-500/10 p-3 text-sm text-red-500">
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
						<Label for="provider">provider</Label>
						<Select
							value={formState.provider_id}
							onValueChange={(value: string) => (formState.provider_id = value)}
						>
							<SelectTrigger class="rounded-xl">
								<span class="truncate text-left">
									{formState.provider_id
										? getProviderName(formState.provider_id)
										: 'select provider'}
								</span>
							</SelectTrigger>
							<SelectContent>
								{#each providers as provider (provider.id)}
									<SelectItem value={provider.id}>{provider.name}</SelectItem>
								{/each}
							</SelectContent>
						</Select>
					</div>

					<div class="space-y-2">
						<Label for="name">model name (id)</Label>
						<Input
							id="name"
							placeholder="gpt-4-turbo"
							bind:value={formState.name}
							disabled={modalMode === 'edit' && formState.is_autofetched}
							class="rounded-xl"
						/>
						<p class="text-xs text-zinc-500">
							the exact model identifier used by the provider API.
						</p>
					</div>

					<div class="space-y-2">
						<Label for="display_name">display name</Label>
						<Input
							id="display_name"
							placeholder="GPT-4 Turbo"
							bind:value={formState.display_name}
							class="rounded-xl"
						/>
					</div>

					<div class="space-y-2">
						<Label for="type">type</Label>
						<Select
							value={formState.model_type}
							onValueChange={(value: Model['model_type']) =>
								(formState.model_type = value)}
						>
							<SelectTrigger class="rounded-xl">
								<span class="truncate text-left">
									{getModelTypeLabel(formState.model_type)}
								</span>
							</SelectTrigger>
							<SelectContent>
								{#each ALL_MODEL_TYPES.filter( (t) => availableModelTypes.includes(t) ) as typeOpt (typeOpt)}
									<SelectItem value={typeOpt}
										>{getModelTypeLabel(typeOpt)}</SelectItem
									>
								{/each}
							</SelectContent>
						</Select>
					</div>

					{#if true}
						{@const providerKey = getProviderKey(formState.provider_id)}
						{@const adapterOptions = getAdapterOptions(
							providerKey,
							formState.model_type
						)}
						<div class="space-y-2">
							<Label for="adapter">adapter</Label>
							<Select
								value={formState.adapter ?? undefined}
								onValueChange={(value: string) => (formState.adapter = value)}
								disabled={!providerKey || adapterOptions.length === 0}
							>
								<SelectTrigger class="rounded-xl">
									<span class="truncate text-left">
										{formState.adapter || 'select adapter'}
									</span>
								</SelectTrigger>
								<SelectContent>
									{#each adapterOptions as opt (opt.value)}
										<SelectItem value={opt.value}>{opt.label}</SelectItem>
									{/each}
								</SelectContent>
							</Select>
							<p class="text-xs text-zinc-500">
								select which sdk adapter is used for this model.
							</p>
						</div>
					{/if}

					<div class="space-y-2">
						<Label>input modalities</Label>
						<p class="text-xs text-zinc-500">
							select which input types this model accepts.
						</p>
						<div class="grid grid-cols-2 gap-2">
							{#each ALL_MODALITIES as modality (modality)}
								<label
									class="flex cursor-pointer items-center gap-2 rounded-xl border border-zinc-800 px-3 py-2 transition-colors select-none hover:border-zinc-600"
									class:border-zinc-500={inputModalities.includes(modality)}
									class:bg-zinc-800={inputModalities.includes(modality)}
								>
									<input
										type="checkbox"
										checked={inputModalities.includes(modality)}
										onchange={() => toggleModality(modality)}
										class="h-4 w-4 rounded border-zinc-600 bg-zinc-900 accent-zinc-300"
									/>
									<span class="text-sm">{modality}</span>
								</label>
							{/each}
						</div>
					</div>

					<div class="grid gap-4 sm:grid-cols-2">
						<div class="space-y-2">
							<Label for="context">context window (optional)</Label>
							<Input
								id="context"
								type="number"
								placeholder="optional"
								bind:value={contextWindowInput}
								class="rounded-xl"
							/>
							<p class="text-xs text-zinc-500">optional</p>
						</div>
						<div class="space-y-2">
							<Label for="input_cost">input cost ($ / 1M tokens) (optional)</Label>
							<Input
								id="input_cost"
								type="number"
								step="0.0001"
								placeholder="optional"
								bind:value={inputCostInput}
								class="rounded-xl"
							/>
							<p class="text-xs text-zinc-500">optional</p>
						</div>
						<div class="space-y-2">
							<Label for="output_cost">output cost ($ / 1M tokens) (optional)</Label>
							<Input
								id="output_cost"
								type="number"
								step="0.0001"
								placeholder="optional"
								bind:value={outputCostInput}
								class="rounded-xl"
							/>
							<p class="text-xs text-zinc-500">optional</p>
						</div>
					</div>

					<div
						class="flex items-center justify-between rounded-xl border border-zinc-800 p-4"
					>
						<div class="space-y-0.5">
							<Label>enabled</Label>
							<div class="text-sm text-zinc-500">
								make this model available for use
							</div>
						</div>
						<Switch bind:checked={formState.enabled} />
					</div>
				</div>
				<div class="flex shrink-0 justify-between gap-2 border-t border-zinc-800 px-6 py-4">
					{#if modalMode === 'edit'}
						<Button
							type="button"
							variant="outline"
							class="gap-2 rounded-xl text-red-400 hover:text-red-300"
							disabled={isLoading}
							onclick={handleDeleteFromModal}
						>
							<Trash2 class="h-4 w-4" />
							delete
						</Button>
					{:else}
						<div></div>
					{/if}
					<div class="flex justify-end gap-2">
						<Button
							type="button"
							variant="outline"
							class="rounded-xl"
							onclick={() => (showModal = false)}
						>
							cancel
						</Button>
						<Button
							type="submit"
							disabled={isLoading ||
								(adapterOptions.length > 0 && !formState.adapter)}
							class="rounded-xl"
						>
							{isLoading
								? 'saving...'
								: modalMode === 'create'
									? 'add model'
									: 'save changes'}
						</Button>
					</div>
				</div>
			</form>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
