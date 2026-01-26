<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import type { Component } from 'svelte'
	// icon imports for settings sections
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import Eye from '$lib/components/icons/Eye.svelte'
	import Lock from '$lib/components/icons/Lock.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Terminal from '$lib/components/icons/Terminal.svelte'
	import User from '$lib/components/icons/User.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'

	interface Props {
		selectedSection: string | null
		isMobile?: boolean
	}

	let { selectedSection, isMobile = false }: Props = $props()

	interface SettingsSection {
		id: string
		label: string
		icon: Component
		description: string
	}

	const sections: SettingsSection[] = [
		{
			id: 'account',
			label: 'account',
			icon: User,
			description: 'profile, email, and personal info',
		},
		{
			id: 'appearance',
			label: 'appearance',
			icon: Eye,
			description: 'theme, colors, and visual preferences',
		},
		{
			id: 'notifications',
			label: 'notifications',
			icon: AppNotification,
			description: 'alerts, sounds, and reminders',
		},
		{
			id: 'privacy',
			label: 'privacy & security',
			icon: Lock,
			description: 'data, permissions, and access control',
		},
		{
			id: 'ai',
			label: 'AI & models',
			icon: Sparkles,
			description: 'model preferences and behavior',
		},
		{
			id: 'advanced',
			label: 'advanced',
			icon: Wrench,
			description: 'developer tools and experimental features',
		},
		{
			id: 'debug',
			label: 'debug',
			icon: Terminal,
			description: 'debug-only UI toggles and diagnostics',
		},
	]

	function selectSection(sectionId: string) {
		void goto(resolve(`/settings/${sectionId}`), { keepFocus: true, noScroll: true })
	}

	function prefetchSection(sectionId: string): void {
		void sectionId
		// no-op for now; could prefetch section data if needed
	}
</script>

<div class="flex h-full min-h-0 flex-col gap-8">
	<header
		class="{isMobile
			? 'mt-0'
			: 'mt-7'} flex max-h-22 items-center justify-between gap-3 px-2 py-5 pb-6"
	>
		<div class="flex min-w-0 items-center gap-2">
			<Cog6 className="h-5 w-5 text-white/60" />
			<h2 class="min-w-0 truncate text-lg font-semibold tracking-wide text-white/85">
				settings
			</h2>
		</div>
	</header>

	<nav class="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
		<div class="space-y-1">
			{#each sections as section (section.id)}
				<div
					role="button"
					tabindex="0"
					class="group rounded-pill flex w-full cursor-pointer items-center gap-3 border border-transparent bg-transparent px-3 py-2.5 text-left transition-all duration-200 hover:border-white/10 hover:bg-white/5 {selectedSection ===
					section.id
						? 'shadow-[inset_0_2px_8px_rgba(255,255,255,0.1)]'
						: ''}"
					style={selectedSection === section.id
						? 'background-color: var(--accent-bg); border-color: var(--accent-border);'
						: ''}
					onmouseenter={() => prefetchSection(section.id)}
					onclick={() => selectSection(section.id)}
					onkeydown={(event) => {
						if (event.key !== 'Enter' && event.key !== ' ') return
						event.preventDefault()
						selectSection(section.id)
					}}
				>
					<span
						class="rounded-pill flex h-8 w-8 items-center justify-center bg-white/8 text-white/80"
					>
						<section.icon className="h-5 w-5" />
					</span>

					<span class="flex min-w-0 flex-1 items-center gap-2">
						<span class="min-w-0 truncate text-[0.95rem] font-medium text-white/90"
							>{section.label}</span
						>
					</span>

					<ChevronRight
						className="h-4 w-4 text-white/35 transition-colors group-hover:text-white/55"
					/>
				</div>
			{/each}
		</div>
	</nav>
</div>
