<script lang="ts">
	import { page } from '$app/state'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { onMount } from 'svelte'
	import {
		Bell,
		Brain,
		CodeXml,
		Database,
		Gauge,
		Globe,
		Image as ImageIcon,
		ListChecks,
		Paintbrush,
		Palette,
		Plug,
		Search,
		Shield,
		Trash2,
		Users,
	} from '@lucide/svelte'
	import type { Component } from 'svelte'

	let { children } = $props()

	const ctx = getSettingsContext()

	onMount(() => {
		Promise.all([
			ctx.fetchSettings(),
			ctx.fetchAgents(),
			ctx.fetchModels(),
			ctx.fetchProviders(),
		])
	})

	type SettingsSection = {
		path: string
		label: string
		keywords: string
		icon: Component
		color: string
		activeBg: string
	}

	const sections: SettingsSection[] = [
		{
			path: '/ui',
			label: 'UI',
			keywords:
				'theme color scheme light dark system background sidebar collapsed animated galaxy veil silk fog clouds grainient iridescence auth pages',
			icon: Palette,
			color: 'text-violet-400',
			activeBg: 'bg-violet-500/10',
		},
		{
			path: '/ai',
			label: 'AI',
			keywords:
				'agents default memory retrieval consolidation similarity threshold top-k chat context recent relevant pinned past chats context window mode turns pre-build embed filters task models thread metadata titles tags autocomplete summarization memory post-processing deduplication attachment decay image audio video iterations context compaction token-aware truncation model limits max messages trigger ratio token budget summary batch size headroom tool result media generation image model steps video audio',
			icon: Brain,
			color: 'text-indigo-400',
			activeBg: 'bg-indigo-500/10',
		},
		{
			path: '/branding',
			label: 'branding',
			keywords:
				'site name display name browser tab emails app version primary color accent color hex analytics key support email admin email logo url sidebar favicon url public frontend origin oidc cdn origin console origin pwa manifest',
			icon: Paintbrush,
			color: 'text-fuchsia-400',
			activeBg: 'bg-fuchsia-500/10',
		},
		{
			path: '/media',
			label: 'media',
			keywords:
				'base url favicon apple touch icon ios home screen cdn url overrides frontend media assets',
			icon: ImageIcon,
			color: 'text-rose-400',
			activeBg: 'bg-rose-500/10',
		},
		{
			path: '/assets',
			label: 'assets',
			keywords:
				'default embedding model vector database provider qdrant chroma pinecone weaviate milvus pgvector redis opensearch endpoint grpc api key collection name template sparse vectors bm25 normalize scores fusion algorithm reciprocal rank distribution vector size dimensions batch size rerank strategy native external top-k storage backend local s3 root path bucket region access key secret key presigned url ttl multipart threshold chunk size max retries retry mode',
			icon: Database,
			color: 'text-cyan-400',
			activeBg: 'bg-cyan-500/10',
		},
		{
			path: '/limits',
			label: 'limits',
			keywords:
				'max threads per user cap messages per thread file size upload rate limit requests per minute authenticated',
			icon: Gauge,
			color: 'text-amber-400',
			activeBg: 'bg-amber-500/10',
		},
		{
			path: '/soft-delete',
			label: 'soft delete',
			keywords:
				'deleting marks deleted permanently removing database threads notes files retention restore cleanup',
			icon: Trash2,
			color: 'text-red-400',
			activeBg: 'bg-red-500/10',
		},
		{
			path: '/web-search',
			label: 'web search',
			keywords:
				'web search agentic agent native perplexity sonar model prompt params iterations search engine blacklisted domains exclude searxng bing google instance url max results max chars concurrent requests timeout web loader tavily playwright user agent extract depth api key temperature image results',
			icon: Globe,
			color: 'text-emerald-400',
			activeBg: 'bg-emerald-500/10',
		},
		{
			path: '/code-interpreter',
			label: 'code interpreter',
			keywords:
				'sandbox engine code execution enabled e2b api key template pre-installed packages python numpy pandas matplotlib timeout',
			icon: CodeXml,
			color: 'text-sky-400',
			activeBg: 'bg-sky-500/10',
		},
		{
			path: '/tasks',
			label: 'tasks',
			keywords:
				'taskiq background task scheduling thread maintenance backfill cron batch lookback inactivity sweep metadata summaries timeout replacement cleanup',
			icon: ListChecks,
			color: 'text-lime-400',
			activeBg: 'bg-lime-500/10',
		},
		{
			path: '/notifications',
			label: 'notifications',
			keywords:
				'notifications web push VAPID keys public key private key browser push ttl missed grace lookahead scheduling delivery',
			icon: Bell,
			color: 'text-yellow-400',
			activeBg: 'bg-yellow-500/10',
		},
		{
			path: '/security',
			label: 'security',
			keywords:
				'authentication session secret key jwt algorithm oauth cors origins access token expire refresh token session timeout idle allowed email domains register signup admins users manage auto-apply roles cookie secure require email verification oidc openid connect sso issuer client id client secret redirect uri scopes disable password login',
			icon: Shield,
			color: 'text-orange-400',
			activeBg: 'bg-orange-500/10',
		},
		{
			path: '/permissions',
			label: 'permissions',
			keywords:
				'default permissions global defaults role explicit rule resource access thread project file note group reminder list action',
			icon: Users,
			color: 'text-teal-400',
			activeBg: 'bg-teal-500/10',
		},
		{
			path: '/integrations',
			label: 'integrations',
			keywords:
				'Open WebUI import deployments jwt chats memories enable allowed deployment name description origin url external services connections MCP servers tools discovery startup user limits allowed denied origins timeout',
			icon: Plug,
			color: 'text-purple-400',
			activeBg: 'bg-purple-500/10',
		},
	]

	let settingsSearch = $state('')

	const filteredSections = $derived.by(() => {
		const query = settingsSearch.trim().toLowerCase()
		if (!query) return sections
		return sections.filter((section) =>
			`${section.label} ${section.keywords}`.toLowerCase().includes(query)
		)
	})

	const basePath = '/settings'
	const currentPath = $derived(page.url.pathname)
</script>

<div class="flex min-h-0 min-w-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">settings</h2>
			<p class="text-zinc-400">manage backend settings (admin only).</p>
		</div>
	</div>

	<div class="min-h-0 min-w-0 flex-1 overflow-hidden">
		<div class="mx-auto flex h-full min-h-0 w-full max-w-full min-w-0 flex-col gap-6">
			{#if ctx.error}
				<div
					class="rounded-lg border border-red-900/40 bg-red-950/40 p-4 text-sm text-red-200"
				>
					{ctx.error}
				</div>
			{/if}

			{#if ctx.isFetching}
				<div class="flex min-h-0 flex-1 items-center justify-center">
					<NokodoLoader className="opacity-70" />
				</div>
			{:else if ctx.response}
				<div
					class="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[240px_minmax(0,1fr)]"
				>
					<aside class="min-h-0 rounded-2xl border border-zinc-800 bg-zinc-950/70 p-3">
						<div
							class="mb-3 flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-2"
						>
							<Search class="h-4 w-4 shrink-0 text-zinc-500" />
							<input
								bind:value={settingsSearch}
								placeholder="search settings..."
								class="min-w-0 flex-1 bg-transparent text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
							/>
						</div>
						<nav class="flex max-h-[45vh] flex-col gap-1 overflow-y-auto lg:max-h-none">
							{#each filteredSections as section (section.path)}
								{@const href = `${basePath}${section.path}`}
								{@const isActive = currentPath === href}
								<a
									{href}
									class="flex items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition-colors {isActive
										? `${section.activeBg} text-zinc-100`
										: 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'}"
								>
									<section.icon
										class="h-4 w-4 shrink-0 {isActive ? section.color : ''}"
									/>
									{section.label}
								</a>
							{:else}
								<div
									class="rounded-xl border border-dashed border-zinc-800 p-4 text-sm text-zinc-500"
								>
									no sections match
								</div>
							{/each}
						</nav>
					</aside>

					<div class="min-h-0 min-w-0 overflow-y-auto pr-1">
						<div class="min-w-0">
							{@render children()}
						</div>
					</div>
				</div>
			{:else}
				<div class="rounded-lg border border-zinc-800 p-8 text-zinc-400">
					no settings loaded.
				</div>
			{/if}
		</div>
	</div>
</div>
