<script lang="ts">
	import { api } from '$lib/api/client'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import QuestionMarkCircle from '$lib/components/icons/QuestionMarkCircle.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import type { SelectorOption } from '$lib/components/primitives'
	import { ActionButton, Selector } from '$lib/components/primitives'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { onMount } from 'svelte'

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
		memories_imported: number
		memories_skipped: number
		errors: string[]
	}

	let selectedOrigin = $state('')
	let credential = $state('')
	let sourcesEnabled = $state(false)
	let deployments = $state<OpenWebUIDeployment[]>([])
	let sourcesLoaded = $state(false)
	let sourcesError = $state<string | null>(null)
	let importing = $state(false)
	let importError = $state<string | null>(null)
	let importResult = $state<OpenWebUIImportSummary | null>(null)
	let showHowTo = $state(false)

	const selectedDeployment = $derived(
		deployments.find((deployment) => deployment.origin === selectedOrigin) ?? null
	)

	const deploymentOptions = $derived<SelectorOption[]>(
		deployments.map((deployment) => ({
			value: deployment.origin,
			label: deployment.name,
			description: deployment.description,
			iconUrl: faviconUrl(deployment.origin),
		}))
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

	function faviconUrl(origin: string): string | undefined {
		try {
			const url = new URL(origin)
			return `https://www.google.com/s2/favicons?sz=64&domain_url=${encodeURIComponent(url.origin)}`
		} catch {
			return undefined
		}
	}

	const openWebUIFaviconUrl = faviconUrl('https://openwebui.com')

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

	async function runImport() {
		if (!selectedOrigin || !credential) {
			importError = 'choose a deployment and paste your Open WebUI key'
			return
		}
		importing = true
		importError = null
		importResult = null
		const { data, error, response } = await api.POST('/v1/integrations/open-webui/import', {
			body: {
				deployment_origin: selectedOrigin,
				jwt: credential,
				include_chats: true,
				include_memories: true,
			},
		})
		if (error || !data) {
			const detail = (error as { detail?: unknown })?.detail
			importError =
				typeof detail === 'string'
					? detail
					: response?.status === 401
						? 'Open WebUI rejected that key'
						: response?.status === 502
							? 'cannot reach that Open WebUI deployment'
							: 'import failed'
			importing = false
			return
		}
		importResult = data as unknown as OpenWebUIImportSummary
		importing = false
	}

	function openSelectedDeployment() {
		if (!selectedDeployment) return
		window.open(selectedDeployment.origin, '_blank', 'noopener,noreferrer')
	}

	onMount(() => {
		void loadSources()
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
							<img src={openWebUIFaviconUrl} alt="" class="h-7 w-7 object-contain" />
						{:else}
							<GlobeAlt class="text-foreground/70 h-5 w-5" />
						{/if}
					</div>
					<div class="min-w-0">
						<div class="text-foreground/90 text-base font-semibold">Open WebUI</div>
						<div class="text-foreground/55 mt-1 text-sm">
							import your chats and memories from an allowed Open WebUI deployment.
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
						onsubmit={(event) => event.preventDefault()}
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
								disabled={importing}
							/>
							<p class="text-foreground/45 mt-1.5 text-xs">
								your key is used only for this import and is never stored.
							</p>
						</div>

						<ActionButton
							variant="secondary"
							class="w-full"
							disabled={importing || !selectedOrigin || !credential}
							onclick={runImport}
						>
							<Download class="h-4 w-4" />
							{#if importing}
								<ShimmerText className="inline-block">importing</ShimmerText>
							{:else}
								import chats and memories
							{/if}
						</ActionButton>
					</form>
				{/if}

				{#if importError}
					<div
						class="rounded-container border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
					>
						{importError}
					</div>
				{/if}
				{#if importResult}
					<div
						class="rounded-container border-foreground/14 bg-foreground/5 border p-3 text-sm"
					>
						<div class="text-foreground/90 font-semibold">import complete</div>
						<div class="text-foreground/65 mt-1.5 grid gap-1 text-xs sm:grid-cols-2">
							<div>{importResult.chats_imported} chats</div>
							<div>{importResult.messages_imported} messages</div>
							<div>{importResult.memories_imported} memories</div>
							<div>
								{importResult.chats_skipped + importResult.memories_skipped} skipped
							</div>
						</div>
						{#if importResult.errors.length > 0}
							<div class="mt-2 text-xs text-amber-300/85">
								{importResult.errors.length} item(s) finished with warnings.
							</div>
						{/if}
					</div>
				{/if}
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
			<ActionButton variant="ghost" onclick={() => (showHowTo = false)}>done</ActionButton>
		</div>
	</div>
</BaseModal>
