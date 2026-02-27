<script lang="ts">
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
</script>

<SettingsSectionLayout
	icon={AppNotification}
	label="notifications"
	description="configure alerts, sounds, and reminder settings"
>
	<div class="space-y-4">
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-white/85">push notifications</div>
			<div class="mt-1 text-sm text-white/55">
				receive notifications for messages, reminders, and updates.
			</div>
			<div class="mt-4 h-6 w-12 rounded-full bg-white/20"></div>
		</div>
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-white/85">email notifications</div>
			<div class="mt-1 text-sm text-white/55">
				receive email digests and important alerts.
			</div>
			<div class="mt-4 h-6 w-12 rounded-full bg-white/10"></div>
		</div>
	</div>
</SettingsSectionLayout>
