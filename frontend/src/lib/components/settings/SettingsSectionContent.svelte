<script lang="ts">
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import CommandLine from '$lib/components/icons/CommandLine.svelte'
	import Eye from '$lib/components/icons/Eye.svelte'
	import Lock from '$lib/components/icons/Lock.svelte'
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import UserCircle from '$lib/components/icons/UserCircle.svelte'
	import Wrench from '$lib/components/icons/Wrench.svelte'
	import AccessibilitySettings from '$lib/components/settings/sections/AccessibilitySettings.svelte'
	import AccountSettings from '$lib/components/settings/sections/AccountSettings.svelte'
	import AdvancedSettings from '$lib/components/settings/sections/AdvancedSettings.svelte'
	import AiSettings from '$lib/components/settings/sections/AiSettings.svelte'
	import AppearanceSettings from '$lib/components/settings/sections/AppearanceSettings.svelte'
	import DebugSettings from '$lib/components/settings/sections/DebugSettings.svelte'
	import NotificationsSettings from '$lib/components/settings/sections/NotificationsSettings.svelte'
	import PrivacySettings from '$lib/components/settings/sections/PrivacySettings.svelte'
	import { session } from '$lib/stores/session.svelte'
	import type { Component } from 'svelte'

	interface Props {
		section: string
	}

	let { section }: Props = $props()

	interface SettingsSection {
		id: string
		label: string
		icon: Component
		description: string
		content: Component
	}

	const sections: SettingsSection[] = [
		{
			id: 'account',
			label: 'account',
			icon: UserCircle,
			description: 'manage your profile, email, and personal information',
			content: AccountSettings,
		},
		{
			id: 'appearance',
			label: 'appearance',
			icon: Eye,
			description: 'customize theme, colors, and visual preferences',
			content: AppearanceSettings,
		},
		{
			id: 'notifications',
			label: 'notifications',
			icon: AppNotification,
			description: 'configure alerts, sounds, and reminder settings',
			content: NotificationsSettings,
		},
		{
			id: 'privacy',
			label: 'privacy & security',
			icon: Lock,
			description: 'control your data, permissions, and access settings',
			content: PrivacySettings,
		},
		{
			id: 'accessibility',
			label: 'accessibility',
			icon: SoundHigh,
			description: 'configure haptic feedback and assistive features',
			content: AccessibilitySettings,
		},
		{
			id: 'ai',
			label: 'AI & models',
			icon: Sparkles,
			description: 'customize AI behavior and model preferences',
			content: AiSettings,
		},
		{
			id: 'advanced',
			label: 'advanced',
			icon: Wrench,
			description: 'developer tools and experimental features',
			content: AdvancedSettings,
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
				content: DebugSettings,
			},
		]
	})

	const currentSection = $derived.by(
		() => effectiveSections.find((s) => s.id === section) ?? effectiveSections[0]
	)
	const CurrentIcon = $derived(currentSection.icon)
	const CurrentContent = $derived(currentSection.content)
</script>

<div class="min-h-0 w-full flex-1">
	<div class="mx-auto max-w-2xl py-6">
		<header class="mb-8 flex items-center gap-4">
			<div class="rounded-box flex h-12 w-12 items-center justify-center bg-white/10">
				<CurrentIcon variant="solid" class="h-6 w-6 text-white/80" />
			</div>
			<div class="min-w-0">
				<div class="text-2xl font-semibold text-white/90">{currentSection.label}</div>
				<div class="mt-1 text-sm text-white/60">{currentSection.description}</div>
			</div>
		</header>

		<CurrentContent />
	</div>
</div>
