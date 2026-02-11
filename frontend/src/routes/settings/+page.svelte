<script lang="ts">
	import UserCircle from '$lib/components/icons/UserCircle.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import SettingsSidebar from '$lib/components/settings/SettingsSidebar.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { getUserInitials } from '$lib/utils'

	const displayName = $derived(session.currentUser?.display_name ?? 'user')
	const email = $derived(session.currentUser?.email ?? '')
</script>

{#if device.isMobile}
	<SettingsSidebar selectedSection={null} isMobile={true} />
{:else}
	<SettingsSectionLayout
		icon={UserCircle}
		label="account"
		description="manage your profile and personal information"
	>
		<div class="rounded-container flex items-center gap-4 bg-white/5 p-5">
			<div
				class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-lg font-semibold text-white uppercase"
				style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
			>
				{getUserInitials(displayName)}
			</div>
			<div class="min-w-0 flex-1">
				<div class="truncate text-sm font-semibold text-white/85">{displayName}</div>
				<div class="mt-0.5 truncate text-sm text-white/50">{email}</div>
			</div>
		</div>
	</SettingsSectionLayout>
{/if}
