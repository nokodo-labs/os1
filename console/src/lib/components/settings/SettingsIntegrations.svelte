<script lang="ts">
	import { api, type Schemas } from '$lib/api'
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
	import { Switch } from '$lib/components/ui/switch'
	import { Plus, RefreshCw, Save, Trash } from '@lucide/svelte'

	type SettingsResponse = Schemas['SettingsResponse']
	type SettingsUpdateRequest = Schemas['SettingsUpdateRequest']
	type Deployment = Schemas['OpenWebUIDeploymentPatch']

	const emptySettingsVersions: Schemas['SettingsVersions'] = {
		ui: 0,
		ai: 0,
		branding: 0,
		media: 0,
		assets: 0,
		limits: 0,
		security: 0,
		notifications: 0,
		soft_delete: 0,
		web_search: 0,
		code_interpreter: 0,
		default_permissions: 0,
		integrations: 0,
		cache: 0,
		tasks: 0,
	}

	let enabled = $state(true)
	let deployments = $state<Deployment[]>([])
	let originalSnapshot = $state<string>('')

	let isFetching = $state(true)
	let isSaving = $state(false)
	let error = $state<string | null>(null)
	let success = $state<string | null>(null)

	let expectedVersion = $state<number>(0)

	function snapshot(): string {
		return JSON.stringify({ enabled, deployments })
	}

	const hasChanges = $derived(snapshot() !== originalSnapshot)

	async function load() {
		isFetching = true
		error = null
		success = null
		const result = await api.GET('/v1/settings', {})
		if (result.error) {
			error = 'failed to load settings'
			isFetching = false
			return
		}
		const data: SettingsResponse = result.data
		const owui = data.data.integrations?.open_webui
		enabled = owui?.enabled ?? true
		deployments = (owui?.deployments ?? []).map((deployment) => ({
			name: deployment.name,
			description: String(deployment.description ?? ''),
			origin: deployment.origin,
		}))
		expectedVersion = Number(data.versions?.integrations ?? 0)
		originalSnapshot = snapshot()
		isFetching = false
	}

	function addDeployment() {
		deployments = [...deployments, { name: '', description: '', origin: '' }]
	}

	function removeDeployment(idx: number) {
		deployments = deployments.filter((_, i) => i !== idx)
	}

	function validate(): string | null {
		const origins: string[] = []
		for (const [i, d] of deployments.entries()) {
			if (!d.name || !d.description || !d.origin) {
				return `deployment #${i + 1}: name, description, and origin are required`
			}
			let normalizedOrigin: string
			try {
				const url = new URL(d.origin)
				normalizedOrigin = url.origin.toLowerCase()
			} catch {
				return `deployment #${i + 1}: origin must be a valid URL`
			}
			if (origins.includes(normalizedOrigin)) {
				return `deployment #${i + 1}: duplicate origin "${d.origin}"`
			}
			origins.push(normalizedOrigin)
		}
		return null
	}

	async function save() {
		const v = validate()
		if (v) {
			error = v
			return
		}
		isSaving = true
		error = null
		success = null
		const body: SettingsUpdateRequest = {
			data: {
				integrations: {
					open_webui: {
						enabled,
						deployments: deployments.map((d) => ({
							name: d.name,
							description: d.description,
							origin: d.origin,
						})),
					},
				},
			},
			expected_versions: { ...emptySettingsVersions, integrations: expectedVersion },
		}
		const result = await api.PATCH('/v1/settings', {
			body,
		})
		if (result.error) {
			if (result.response.status === 409) {
				error = 'integrations were updated elsewhere. reload and try again.'
			} else {
				const detail = (result.error as { detail?: unknown })?.detail
				error = typeof detail === 'string' ? detail : 'failed to save'
			}
			isSaving = false
			return
		}
		const data: SettingsResponse | undefined = result.data
		expectedVersion = Number(data?.versions.integrations ?? expectedVersion + 1)
		originalSnapshot = snapshot()
		success = 'saved'
		isSaving = false
	}

	$effect(() => {
		void load()
	})
</script>

<Card class="border-zinc-800 bg-zinc-900">
	<CardHeader>
		<CardTitle>integrations</CardTitle>
		<CardDescription>
			Open WebUI import deployments. users will be able to pick from this list and provide
			their own key to import all chats and memories.
		</CardDescription>
	</CardHeader>
	<CardContent class="space-y-5">
		{#if error}
			<div class="rounded-lg border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200">
				{error}
			</div>
		{/if}
		{#if success}
			<div
				class="rounded-lg border border-emerald-900/40 bg-emerald-950/40 p-3 text-sm text-emerald-200"
			>
				{success}
			</div>
		{/if}

		<div class="flex items-center justify-between gap-4">
			<div class="space-y-1">
				<Label>enable Open WebUI import</Label>
				<p class="text-xs text-zinc-500">
					when off, users cannot trigger imports regardless of configured deployments.
				</p>
			</div>
			<Switch bind:checked={enabled} disabled={isFetching || isSaving} />
		</div>

		<div class="space-y-3">
			<div class="flex items-center justify-between">
				<Label>allowed Open WebUI deployments</Label>
				<Button
					size="sm"
					variant="secondary"
					class="rounded-xl"
					onclick={addDeployment}
					disabled={isFetching || isSaving}
				>
					<Plus class="mr-1.5 h-4 w-4" />
					add deployment
				</Button>
			</div>
			{#if deployments.length === 0}
				<p class="text-xs text-zinc-500">no deployments configured.</p>
			{/if}
			{#each deployments as dep, idx (idx)}
				<div class="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4">
					<div class="grid gap-3 md:grid-cols-2">
						<div class="space-y-1">
							<Label for={`owui-name-${idx}`}>name</Label>
							<Input
								id={`owui-name-${idx}`}
								class="rounded-lg"
								placeholder="workspace Open WebUI"
								bind:value={dep.name}
							/>
						</div>
						<div class="space-y-1">
							<Label for={`owui-origin-${idx}`}>origin URL</Label>
							<Input
								id={`owui-origin-${idx}`}
								class="rounded-lg"
								placeholder="https://owui.example.com"
								bind:value={dep.origin}
							/>
						</div>
						<div class="space-y-1 md:col-span-2">
							<Label for={`owui-description-${idx}`}>description</Label>
							<Input
								id={`owui-description-${idx}`}
								class="rounded-lg"
								placeholder="company-hosted Open WebUI workspace"
								bind:value={dep.description}
							/>
						</div>
					</div>
					<div class="mt-3 flex justify-end">
						<Button
							size="sm"
							variant="ghost"
							class="rounded-lg text-red-300 hover:bg-red-950/40 hover:text-red-200"
							onclick={() => removeDeployment(idx)}
						>
							<Trash class="mr-1.5 h-4 w-4" />
							remove
						</Button>
					</div>
				</div>
			{/each}
		</div>

		<div class="flex items-center justify-end gap-2 pt-2">
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={load}
				disabled={isFetching || isSaving}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				reload
			</Button>
			<Button
				class="rounded-xl"
				onclick={save}
				disabled={!hasChanges || isFetching || isSaving}
			>
				<Save class="mr-1.5 h-4 w-4" />
				{isSaving ? 'saving...' : 'save'}
			</Button>
		</div>
	</CardContent>
</Card>
