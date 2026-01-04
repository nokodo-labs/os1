<script lang="ts">
	import { page } from '$app/state'
	import { auth } from '$lib/auth.svelte'
	import {
		Bot,
		Box,
		FlaskConical,
		LayoutDashboard,
		MessageSquare,
		Plug,
		ScrollText,
		Server,
		Users,
	} from '@lucide/svelte'

	let { children } = $props()
</script>

<div class="flex min-h-screen bg-zinc-950 text-zinc-100">
	<!-- Sidebar -->
	<aside class="flex w-64 flex-col border-r border-zinc-800 p-6">
		<div class="mb-8">
			<img
				src="https://nokodo.net/media/images/logo_full.svg"
				alt="nokodo logo"
				class="h-6 w-auto object-contain"
			/>
			<h1 class="text-xl font-semibold">console</h1>
		</div>

		<nav class="flex-1 space-y-2">
			<a
				href="/dashboard"
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page
					.url.pathname === '/dashboard'
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<LayoutDashboard class="h-4 w-4" />
				dashboard
			</a>
			<a
				href="/providers"
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/providers'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Server class="h-4 w-4" />
				providers
			</a>
			<a
				href="/models"
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/models'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Box class="h-4 w-4" />
				models
			</a>
			<a
				href="/agents"
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/agents'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Bot class="h-4 w-4" />
				agents
			</a>
			<a
				href="/plugins"
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/plugins'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Plug class="h-4 w-4" />
				plugins
			</a>
			<a
				href="/playground"
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/playground'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<FlaskConical class="h-4 w-4" />
				playground
			</a>
			<a
				href="/prompts"
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/prompts'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<ScrollText class="h-4 w-4" />
				prompts
			</a>
			<a
				href="/threads"
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/threads'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<MessageSquare class="h-4 w-4" />
				threads
			</a>
			<a
				href="/users"
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/users'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Users class="h-4 w-4" />
				users
			</a>
		</nav>

		<button
			class="mt-auto text-left text-sm text-zinc-400 hover:text-zinc-100"
			onclick={() => auth.logout()}
		>
			sign out
		</button>
	</aside>

	<!-- Main Content -->
	<main class="flex-1 p-8">
		{@render children()}
	</main>
</div>
