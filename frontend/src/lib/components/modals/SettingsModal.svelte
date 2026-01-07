<script lang="ts">
	import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
	import AppModal from '$lib/components/common/AppModal.svelte'
	import DebugMenu from '$lib/components/debug/DebugMenu.svelte'
	import type { createThemeContext } from '$lib/contexts/themeContext.svelte'
	import { currentUser } from '$lib/stores/session'

	type ThemeContext = ReturnType<typeof createThemeContext>

	interface SettingsModalProps {
		open: boolean
		onClose: () => void
		theme: ThemeContext
		currentBackground: BackgroundType
	}

	let { open, onClose, theme, currentBackground = $bindable() }: SettingsModalProps = $props()

	let showAdminDebug = $derived(Boolean($currentUser?.is_superuser))
</script>

<AppModal
	{open}
	title="settings"
	description="manage your preferences"
	{onClose}
	widthClassName="max-w-2xl"
>
	<div class="space-y-4">
		<div class="rounded-2xl bg-white/5 p-4">
			<div class="text-sm font-semibold text-white/85">appearance</div>
			<div class="mt-1 text-sm text-white/55">
				theme, motion, and visual preferences (mock)
			</div>
		</div>

		<div class="rounded-2xl bg-white/5 p-4">
			<div class="text-sm font-semibold text-white/85">account</div>
			<div class="mt-1 text-sm text-white/55">
				profile, security, and session controls (mock)
			</div>
		</div>

		{#if showAdminDebug}
			<div class="rounded-2xl bg-white/5 p-4">
				<div class="text-sm font-semibold text-white/85">debug controls</div>
				<div class="mt-1 text-sm text-white/55">admin-only debug settings</div>
				<div class="mt-3">
					<DebugMenu embedded {theme} bind:currentBackground />
				</div>
			</div>
		{/if}

		<div class="flex justify-end">
			<button
				type="button"
				class="rounded-2xl border-none bg-white/10 px-4 py-2 text-sm font-semibold text-white/85 transition-colors hover:bg-white/15"
				onclick={onClose}
			>
				close
			</button>
		</div>
	</div>
</AppModal>
