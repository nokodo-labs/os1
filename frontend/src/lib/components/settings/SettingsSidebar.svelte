<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import CommandLine from '$lib/components/icons/CommandLine.svelte'
	import Eye from '$lib/components/icons/Eye.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Lock from '$lib/components/icons/Lock.svelte'
	import ShieldCheck from '$lib/components/icons/ShieldCheck.svelte'
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'
	import { session } from '$lib/stores/session.svelte'
	import type { Component } from 'svelte'

	interface Props {
		selectedSection: string | null
		isMobile?: boolean
		rowIconBackground?: boolean
	}

	let { selectedSection, isMobile = false, rowIconBackground = false }: Props = $props()

	interface SettingsSection {
		id: SettingsSectionId
		label: string
		icon: Component
		description: string
	}

	type SettingsSectionId =
		| 'appearance'
		| 'notifications'
		| 'privacy'
		| 'accessibility'
		| 'ai'
		| 'security'
		| 'advanced'
		| 'about'
		| 'debug'

	type SettingsRouteId =
		| '/settings/appearance'
		| '/settings/notifications'
		| '/settings/privacy'
		| '/settings/accessibility'
		| '/settings/ai'
		| '/settings/security'
		| '/settings/advanced'
		| '/settings/about'
		| '/settings/debug'

	const settingsRouteBySection = {
		appearance: '/settings/appearance',
		notifications: '/settings/notifications',
		privacy: '/settings/privacy',
		accessibility: '/settings/accessibility',
		ai: '/settings/ai',
		security: '/settings/security',
		advanced: '/settings/advanced',
		about: '/settings/about',
		debug: '/settings/debug',
	} as const satisfies Record<SettingsSectionId, SettingsRouteId>

	const sections: SettingsSection[] = [
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
			label: 'privacy',
			icon: Lock,
			description: 'data collection and sharing settings',
		},
		{
			id: 'accessibility',
			label: 'accessibility',
			icon: SoundHigh,
			description: 'haptic feedback and assistive features',
		},
		{
			id: 'ai',
			label: 'AI',
			icon: Sparkles,
			description: 'model preferences and behavior',
		},
		{
			id: 'security',
			label: 'security',
			icon: ShieldCheck,
			description: 'passwords, email, and authentication',
		},
		{
			id: 'advanced',
			label: 'advanced',
			icon: Wrench,
			description: 'data management and imports',
		},
		{
			id: 'about',
			label: 'about',
			icon: InfoCircle,
			description: 'app info, credits, and links',
		},
	]

	const showAdminDebug = $derived(Boolean(session.currentUser?.is_superuser))

	const effectiveSections = $derived.by((): SettingsSection[] => {
		if (!showAdminDebug) return sections
		return [
			...sections,
			{
				id: 'debug',
				label: 'debug',
				icon: CommandLine,
				description: 'debug-only UI toggles and diagnostics',
			},
		]
	})

	function selectSection(sectionId: SettingsSectionId) {
		void goto(resolve(settingsRouteBySection[sectionId]), { keepFocus: true, noScroll: true })
	}

	function prefetchSection(sectionId: string): void {
		void sectionId
		// no-op for now; could prefetch section data if needed
	}
</script>

<div class="flex h-full min-h-0 flex-col" style="gap: var(--spacing-header-content);">
	<header
		class="{isMobile
			? 'mt-0'
			: 'mt-7'} flex max-h-22 items-center justify-between gap-3 px-2 py-5 pb-6"
	>
		<div class="flex min-w-0 items-center gap-2">
			<Cog6 variant="solid" class="h-5 w-5 text-white/60" />
			<h2 class="min-w-0 truncate text-lg font-semibold tracking-wide text-white/85">
				settings
			</h2>
		</div>
	</header>

	<nav class="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
		<div class="space-y-1">
			{#each effectiveSections as section (section.id)}
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
						class="rounded-pill flex h-8 w-8 items-center justify-center text-white/80 {rowIconBackground
							? 'bg-white/8'
							: ''}"
					>
						<section.icon variant="solid" class="h-5 w-5" />
					</span>

					<span class="flex min-w-0 flex-1 items-center gap-2">
						<span class="min-w-0 truncate text-[0.95rem] font-medium text-white/90"
							>{section.label}</span
						>
					</span>

					<ChevronRight
						class="h-4 w-4 text-white/50 transition-colors group-hover:text-white/55"
					/>
				</div>
			{/each}
		</div>
	</nav>
</div>
