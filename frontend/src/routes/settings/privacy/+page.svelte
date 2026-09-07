<script lang="ts">
	import { api } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Lock from '$lib/components/icons/Lock.svelte'
	import Users from '$lib/components/icons/Users.svelte'
	import { DropdownSelect, Switch } from '$lib/components/primitives'
	import { privacyFields, privacyVisibilityFields } from '$lib/components/settings/fields/privacy'
	import SettingsField from '$lib/components/settings/SettingsField.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { clearGeolocation, requestGeolocation } from '$lib/stores/device.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { session } from '$lib/stores/session.svelte'

	type Visibility = 'everyone' | 'friends' | 'private'
	type PrivacySettings = components['schemas']['UserPrivacy']

	const visibilityOptions = [
		{ value: 'everyone', label: 'everyone', icon: GlobeAlt, iconVariant: 'solid' },
		{ value: 'friends', label: 'friends only', icon: Users, iconVariant: 'solid' },
		{ value: 'private', label: 'only me', icon: Lock, iconVariant: 'solid' },
	]

	// current privacy settings from user object
	const privacy = $derived(
		(session.currentUser as Record<string, unknown> | null)?.privacy as
			| Partial<PrivacySettings>
			| null
			| undefined
	)

	function getVisibility(field: keyof PrivacySettings): Visibility {
		const val = privacy?.[field]
		if (val === 'everyone' || val === 'friends' || val === 'private') return val
		// defaults
		if (
			field === 'online_status' ||
			field === 'real_name' ||
			field === 'gender' ||
			field === 'birth_date' ||
			field === 'allow_dms'
		)
			return 'friends'
		if (field === 'email') return 'private'
		return 'everyone'
	}

	async function setVisibility(field: keyof PrivacySettings, value: Visibility): Promise<void> {
		const uid = session.currentUser?.id
		if (!uid) return
		const updated = { ...(privacy ?? {}), [field]: value } as PrivacySettings
		const { data } = await api.PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: uid } },
			body: { privacy: updated },
		})
		if (data) session.currentUser = { ...data }
	}

	const findByEmail = $derived(session.currentUser?.find_by_email ?? false)

	async function setFindByEmail(enabled: boolean): Promise<void> {
		const uid = session.currentUser?.id
		if (!uid) return
		const { data } = await api.PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: uid } },
			body: { find_by_email: enabled },
		})
		if (data) session.currentUser = { ...data }
	}

	// AI personalization toggles
	const useLocation = $derived(preferences.data.privacy.useLocation ?? false)
	const useDeviceContext = $derived(preferences.data.privacy.useDeviceContext ?? true)
	const useBatteryStatus = $derived(preferences.data.privacy.useBatteryStatus ?? false)

	function setUseLocation(enabled: boolean): void {
		void preferences.update('privacy', { useLocation: enabled })
		if (enabled) {
			requestGeolocation()
		} else {
			clearGeolocation()
		}
	}

	function setUseDeviceContext(enabled: boolean): void {
		void preferences.update('privacy', { useDeviceContext: enabled })
	}

	function setUseBatteryStatus(enabled: boolean): void {
		void preferences.update('privacy', { useBatteryStatus: enabled })
	}
</script>

<SettingsSectionLayout
	icon={Lock}
	label="privacy"
	description="control who can see your information"
>
	<div class="space-y-4">
		<!-- profile privacy controls -->
		<SettingsField field={privacyFields.profileVisibility}>
			<div class="mt-4 space-y-4">
				<SettingsField field={privacyFields.emailSearch} surface="plain" size="row">
					{#snippet control(labelId)}
						<Switch
							size="sm"
							checked={findByEmail}
							onchange={setFindByEmail}
							ariaLabelledbyId={labelId}
						/>
					{/snippet}
				</SettingsField>
				{#each privacyVisibilityFields as row (row.key)}
					<SettingsField field={row.field} surface="plain" size="row">
						{#snippet control()}
							<DropdownSelect
								options={visibilityOptions}
								value={getVisibility(row.key)}
								onchange={(value) =>
									void setVisibility(row.key, value as Visibility)}
								ariaLabel={`${row.field.label} visibility`}
								class="w-36 shrink-0"
								buttonClass="px-3 py-1.5 text-xs"
							/>
						{/snippet}
					</SettingsField>
				{/each}
			</div>
		</SettingsField>

		<!-- AI personalization -->
		<SettingsField field={privacyFields.aiPersonalization}>
			<div class="mt-4 space-y-4">
				<SettingsField field={privacyFields.deviceInformation} surface="plain" size="row">
					{#snippet control(labelId)}
						<Switch
							size="md"
							checked={useDeviceContext}
							onchange={setUseDeviceContext}
							ariaLabelledbyId={labelId}
						/>
					{/snippet}
				</SettingsField>
				<SettingsField field={privacyFields.preciseLocation} surface="plain" size="row">
					{#snippet control(labelId)}
						<Switch
							size="md"
							checked={useLocation}
							onchange={setUseLocation}
							ariaLabelledbyId={labelId}
						/>
					{/snippet}
				</SettingsField>
				<SettingsField field={privacyFields.batteryStatus} surface="plain" size="row">
					{#snippet control(labelId)}
						<Switch
							size="md"
							checked={useBatteryStatus}
							onchange={setUseBatteryStatus}
							ariaLabelledbyId={labelId}
						/>
					{/snippet}
				</SettingsField>
			</div>
		</SettingsField>

		<!-- data collection -->
		<SettingsField field={privacyFields.dataCollection}>
			<div class="mt-4 space-y-3">
				<SettingsField field={privacyFields.analytics} surface="plain" size="row">
					{#snippet control()}
						<div class="bg-foreground/20 h-6 w-12 rounded-full"></div>
					{/snippet}
				</SettingsField>
				<SettingsField field={privacyFields.crashReports} surface="plain" size="row">
					{#snippet control()}
						<div class="bg-foreground/20 h-6 w-12 rounded-full"></div>
					{/snippet}
				</SettingsField>
			</div>
		</SettingsField>
	</div>
</SettingsSectionLayout>
