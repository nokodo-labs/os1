<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import UserCircle from '$lib/components/icons/UserCircle.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'

	const chrome = useSystemChrome()

	const handleBackToSettings = async () => {
		await goto(resolve('/settings'), { keepFocus: true, noScroll: true })
	}

	$effect(() => {
		if (device.isMobile) {
			chrome.setContextActions(mobileBackAction)
			return () => chrome.setContextActions(null)
		}
	})
</script>

{#snippet mobileBackAction()}
	<button
		type="button"
		class="rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
		onclick={handleBackToSettings}
		aria-label="back to settings"
	>
		<ChevronLeft class="h-5 w-5" strokeWidth="2" />
	</button>
{/snippet}

<SettingsSectionLayout
	icon={UserCircle}
	label="account"
	description="manage your profile, email, and personal information"
>
	<div class="space-y-4">
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">profile</div>
			<div class="mt-1 text-sm text-white/55">
				your display name, avatar, and bio. this information is visible to other users.
			</div>
			<div class="mt-4 flex items-center gap-4">
				<div class="h-16 w-16 rounded-full bg-white/10"></div>
				<div class="flex-1 space-y-2">
					<div class="h-4 w-32 rounded bg-white/10"></div>
					<div class="h-3 w-48 rounded bg-white/8"></div>
				</div>
			</div>
		</div>
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">email</div>
			<div class="mt-1 text-sm text-white/55">
				your email address for notifications and account recovery.
			</div>
			<div class="rounded-pill mt-3 h-10 w-full bg-white/8"></div>
		</div>
	</div>
</SettingsSectionLayout>
