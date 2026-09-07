<script lang="ts">
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import { Switch } from '$lib/components/primitives'
	import { notificationsFields } from '$lib/components/settings/fields/notifications'
	import SettingsField from '$lib/components/settings/SettingsField.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import {
		pushNotifications,
		requestPushNotifications,
	} from '$lib/stores/pushNotifications.svelte'

	const pushEnabled = $derived(preferences.data.notifications.pushEnabled ?? true)
	const pushStatus = $derived.by(() => {
		if (!pushNotifications.supported) return 'not supported by this browser'
		if (!pushEnabled) return 'off for this account'
		if (pushNotifications.status === 'not_configured') return 'not configured on this server'
		if (pushNotifications.status === 'prompting') return 'waiting for browser permission'
		if (pushNotifications.status === 'subscribing') return 'connecting this device'
		if (pushNotifications.status === 'ready') return 'ready on this device'
		if (pushNotifications.status === 'failed') return pushNotifications.error ?? 'setup failed'
		if (pushNotifications.permission === 'granted') return 'browser permission granted'
		if (pushNotifications.permission === 'denied') return 'blocked in browser settings'
		return 'asks for browser permission on startup'
	})

	function setPushNotifications(enabled: boolean): void {
		void preferences.update('notifications', { pushEnabled: enabled })
		if (enabled) void requestPushNotifications()
	}
</script>

<SettingsSectionLayout
	icon={AppNotification}
	label="notifications"
	description="configure alerts, sounds, and reminder settings"
>
	<div class="space-y-4">
		<SettingsField field={notificationsFields.push}>
			{#snippet control(labelId)}
				<Switch
					size="md"
					checked={pushEnabled}
					onchange={setPushNotifications}
					ariaLabelledbyId={labelId}
				/>
			{/snippet}
			<div class="text-foreground/40 mt-2 text-xs">{pushStatus}</div>
		</SettingsField>
		<SettingsField field={notificationsFields.email}>
			{#snippet control(labelId)}
				<Switch
					size="md"
					checked={false}
					disabled
					tooltip="coming soon"
					ariaLabelledbyId={labelId}
				/>
			{/snippet}
			<div class="text-foreground/40 mt-2 text-xs">coming soon</div>
		</SettingsField>
	</div>
</SettingsSectionLayout>
