<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type Provider = Schemas['Provider']
	type ProviderCreate = Schemas['ProviderCreate']
	type ProviderType = Schemas['ProviderType']
	type ProviderUpdate = Schemas['ProviderUpdate']

	import EmptyState from '$lib/components/EmptyState.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
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
		Bot,
		Cpu,
		Plus,
		RefreshCw,
		Search,
		Server,
		Settings2,
		Sparkles,
		Trash2,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'
	import { onMount } from 'svelte'

	let providers = $state<Provider[]>([])
	let searchQuery = $state('')
	let showModal = $state(false)
	let modalMode = $state<'create' | 'edit'>('create')
	let modalStep = $state<'select' | 'configure'>('select')
	let isLoading = $state(false)
	let isFetching = $state(true)
	let editingId = $state<string | null>(null)
	let error = $state<string | null>(null)
	let submitError = $state<string | null>(null)

	type ProviderFormState = {
		name: string
		adapter_type: string
		provider_type: ProviderType
		base_url: string
		api_key: string
		is_autofetch_enabled: boolean
	}

	// Form state (UI-friendly)
	let formState = $state<ProviderFormState>({
		name: '',
		adapter_type: 'openai',
		provider_type: 'external',
		base_url: '',
		api_key: '',
		is_autofetch_enabled: true,
	})

	// Temporary state for headers editing
	let headerEntries = $state<Array<{ key: string; value: string }>>([])

	const presets = [
		{
			id: 'openai',
			name: 'OpenAI',
			type: 'openai',
			provider_type: 'external',
			url: 'https://api.openai.com/v1',
			icon: Sparkles,
		},
		{
			id: 'google',
			name: 'Google',
			type: 'google',
			provider_type: 'external',
			url: '',
			icon: Sparkles,
		},
		{
			id: 'anthropic',
			name: 'Anthropic',
			type: 'anthropic',
			provider_type: 'external',
			url: 'https://api.anthropic.com/v1',
			icon: Bot,
		},
		{
			id: 'ollama',
			name: 'Ollama',
			type: 'ollama',
			provider_type: 'local',
			url: 'http://localhost:11434/v1',
			icon: Cpu,
		},
		{
			id: 'custom',
			name: 'custom',
			type: 'openai', // default to openai compatible
			provider_type: 'external',
			url: '',
			icon: Settings2,
		},
	]

	const filteredProviders = $derived.by(() => {
		if (!searchQuery.trim()) return providers
		const q = searchQuery.toLowerCase()
		return providers.filter(
			(p) =>
				p.name.toLowerCase().includes(q) ||
				p.adapter_type.toLowerCase().includes(q) ||
				p.id.toLowerCase().includes(q)
		)
	})

	onMount(async () => {
		await loadProviders()
	})

	async function loadProviders() {
		error = null
		try {
			providers = unwrap(await api.GET('/v1/providers'))
		} catch (e) {
			console.error('Failed to load providers', e)
			error = 'Failed to load providers. Please check if the backend is running.'
		} finally {
			isFetching = false
		}
	}

	function openCreateModal() {
		modalMode = 'create'
		modalStep = 'select'
		showModal = true
		editingId = null
		submitError = null
		resetForm()
	}

	function openEditModal(provider: Provider) {
		modalMode = 'edit'
		modalStep = 'configure'
		editingId = provider.id
		submitError = null
		formState = {
			name: provider.name,
			adapter_type: provider.adapter_type,
			provider_type: provider.provider_type || 'external',
			base_url: provider.base_url || '',
			is_autofetch_enabled: provider.is_autofetch_enabled ?? true,
			api_key: '', // Don't show existing key
		}
		// Convert headers object to array for editing
		headerEntries = Object.entries(provider.additional_headers || {}).map(([key, value]) => ({
			key,
			value,
		}))
		showModal = true
	}

	function selectPreset(preset: (typeof presets)[0]) {
		formState.adapter_type = preset.type
		formState.provider_type = preset.provider_type as ProviderType
		formState.base_url = preset.url
		if (preset.id !== 'custom') {
			formState.name = preset.name
		}
		modalStep = 'configure'
	}

	function resetForm() {
		formState = {
			name: '',
			adapter_type: 'openai',
			provider_type: 'external',
			base_url: '',
			api_key: '',
			is_autofetch_enabled: true,
		}
		headerEntries = []
	}

	function addHeader() {
		headerEntries = [...headerEntries, { key: '', value: '' }]
	}

	function removeHeader(index: number) {
		headerEntries = headerEntries.filter((_, i) => i !== index)
	}

	async function handleSubmit(e: Event) {
		e.preventDefault()
		isLoading = true

		// Convert headers array back to object
		const headers = headerEntries.reduce(
			(acc, { key, value }) => {
				if (key.trim()) acc[key.trim()] = value.trim()
				return acc
			},
			{} as Record<string, string>
		)

		submitError = null

		if (!formState.name.trim()) {
			submitError = 'provider name is required'
			isLoading = false
			return
		}

		try {
			if (modalMode === 'create') {
				const payload: ProviderCreate = {
					name: formState.name.trim(),
					adapter_type: formState.adapter_type,
					provider_type: formState.provider_type,
					base_url: formState.base_url.trim() ? formState.base_url.trim() : null,
					api_key: formState.api_key.trim() ? formState.api_key.trim() : null,
					additional_headers: Object.keys(headers).length > 0 ? headers : null,
					status: 'enabled',
					is_autofetch_enabled: formState.is_autofetch_enabled,
				}
				unwrap(await api.POST('/v1/providers', { body: payload }))
			} else if (editingId) {
				const payload: ProviderUpdate = {
					name: formState.name.trim() || undefined,
					adapter_type: formState.adapter_type,
					provider_type: formState.provider_type,
					base_url: formState.base_url.trim() ? formState.base_url.trim() : null,
					additional_headers: Object.keys(headers).length > 0 ? headers : null,
					is_autofetch_enabled: formState.is_autofetch_enabled,
				}
				if (formState.api_key.trim()) payload.api_key = formState.api_key.trim()
				unwrap(
					await api.PATCH('/v1/providers/{provider_id}', {
						params: { path: { provider_id: editingId } },
						body: payload,
					})
				)
			}
			await loadProviders()
			showModal = false
			resetForm()
		} catch (e) {
			console.error('Failed to save provider', e)
			submitError = e instanceof Error ? e.message : 'failed to save provider'
		} finally {
			isLoading = false
		}
	}

	function handleTestConnection() {
		// TODO: implement provider connection test
	}
</script>

<div class="flex flex-col gap-6">
	<div class="space-y-6">
		<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
			<div>
				<h2 class="text-2xl font-bold tracking-tight">providers</h2>
				<p class="text-zinc-400">manage your AI model providers.</p>
			</div>
			<div
				class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center"
			>
				<div class="relative w-full sm:w-auto sm:flex-1">
					<Search
						class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500"
					/>
					<Input
						type="search"
						placeholder="search providers..."
						bind:value={searchQuery}
						class="w-full pl-8 sm:w-50 lg:w-75"
					/>
				</div>
				<div class="flex w-full items-center gap-2 sm:w-auto">
					<Button onclick={openCreateModal} class="flex-1 gap-2 rounded-xl sm:flex-none">
						<Plus class="h-4 w-4" />
						add provider
					</Button>
					<Button
						variant="outline"
						class="flex-1 rounded-xl sm:flex-none"
						onclick={() => loadProviders()}
						disabled={isFetching}
					>
						<RefreshCw class="mr-2 h-4 w-4 {isFetching ? 'animate-spin' : ''}" />
						{isFetching ? 'loading...' : 'refresh'}
					</Button>
				</div>
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
				<Button variant="outline" class="mt-4" onclick={loadProviders}>Retry</Button>
			</div>
		{:else}
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each filteredProviders as provider (provider.id)}
					<Card
						class="flex shrink-0 cursor-pointer flex-col overflow-hidden rounded-2xl border-zinc-800 bg-zinc-900 transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
						onclick={() => openEditModal(provider)}
						onkeydown={(event) => {
							if (event.key === 'Enter' || event.key === ' ') {
								event.preventDefault()
								openEditModal(provider)
							}
						}}
						role="button"
						tabindex={0}
					>
						<CardHeader class="border-b border-zinc-800/50 px-4 py-4">
							<div class="flex items-start justify-between gap-4">
								<div class="flex min-w-0 flex-1 items-start gap-3">
									<div
										class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-400"
									>
										<Server class="h-4 w-4" />
									</div>
									<div class="min-w-0 flex-1">
										<CardTitle class="truncate text-base"
											>{provider.name}</CardTitle
										>
										<CardDescription class="mt-1 truncate text-xs"
											>{provider.adapter_type}</CardDescription
										>
									</div>
								</div>
							</div>
						</CardHeader>
						<CardContent class="flex flex-1 flex-col justify-end px-4 py-4">
							<div class="flex flex-col gap-2 text-xs">
								<div class="flex items-center justify-between gap-2">
									<div class="flex items-center gap-2">
										<div
											class={`h-2 w-2 rounded-full ${provider.status === 'enabled' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-zinc-700'}`}
										></div>
										<span
											class="text-xs font-medium tracking-wider text-zinc-400 uppercase"
										>
											{provider.status}
										</span>
									</div>
									<span
										class="truncate font-medium tracking-wider text-zinc-500 uppercase"
									>
										{provider.provider_type}
									</span>
								</div>
								{#if provider.is_autofetch_enabled}
									<div
										class="mt-1 flex items-center justify-between gap-2 border-t border-zinc-800/50 pt-2"
									>
										<span
											class="shrink-0 font-medium tracking-wider text-zinc-600 uppercase"
											>models</span
										>
										<span
											class="inline-flex items-center rounded-md bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium tracking-wider text-blue-400 uppercase"
										>
											autofetched
										</span>
									</div>
								{/if}
								{#if provider.base_url}
									<div class="mt-1 border-t border-zinc-800/50 pt-2">
										<p
											class="truncate font-mono text-[10px] text-zinc-500"
											title={provider.base_url}
										>
											{provider.base_url}
										</p>
									</div>
								{/if}
							</div>
						</CardContent>
					</Card>
				{/each}

				{#if providers.length === 0}
					<EmptyState message="no providers configured yet." />
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
			data-dialog-content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[90vh] w-[min(512px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">
						{modalMode === 'create'
							? modalStep === 'select'
								? 'select provider'
								: 'configure provider'
							: 'edit provider'}
					</Dialog.Title>
					<p class="text-sm text-zinc-400">
						{modalMode === 'create' && modalStep === 'select'
							? 'choose a provider template or start from scratch.'
							: 'enter connection details.'}
					</p>
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

			{#if modalMode === 'create' && modalStep === 'select'}
				<div class="min-h-0 flex-1 overflow-y-auto px-6 py-4">
					<div class="grid grid-cols-2 gap-4">
						{#each presets as preset (preset.name)}
							<button
								class="flex flex-col items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 transition-colors hover:border-zinc-700 hover:bg-zinc-800"
								onclick={() => selectPreset(preset)}
							>
								<preset.icon class="h-8 w-8 text-zinc-400" />
								<span class="font-medium">{preset.name}</span>
							</button>
						{/each}
					</div>
				</div>
				<div class="flex shrink-0 justify-end border-t border-zinc-800 px-6 py-4">
					<Button variant="outline" class="rounded-xl" onclick={() => (showModal = false)}
						>cancel</Button
					>
				</div>
			{:else}
				<form onsubmit={handleSubmit} class="flex min-h-0 flex-1 flex-col">
					<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
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
								bind:value={formState.name}
								placeholder="e.g. my openai provider"
								class="rounded-xl"
							/>
						</div>

						<div class="space-y-2">
							<Label for="api_type">API type</Label>
							<Select
								value={formState.adapter_type}
								onValueChange={(v: string) => (formState.adapter_type = v)}
							>
								<SelectTrigger id="api_type" class="rounded-xl">
									<span class="truncate text-left">
										{formState.adapter_type === 'openai'
											? 'OpenAI'
											: formState.adapter_type === 'google'
												? 'Google'
												: formState.adapter_type === 'anthropic'
													? 'Anthropic'
													: formState.adapter_type === 'ollama'
														? 'Ollama'
														: formState.adapter_type}
									</span>
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="openai">OpenAI</SelectItem>
									<SelectItem value="google">Google</SelectItem>
									<SelectItem value="anthropic">Anthropic</SelectItem>
									<SelectItem value="ollama">Ollama</SelectItem>
								</SelectContent>
							</Select>
						</div>

						<div class="space-y-2">
							<Label for="provider_type">provider type</Label>
							<Select
								value={formState.provider_type}
								onValueChange={(v: string) =>
									(formState.provider_type = v as ProviderType)}
							>
								<SelectTrigger id="provider_type" class="rounded-xl">
									<span class="truncate text-left">{formState.provider_type}</span
									>
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="external">external</SelectItem>
									<SelectItem value="local">local</SelectItem>
								</SelectContent>
							</Select>
						</div>

						<div class="flex items-center justify-between">
							<div class="space-y-0.5">
								<Label for="autofetch">model autofetch</Label>
								<p class="text-xs text-zinc-500">
									automatically sync available models from API.
								</p>
							</div>
							<Switch
								id="autofetch"
								checked={formState.is_autofetch_enabled}
								onCheckedChange={(v: boolean) =>
									(formState.is_autofetch_enabled = v)}
							/>
						</div>

						<div class="space-y-2">
							<Label for="url">base URL (optional)</Label>
							<Input
								id="url"
								bind:value={formState.base_url}
								placeholder="https://api.openai.com/v1"
								class="rounded-xl"
							/>
						</div>
						<div class="space-y-2">
							<Label for="key">API key (secret)</Label>
							<Input
								id="key"
								type="password"
								bind:value={formState.api_key}
								placeholder={modalMode === 'edit' ? '(unchanged)' : 'sk-...'}
								autocomplete="off"
								class="rounded-xl"
							/>
						</div>

						<div class="space-y-2 border-t border-zinc-800 pt-2">
							<div class="flex items-center justify-between">
								<Label>additional headers</Label>
								<Button
									type="button"
									variant="ghost"
									size="sm"
									onclick={addHeader}
									class="h-6 text-xs"
								>
									<Plus class="mr-1 h-3 w-3" /> add
								</Button>
							</div>

							{#if headerEntries.length === 0}
								<p class="text-xs text-zinc-500 italic">no additional headers.</p>
							{:else}
								<div class="space-y-2">
									{#each headerEntries as entry, i (i)}
										<div
											class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
										>
											<Label class="sr-only" for={`header-key-${i}`}
												>header key</Label
											>
											<Input
												id={`header-key-${i}`}
												placeholder="key"
												bind:value={entry.key}
												autocomplete="off"
												class="h-8 rounded-lg text-xs"
											/>
											<Label class="sr-only" for={`header-value-${i}`}
												>header value (secret)</Label
											>
											<Input
												id={`header-value-${i}`}
												type="password"
												placeholder="value"
												bind:value={entry.value}
												autocomplete="off"
												class="h-8 rounded-lg text-xs"
											/>
											<Button
												type="button"
												variant="ghost"
												size="icon"
												class="h-8 w-8 shrink-0 text-zinc-500 hover:text-red-400"
												onclick={() => removeHeader(i)}
											>
												<Trash2 class="h-3 w-3" />
											</Button>
										</div>
									{/each}
								</div>
							{/if}
						</div>

						{#if submitError}
							<div class="rounded-lg bg-red-900/20 p-3 text-sm text-red-400">
								{submitError}
							</div>
						{/if}
					</div>
					<div
						class="flex shrink-0 justify-between gap-2 border-t border-zinc-800 px-6 py-4"
					>
						{#if modalMode === 'create'}
							<Button
								variant="ghost"
								type="button"
								class="rounded-xl"
								onclick={() => (modalStep = 'select')}
							>
								back
							</Button>
						{:else}
							<span></span>
						{/if}
						<div class="flex gap-2">
							<Button
								type="button"
								variant="outline"
								class="rounded-xl"
								disabled={isLoading}
								onclick={handleTestConnection}
							>
								test
							</Button>
							<Button
								variant="outline"
								type="button"
								class="rounded-xl"
								onclick={() => (showModal = false)}>cancel</Button
							>
							<Button type="submit" disabled={isLoading} class="rounded-xl">
								{isLoading
									? 'saving...'
									: modalMode === 'create'
										? 'add provider'
										: 'save changes'}
							</Button>
						</div>
					</div>
				</form>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
