<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import Cog6 from '$lib/components/icons/Cog6.svelte'
	import CommandLine from '$lib/components/icons/CommandLine.svelte'
	import Eye from '$lib/components/icons/Eye.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Lock from '$lib/components/icons/Lock.svelte'
	import ShieldCheck from '$lib/components/icons/ShieldCheck.svelte'
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
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
		| 'integrations'
		| 'advanced'
		| 'about'
		| 'debug'

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
			id: 'integrations',
			label: 'integrations',
			icon: GlobeAlt,
			description: 'imports and connected apps',
		},
		{
			id: 'advanced',
			label: 'advanced',
			icon: Wrench,
			description: 'data management and experiments',
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
		switch (sectionId) {
			case 'appearance':
				void goto(resolve('/settings/appearance'), { keepFocus: true, noScroll: true })
				break
			case 'notifications':
				void goto(resolve('/settings/notifications'), { keepFocus: true, noScroll: true })
				break
			case 'privacy':
				void goto(resolve('/settings/privacy'), { keepFocus: true, noScroll: true })
				break
			case 'accessibility':
				void goto(resolve('/settings/accessibility'), { keepFocus: true, noScroll: true })
				break
			case 'ai':
				void goto(resolve('/settings/ai'), { keepFocus: true, noScroll: true })
				break
			case 'security':
				void goto(resolve('/settings/security'), { keepFocus: true, noScroll: true })
				break
			case 'integrations':
				void goto(resolve('/settings/integrations'), { keepFocus: true, noScroll: true })
				break
			case 'advanced':
				void goto(resolve('/settings/advanced'), { keepFocus: true, noScroll: true })
				break
			case 'about':
				void goto(resolve('/settings/about'), { keepFocus: true, noScroll: true })
				break
			case 'debug':
				void goto(resolve('/settings/debug'), { keepFocus: true, noScroll: true })
				break
		}
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
			<Cog6 variant="solid" class="text-foreground/60 h-5 w-5" />
			<h2 class="text-foreground/85 min-w-0 truncate text-lg font-semibold tracking-wide">
				settings
			</h2>
		</div>
	</header>

	<nav class="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
		<div class="space-y-1">
			{#each effectiveSections as section (section.id)}
				<SidebarListItem
					selected={selectedSection === section.id}
					onSelect={() => selectSection(section.id)}
					onPrefetch={() => prefetchSection(section.id)}
					showChevron={true}
				>
					{#snippet leading()}
						<span
							class="rounded-pill text-foreground/80 flex h-8 w-8 items-center justify-center {rowIconBackground
								? 'bg-foreground/8'
								: ''}"
						>
							<section.icon variant="solid" class="h-5 w-5" />
						</span>
					{/snippet}
					<span class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
						>{section.label}</span
					>
				</SidebarListItem>
			{/each}
		</div>
	</nav>
</div>
