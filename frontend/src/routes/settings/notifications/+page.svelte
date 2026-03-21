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
			<div class="text-foreground/85 text-sm font-semibold">push notifications</div>
			<div class="text-foreground/55 mt-1 text-sm">
				receive notifications for messages, reminders, and updates.
			</div>
			<div class="bg-foreground/20 mt-4 h-6 w-12 rounded-full"></div>
		</div>
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-foreground/85 text-sm font-semibold">email notifications</div>
			<div class="text-foreground/55 mt-1 text-sm">
				receive email digests and important alerts.
			</div>
			<div class="bg-foreground/10 mt-4 h-6 w-12 rounded-full"></div>
		</div>
	</div>
</SettingsSectionLayout>
