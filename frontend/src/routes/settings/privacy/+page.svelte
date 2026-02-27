<script lang="ts">
	import { apiClient } from '$lib/api/client'
	import Lock from '$lib/components/icons/Lock.svelte'
	import { Switch } from '$lib/components/primitives'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { clearGeolocation, requestGeolocation } from '$lib/stores/device.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'
	import { session } from '$lib/stores/session.svelte'

	type Visibility = 'everyone' | 'friends' | 'private'

	const visibilityOptions: { value: Visibility; label: string }[] = [
		{ value: 'everyone', label: 'everyone' },
		{ value: 'friends', label: 'friends only' },
		{ value: 'private', label: 'only me' },
	]

	// current privacy settings from user object
	const privacy = $derived(
		(session.currentUser as Record<string, unknown> | null)?.privacy as
			| Record<string, string>
			| null
			| undefined
	)

	function getVisibility(field: string): Visibility {
		const val = privacy?.[field]
		if (val === 'everyone' || val === 'friends' || val === 'private') return val
		// defaults
		if (field === 'gender' || field === 'birth_date') return 'friends'
		return 'everyone'
	}

	async function setVisibility(field: string, value: Visibility): Promise<void> {
		const uid = session.currentUser?.id
		if (!uid) return
		const updated = { ...(privacy ?? {}), [field]: value }
		const { data } = await apiClient().PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: uid } },
			body: { privacy: updated },
		})
		if (data) session.currentUser = { ...data }
	}

	const privacyFields = [
		{
			key: 'online_status',
			label: 'online status',
			description: 'who can see when you are online',
		},
		{
			key: 'profile_picture',
			label: 'profile picture',
			description: 'who can see your profile picture',
		},
		{
			key: 'real_name',
			label: 'real name',
			description: 'who can see your display name',
		},
		{
			key: 'bio',
			label: 'bio',
			description: 'who can see your bio',
		},
		{
			key: 'gender',
			label: 'gender',
			description: 'who can see your gender',
		},
		{
			key: 'birth_date',
			label: 'age / birth date',
			description: 'who can see your age or birth date',
		},
		{
			key: 'allow_dms',
			label: 'direct messages',
			description: 'who can send you direct messages',
		},
		{
			key: 'allow_friend_requests',
			label: 'friend requests',
			description: 'who can send you friend requests',
		},
	] as const

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
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-white/85">profile visibility</div>
			<div class="mt-1 text-sm text-white/55">
				choose who can see each part of your profile.
			</div>
			<div class="mt-4 space-y-4">
				{#each privacyFields as field (field.key)}
					<div class="flex items-center justify-between gap-3">
						<div class="min-w-0 flex-1">
							<div class="text-sm text-white/70">{field.label}</div>
							<div class="text-xs text-white/50">{field.description}</div>
						</div>
						<select
							class="rounded-pill w-32 shrink-0 cursor-pointer appearance-none border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/80 scheme-dark transition-colors outline-none focus:border-white/20"
							value={getVisibility(field.key)}
							onchange={(e) =>
								void setVisibility(field.key, e.currentTarget.value as Visibility)}
						>
							{#each visibilityOptions as opt (opt.value)}
								<option value={opt.value} class="bg-neutral-900">{opt.label}</option
								>
							{/each}
						</select>
					</div>
				{/each}
			</div>
		</div>

		<!-- AI personalization -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-white/85">AI personalization</div>
			<div class="mt-1 text-sm text-white/55">
				control what information is shared with the AI to personalise your experience.
			</div>
			<div class="mt-4 space-y-4">
				<div class="flex items-center justify-between gap-3">
					<div>
						<div class="text-sm text-white/70">device information</div>
						<div class="text-xs text-white/50">
							share timezone, device type, and browser to help the AI personalise
							responses
						</div>
					</div>
					<Switch size="md" checked={useDeviceContext} onchange={setUseDeviceContext} />
				</div>
				<div class="flex items-center justify-between gap-3">
					<div>
						<div class="text-sm text-white/70">precise location</div>
						<div class="text-xs text-white/50">
							share your location with the AI for location-aware responses
						</div>
					</div>
					<Switch size="md" checked={useLocation} onchange={setUseLocation} />
				</div>
				<div class="flex items-center justify-between gap-3">
					<div>
						<div class="text-sm text-white/70">battery status</div>
						<div class="text-xs text-white/50">
							share charging state and battery level for context-aware responses
						</div>
					</div>
					<Switch size="md" checked={useBatteryStatus} onchange={setUseBatteryStatus} />
				</div>
			</div>
		</div>

		<!-- data collection -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-white/85">data collection</div>
			<div class="mt-1 text-sm text-white/55">
				control what data is collected and how it's used.
			</div>
			<div class="mt-4 space-y-3">
				<div class="flex items-center justify-between">
					<span class="text-sm text-white/70">analytics</span>
					<div class="h-6 w-12 rounded-full bg-white/20"></div>
				</div>
				<div class="flex items-center justify-between">
					<span class="text-sm text-white/70">crash reports</span>
					<div class="h-6 w-12 rounded-full bg-white/20"></div>
				</div>
			</div>
		</div>
	</div>
</SettingsSectionLayout>
