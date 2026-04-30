<script lang="ts">
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { auth } from '$lib/auth.svelte'
	import {
		Bot,
		Box,
		Brain,
		Activity,
		Database,
		FileText,
		FlaskConical,
		FolderKanban,
		LayoutDashboard,
		ListChecks,
		Menu,
		MessageSquare,
		Network,
		Plug,
		ScrollText,
		Server,
		Settings,
		Shield,
		StickyNote,
		Users,
		X,
	} from '@lucide/svelte'
	import type { Component } from 'svelte'

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

	type NavRoute =
		| '/dashboard'
		| '/providers'
		| '/models'
		| '/agents'
		| '/plugins'
		| '/playground'
		| '/prompts'
		| '/threads'
		| '/projects'
		| '/notes'
		| '/reminders'
		| '/tasks'
		| '/files'
		| '/memories'
		| '/vectors'
		| '/users'
		| '/groups'
		| '/roles'
		| '/settings'

	type NavItem = {
		href: string
		match: NavRoute
		label: string
		icon: Component
		// always-on icon color (per-resource accent)
		color: string
		// active background tint
		activeBg: string
	}

	const navItems: NavItem[] = [
		{
			href: resolve('/dashboard'),
			match: '/dashboard',
			label: 'dashboard',
			icon: LayoutDashboard,
			color: 'text-zinc-300',
			activeBg: 'bg-zinc-800',
		},
		{
			href: resolve('/providers'),
			match: '/providers',
			label: 'providers',
			icon: Server,
			color: 'text-cyan-400',
			activeBg: 'bg-cyan-500/15',
		},
		{
			href: resolve('/models'),
			match: '/models',
			label: 'models',
			icon: Box,
			color: 'text-blue-400',
			activeBg: 'bg-blue-500/15',
		},
		{
			href: resolve('/agents'),
			match: '/agents',
			label: 'agents',
			icon: Bot,
			color: 'text-indigo-400',
			activeBg: 'bg-indigo-500/15',
		},
		{
			href: resolve('/plugins'),
			match: '/plugins',
			label: 'plugins',
			icon: Plug,
			color: 'text-violet-400',
			activeBg: 'bg-violet-500/15',
		},
		{
			href: resolve('/playground'),
			match: '/playground',
			label: 'playground',
			icon: FlaskConical,
			color: 'text-lime-400',
			activeBg: 'bg-lime-500/15',
		},
		{
			href: resolve('/prompts'),
			match: '/prompts',
			label: 'prompts',
			icon: ScrollText,
			color: 'text-fuchsia-400',
			activeBg: 'bg-fuchsia-500/15',
		},
		{
			href: resolve('/threads'),
			match: '/threads',
			label: 'threads',
			icon: MessageSquare,
			color: 'text-emerald-400',
			activeBg: 'bg-emerald-500/15',
		},
		{
			href: resolve('/projects'),
			match: '/projects',
			label: 'projects',
			icon: FolderKanban,
			color: 'text-yellow-400',
			activeBg: 'bg-yellow-500/15',
		},
		{
			href: resolve('/notes'),
			match: '/notes',
			label: 'notes',
			icon: StickyNote,
			color: 'text-amber-400',
			activeBg: 'bg-amber-500/15',
		},
		{
			href: resolve('/reminders'),
			match: '/reminders',
			label: 'reminders',
			icon: ListChecks,
			color: 'text-sky-400',
			activeBg: 'bg-sky-500/15',
		},
		{
			href: '/tasks',
			match: '/tasks',
			label: 'tasks',
			icon: Activity,
			color: 'text-lime-400',
			activeBg: 'bg-lime-500/15',
		},
		{
			href: resolve('/files'),
			match: '/files',
			label: 'files',
			icon: FileText,
			color: 'text-rose-400',
			activeBg: 'bg-rose-500/15',
		},
		{
			href: resolve('/memories'),
			match: '/memories',
			label: 'memories',
			icon: Brain,
			color: 'text-purple-400',
			activeBg: 'bg-purple-500/15',
		},
		{
			href: resolve('/vectors'),
			match: '/vectors',
			label: 'vectors',
			icon: Database,
			color: 'text-teal-400',
			activeBg: 'bg-teal-500/15',
		},
		{
			href: resolve('/users'),
			match: '/users',
			label: 'users',
			icon: Users,
			color: 'text-orange-400',
			activeBg: 'bg-orange-500/15',
		},
		{
			href: resolve('/groups'),
			match: '/groups',
			label: 'groups',
			icon: Network,
			color: 'text-amber-300',
			activeBg: 'bg-amber-400/15',
		},
		{
			href: resolve('/roles'),
			match: '/roles',
			label: 'roles',
			icon: Shield,
			color: 'text-red-400',
			activeBg: 'bg-red-500/15',
		},
		{
			href: resolve('/settings'),
			match: '/settings',
			label: 'settings',
			icon: Settings,
			color: 'text-zinc-300',
			activeBg: 'bg-zinc-800',
		},
	]

	function isActive(item: NavItem): boolean {
		if (item.match === '/dashboard') return page.url.pathname === '/dashboard'
		return page.url.pathname.startsWith(item.match)
	}
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
			{#each navItems as item (item.href)}
				{@const active = isActive(item)}
				<a
					href={resolve(item.match)}
					class="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors {active
						? `${item.activeBg} text-white`
						: 'text-zinc-300 hover:bg-zinc-900'}"
				>
					<item.icon class="h-4 w-4 shrink-0 {item.color}" />
					{item.label}
				</a>
			{/each}
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
			<div class="flex items-center gap-2">
				<img
					src="https://nokodo.net/media/images/logo_full.svg"
					alt="nokodo logo"
					class="h-5 w-auto object-contain"
				/>
				<span class="text-sm font-semibold text-zinc-100">console</span>
			</div>
		</div>
		<div class="flex flex-1 flex-col overflow-x-hidden overflow-y-auto bg-zinc-950">
			<div
				class="mx-auto flex w-full max-w-400 flex-1 flex-col px-4 py-6 sm:px-6 md:px-8 md:py-8"
			>
				{@render children()}
			</div>
		</div>
	</main>
</div>
