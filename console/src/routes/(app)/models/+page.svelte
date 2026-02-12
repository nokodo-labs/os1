<script lang="ts">
	import { resolve } from '$app/paths'
	import {
		api,
		unwrap,
		type Model,
		type ModelCreate,
		type ModelUpdate,
		type Provider,
	} from '$lib/api'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Switch } from '$lib/components/ui/switch'
	import { Pencil, Plus, Trash2, X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'
	import { onMount } from 'svelte'

	type ModelCreateForm = ModelCreate & { adapter?: string | null }

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

	const hasProviders = $derived(providers.length > 0)
	const addModelDisabledReason = 'add a provider to enable model creation.'
	const emptyStateNoProvidersMessage = 'no providers configured yet.'
	const emptyStateNoProvidersHint = 'add a provider first to create models.'
	const emptyStateNoModelsMessage = 'no models configured yet.'

	const filteredModels = $derived(
		models.filter((m) => {
			const q = searchQuery.toLowerCase()
			return (
				m.name.toLowerCase().includes(q) ||
				(m.display_name && m.display_name.toLowerCase().includes(q)) ||
				m.id.toLowerCase().includes(q)
			)
		})
	)

	// Form state
	let formState = $state<ModelCreateForm>({
		name: '',
		display_name: '',
		model_type: 'llm',
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

	$effect(() => {
		if (showModal && modalMode === 'create') {
			// Auto-select adapter if only one option exists, or clear it if current is invalid
			if (adapterOptions.length === 1) {
				formState.adapter = adapterOptions[0].value
			} else if (!formState.adapter && adapterOptions.length > 0 && modalMode === 'create') {
				formState.adapter = adapterOptions[0].value
			} else if (
				formState.adapter &&
				!adapterOptions.find((o) => o.value === formState.adapter)
			) {
				formState.adapter = null
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

	$effect(() => {
		if (showModal && modalMode === 'create') {
			// Auto-select adapter if only one option exists, or clear it if current is invalid
			if (adapterOptions.length === 1) {
				formState.adapter = adapterOptions[0].value
			} else if (!formState.adapter && adapterOptions.length > 0 && modalMode === 'create') {
				formState.adapter = adapterOptions[0].value
			} else if (
				formState.adapter &&
				!adapterOptions.find((o) => o.value === formState.adapter)
			) {
				formState.adapter = null
			}
		}
	})

	function openCreateModal() {
		if (!hasProviders) return
		modalMode = 'create'
		formState = {
			name: '',
			display_name: '',
			model_type: 'llm',
			adapter: null,
			provider_id: providers.length > 0 ? providers[0].id : '',
			enabled: true,
			is_autofetched: false,
		}
		contextWindowInput = ''
		inputCostInput = ''
		outputCostInput = ''
		showModal = true
		submitError = null
	}

	function openEditModal(model: Model) {
		modalMode = 'edit'
		editingId = model.id
		const adapter = (model as unknown as { adapter?: string | null }).adapter ?? null
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
				const createPayload = { ...formState } as unknown as ModelCreate
				const contextWindow = parseOptionalNumber(contextWindowInput)
				const inputCost = parseOptionalNumber(inputCostInput)
				const outputCost = parseOptionalNumber(outputCostInput)
				if (contextWindow !== null) createPayload.context_window = contextWindow
				if (inputCost !== null) createPayload.input_cost = inputCost
				if (outputCost !== null) createPayload.output_cost = outputCost
				unwrap(await api.POST('/v1/models', { body: createPayload }))
			} else if (editingId) {
				// Exclude provider_id from update
				const rest = Object.fromEntries(
					Object.entries(formState).filter(([k]) => k !== 'provider_id')
				)
				const updatePayload = {
					...(rest as unknown as Record<string, unknown>),
					context_window: parseOptionalNumber(contextWindowInput),
					input_cost: parseOptionalNumber(inputCostInput),
					output_cost: parseOptionalNumber(outputCostInput),
				} as unknown as ModelUpdate
				unwrap(
					await api.PATCH('/v1/models/{model_id}', {
						params: { path: { model_id: editingId } },
						body: updatePayload as unknown as ModelUpdate,
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
		if (modelType === 'llm') return 'chat model'
		return modelType
	}

	function getAdapterOptions(providerKey: string | null, modelType: Model['model_type']) {
		if (!providerKey) return []
		if (modelType === 'llm') {
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
		return []
	}
</script>

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">models</h2>
			<p class="text-zinc-400">manage your AI models.</p>
		</div>
		{#if hasProviders}
			<Button onclick={openCreateModal}>
				<Plus class="mr-2 h-4 w-4" />
				add model
			</Button>
		{:else}
			<div class="flex flex-col items-end gap-1">
				<span title={addModelDisabledReason}>
					<Button onclick={openCreateModal} disabled>
						<Plus class="mr-2 h-4 w-4" />
						add model
					</Button>
				</span>
				<a
					href={resolve('/providers')}
					class="text-xs text-zinc-500 underline underline-offset-4 hover:text-zinc-300"
				>
					{addModelDisabledReason}
				</a>
			</div>
		{/if}
	</div>

	<div class="flex w-full shrink-0 items-center space-x-2">
		<Input
			type="search"
			placeholder="search models..."
			bind:value={searchQuery}
			class="h-9 max-w-sm"
		/>
	</div>

	<div class="min-h-0 flex-1 overflow-y-auto">
		<div class="flex min-h-0 flex-1 flex-col gap-6">
			{#if isFetching}
				<div class="flex min-h-0 flex-1 items-center justify-center">
					<NokodoLoader />
				</div>
			{:else if error}
				<div class="rounded-md bg-red-500/10 p-4 text-red-500">
					{error}
				</div>
			{:else}
				<div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
					{#each filteredModels as model (model.id)}
						<Card class="border-zinc-800 bg-zinc-900 text-zinc-100">
							<CardHeader
								class="flex flex-row items-start justify-between space-y-0 pb-2"
							>
								<CardTitle class="text-base font-medium">
									{model.display_name || model.name}
								</CardTitle>
								<div class="flex gap-2">
									<Button
										variant="ghost"
										size="icon"
										class="h-8 w-8 text-zinc-400 hover:text-zinc-100"
										onclick={() => openEditModal(model)}
									>
										<Pencil class="h-4 w-4" />
									</Button>
									<Button
										variant="ghost"
										size="icon"
										class="h-8 w-8 text-zinc-400 hover:text-red-500"
										onclick={() => handleDelete(model.id)}
									>
										<Trash2 class="h-4 w-4" />
									</Button>
								</div>
							</CardHeader>
							<CardContent>
								<div class="mb-4 text-sm text-zinc-400">
									{getProviderName(model.provider_id)} • {getModelTypeLabel(
										model.model_type
									)}
								</div>
								<div class="flex items-center gap-2">
									<div
										class={`h-2 w-2 rounded-full ${
											model.enabled ? 'bg-green-500' : 'bg-zinc-700'
										}`}
									></div>
									<span class="text-xs text-zinc-500">
										{model.enabled ? 'enabled' : 'disabled'}
									</span>
									{#if model.is_autofetched}
										<span class="ml-2 text-xs text-blue-500">autofetched</span>
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
								<SelectItem value="llm">chat model</SelectItem>
								<SelectItem value="embedding">embedding</SelectItem>
								<SelectItem value="image_generation">image generation</SelectItem>
								<SelectItem value="audio">audio</SelectItem>
								<SelectItem value="video">video</SelectItem>
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
						<Button type="submit" disabled={isLoading} class="rounded-xl">
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
