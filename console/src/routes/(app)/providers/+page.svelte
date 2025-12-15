<script lang="ts">
	import { api, type Provider, type ProviderCreate } from '$lib/api'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardFooter,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Switch } from '$lib/components/ui/switch'
	import { Bot, Cpu, Pencil, Plus, Server, Settings2, Sparkles, Trash2 } from '@lucide/svelte'
	import { onMount } from 'svelte'

	let providers = $state<Provider[]>([])
	let showModal = $state(false)
	let modalMode = $state<'create' | 'edit'>('create')
	let modalStep = $state<'select' | 'configure'>('select')
	let isLoading = $state(false)
	let isFetching = $state(true)
	let editingId = $state<string | null>(null)
	let error = $state<string | null>(null)
	let submitError = $state<string | null>(null)

	// Form state
	let formState = $state<ProviderCreate>({
		name: '',
		adapter_type: 'openai',
		provider_type: 'external',
		base_url: '',
		api_key: '',
		model_prefix: '',
		additional_headers: {},
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
			prefix: 'openai',
			icon: Sparkles,
		},
		{
			id: 'anthropic',
			name: 'Anthropic',
			type: 'anthropic',
			provider_type: 'external',
			url: 'https://api.anthropic.com/v1',
			prefix: 'anthropic',
			icon: Bot,
		},
		{
			id: 'ollama',
			name: 'Ollama',
			type: 'ollama',
			provider_type: 'local',
			url: 'http://localhost:11434/v1',
			prefix: 'ollama',
			icon: Cpu,
		},
		{
			id: 'azure',
			name: 'Azure OpenAI',
			type: 'azure',
			provider_type: 'external',
			url: '',
			prefix: 'azure',
			icon: Server,
		},
		{
			id: 'custom',
			name: 'custom',
			type: 'openai', // default to openai compatible
			provider_type: 'external',
			url: '',
			prefix: '',
			icon: Settings2,
		},
	]

	onMount(async () => {
		await loadProviders()
	})

	async function loadProviders() {
		error = null
		try {
			providers = await api.getProviders()
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
			provider_type: provider.provider_type,
			base_url: provider.base_url,
			model_prefix: provider.model_prefix,
			additional_headers: provider.additional_headers,
			is_autofetch_enabled: provider.is_autofetch_enabled,
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
		formState.provider_type = preset.provider_type as 'local' | 'external'
		formState.base_url = preset.url
		formState.model_prefix = preset.prefix
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
			model_prefix: '',
			additional_headers: {},
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

		formState.additional_headers = headers
		submitError = null

		try {
			if (modalMode === 'create') {
				await api.createProvider(formState)
			} else if (editingId) {
				await api.updateProvider(editingId, formState)
			}
			await loadProviders()
			showModal = false
			resetForm()
		} catch (e) {
			console.error('Failed to save provider', e)
			submitError =
				'Failed to save provider. ' + (e instanceof Error ? e.message : 'Unknown error')
		} finally {
			isLoading = false
		}
	}

	async function handleDeleteProvider() {
		if (!editingId) return
		if (!confirm('Are you sure you want to delete this provider?')) return
		isLoading = true
		submitError = null
		try {
			await api.deleteProvider(editingId)
			await loadProviders()
			showModal = false
			resetForm()
		} catch (e) {
			console.error('Failed to delete provider', e)
			submitError =
				'Failed to delete provider. ' + (e instanceof Error ? e.message : 'Unknown error')
		} finally {
			isLoading = false
		}
	}

	function handleTestConnection() {
		// TODO: implement provider connection test
	}
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">providers</h2>
			<p class="text-zinc-400">manage your AI model providers.</p>
		</div>
		<Button onclick={openCreateModal} class="gap-2 rounded-xl">
			<Plus class="h-4 w-4" />
			add provider
		</Button>
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
		<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
			{#each providers as provider}
				<Card class="overflow-hidden rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
					<CardHeader>
						<div class="flex items-start justify-between">
							<div>
								<CardTitle>{provider.name}</CardTitle>
								<CardDescription>{provider.adapter_type}</CardDescription>
							</div>
							<Button
								variant="ghost"
								size="icon"
								class="h-8 w-8 text-zinc-400 hover:text-zinc-100"
								onclick={() => openEditModal(provider)}
							>
								<Pencil class="h-4 w-4" />
							</Button>
						</div>
					</CardHeader>
					<CardContent>
						<div class="space-y-1 text-sm text-zinc-400">
							<div class="flex justify-between">
								<span>status:</span>
								<span
									class={provider.status === 'enabled'
										? 'text-green-400'
										: 'text-zinc-500'}>{provider.status}</span
								>
							</div>
							<div class="flex justify-between">
								<span>type:</span>
								<span>{provider.provider_type}</span>
							</div>
							<div class="flex justify-between">
								<span>autofetch:</span>
								<span
									class={provider.is_autofetch_enabled
										? 'text-blue-400'
										: 'text-zinc-500'}
									>{provider.is_autofetch_enabled ? 'enabled' : 'disabled'}</span
								>
							</div>
							{#if provider.model_prefix}
								<div class="flex justify-between">
									<span>prefix:</span>
									<span
										class="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs"
										>{provider.model_prefix}</span
									>
								</div>
							{/if}
							{#if provider.base_url}
								<div class="mt-2 border-t border-zinc-800 pt-2">
									<p class="truncate font-mono text-xs opacity-70">
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

{#if showModal}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
		<Card class="w-full max-w-lg rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader>
				<CardTitle>
					{modalMode === 'create'
						? modalStep === 'select'
							? 'select provider'
							: 'configure provider'
						: 'edit provider'}
				</CardTitle>
				<CardDescription>
					{modalMode === 'create' && modalStep === 'select'
						? 'choose a provider template or start from scratch.'
						: 'enter connection details.'}
				</CardDescription>
			</CardHeader>

			{#if modalMode === 'create' && modalStep === 'select'}
				<CardContent class="grid grid-cols-2 gap-4">
					{#each presets as preset}
						<button
							class="flex flex-col items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 transition-colors hover:border-zinc-700 hover:bg-zinc-800"
							onclick={() => selectPreset(preset)}
						>
							<preset.icon class="h-8 w-8 text-zinc-400" />
							<span class="font-medium">{preset.name}</span>
						</button>
					{/each}
				</CardContent>
				<CardFooter class="flex justify-end">
					<Button variant="outline" class="rounded-xl" onclick={() => (showModal = false)}
						>cancel</Button
					>
				</CardFooter>
			{:else}
				<form onsubmit={handleSubmit}>
					<CardContent class="max-h-[60vh] space-y-4 overflow-y-auto pr-2">
						<div class="space-y-2">
							<Label for="name">name</Label>
							<Input
								id="name"
								bind:value={formState.name}
								required
								placeholder="e.g. OpenAI Production"
								class="rounded-xl"
							/>
						</div>

						<div class="grid grid-cols-2 gap-4">
							<div class="space-y-2">
								<Label for="api_type">API type</Label>
								<select
									id="api_type"
									bind:value={formState.adapter_type}
									class="flex h-10 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm ring-offset-white file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:ring-2 focus-visible:ring-zinc-950 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-950 dark:ring-offset-zinc-950 dark:placeholder:text-zinc-400 dark:focus-visible:ring-zinc-300"
								>
									<option value="openai">OpenAI</option>
									<option value="anthropic">Anthropic</option>
									<option value="ollama">Ollama</option>
									<option value="azure">Azure OpenAI</option>
								</select>
							</div>
							<div class="space-y-2">
								<Label for="provider_type">provider type</Label>
								<select
									id="provider_type"
									bind:value={formState.provider_type}
									class="flex h-10 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm ring-offset-white file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:ring-2 focus-visible:ring-zinc-950 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-950 dark:ring-offset-zinc-950 dark:placeholder:text-zinc-400 dark:focus-visible:ring-zinc-300"
								>
									<option value="external">external</option>
									<option value="local">local</option>
								</select>
							</div>
						</div>

						<div class="space-y-2">
							<Label for="prefix">model prefix</Label>
							<Input
								id="prefix"
								bind:value={formState.model_prefix}
								placeholder="e.g. openai"
								class="rounded-xl"
							/>
							<p class="text-xs text-zinc-500">
								used to namespace models from this provider.
							</p>
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
							<Label for="key">API key</Label>
							<Input
								id="key"
								type="password"
								bind:value={formState.api_key}
								placeholder={modalMode === 'edit' ? '(unchanged)' : 'sk-...'}
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
									{#each headerEntries as entry, i}
										<div class="flex gap-2">
											<Input
												placeholder="Key"
												bind:value={entry.key}
												class="h-8 rounded-lg text-xs"
											/>
											<Input
												placeholder="Value"
												bind:value={entry.value}
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
					</CardContent>
					<CardFooter class="flex justify-between gap-2">
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
							<Button
								type="button"
								variant="destructive"
								class="rounded-xl"
								disabled={isLoading}
								onclick={handleDeleteProvider}
							>
								delete
							</Button>
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
					</CardFooter>
				</form>
			{/if}
		</Card>
	</div>
{/if}
