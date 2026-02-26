<script lang="ts">
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { auth } from '$lib/auth.svelte'
	import {
		Bot,
		Box,
		Brain,
		Database,
		FileText,
		FlaskConical,
		LayoutDashboard,
		ListChecks,
		Menu,
		MessageSquare,
		Plug,
		ScrollText,
		Server,
		Settings,
		Shield,
		StickyNote,
		Users,
		UsersRound,
		X,
	} from '@lucide/svelte'

	let { children } = $props()

	let sidebarOpen = $state(false)

	function openSidebar() {
		sidebarOpen = true
	}

	function closeSidebar() {
		sidebarOpen = false
	}

	// close sidebar on route change
	$effect(() => {
		void page.url.pathname
		sidebarOpen = false
	})
</script>

<div class="flex h-dvh overflow-hidden bg-zinc-950 text-zinc-100">
	<!-- mobile backdrop -->
	{#if sidebarOpen}
		<div
			class="fixed inset-0 z-40 bg-black/60 md:hidden"
			role="presentation"
			aria-hidden="true"
			onclick={closeSidebar}
		></div>
	{/if}

	<!-- Sidebar -->
	<aside
		class="fixed inset-y-0 left-0 z-50 flex h-full w-64 flex-col border-r border-zinc-800 bg-zinc-950 transition-transform duration-300 ease-in-out md:relative md:translate-x-0 {sidebarOpen
			? 'translate-x-0'
			: '-translate-x-full md:translate-x-0'} p-6"
	>
		<!-- sidebar header -->
		<div class="mb-8 flex shrink-0 items-start justify-between">
			<div>
				<img
					src="https://nokodo.net/media/images/logo_full.svg"
					alt="nokodo logo"
					class="h-6 w-auto object-contain"
				/>
				<h1 class="text-xl font-semibold">console</h1>
			</div>
			<button
				type="button"
				class="flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200 md:hidden"
				aria-label="close sidebar"
				onclick={closeSidebar}
			>
				<X class="h-4 w-4" />
			</button>
		</div>

		<!-- scrollable nav -->
		<nav class="-mr-2 flex-1 space-y-1 overflow-y-auto pr-2">
			<a
				href={resolve('/dashboard')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page
					.url.pathname === '/dashboard'
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<LayoutDashboard class="h-4 w-4" />
				dashboard
			</a>
			<a
				href={resolve('/providers')}
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
				href={resolve('/models')}
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
				href={resolve('/agents')}
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
				href={resolve('/plugins')}
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
				href={resolve('/playground')}
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
				href={resolve('/prompts')}
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
				href={resolve('/threads')}
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
				href={resolve('/notes')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/notes'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<StickyNote class="h-4 w-4" />
				notes
			</a>
			<a
				href={resolve('/reminders')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/reminders'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<ListChecks class="h-4 w-4" />
				reminders
			</a>
			<a
				href={resolve('/memories')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/memories'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Brain class="h-4 w-4" />
				memories
			</a>
			<a
				href={resolve('/(app)/vectors')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/vectors'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Database class="h-4 w-4" />
				vectors
			</a>
			<a
				href={resolve('/users')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/users'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Users class="h-4 w-4" />
				users
			</a>
			<a
				href={resolve('/groups')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/groups'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<UsersRound class="h-4 w-4" />
				groups
			</a>
			<a
				href={resolve('/files')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/files'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<FileText class="h-4 w-4" />
				files
			</a>
			<a
				href={resolve('/roles')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/roles'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Shield class="h-4 w-4" />
				roles
			</a>
			<a
				href={resolve('/settings')}
				class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors {page.url.pathname.startsWith(
					'/settings'
				)
					? 'bg-zinc-800 text-white'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				<Settings class="h-4 w-4" />
				settings
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
	<main class="flex flex-1 flex-col overflow-hidden">
		<!-- mobile top bar -->
		<div class="flex shrink-0 items-center gap-3 border-b border-zinc-800 px-4 py-3 md:hidden">
			<button
				type="button"
				class="flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
				aria-label="open sidebar"
				onclick={openSidebar}
			>
				<Menu class="h-4 w-4" />
			</button>
			<span class="text-sm font-semibold text-zinc-100">console</span>
		</div>
		<div class="flex flex-1 flex-col overflow-auto p-8">
			{@render children()}
		</div>
	</main>
</div>
