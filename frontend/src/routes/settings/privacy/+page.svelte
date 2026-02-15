<script lang="ts">
	import Lock from '$lib/components/icons/Lock.svelte'
	import { Switch } from '$lib/components/primitives'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { preferences } from '$lib/stores/preferences.svelte'

	const useLocation = $derived(preferences.data.privacy.useLocation ?? false)
	const useDeviceContext = $derived(preferences.data.privacy.useDeviceContext ?? true)

	function setUseLocation(enabled: boolean): void {
		void preferences.update('privacy', { useLocation: enabled })
	}

	function setUseDeviceContext(enabled: boolean): void {
		void preferences.update('privacy', { useDeviceContext: enabled })
	}
</script>

<SettingsSectionLayout
	icon={Lock}
	label="privacy & security"
	description="control your data, permissions, and access settings"
>
	<div class="space-y-4">
		<!-- personalization -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">personalization</div>
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
			</div>
		</div>

		<!-- data collection (placeholder, same as before) -->
		<div class="rounded-container bg-white/5 p-5">
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

		<!-- sessions (placeholder) -->
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">sessions</div>
			<div class="mt-1 text-sm text-white/55">
				manage active sessions and sign out of other devices.
			</div>
			<div class="rounded-pill mt-4 h-10 w-full bg-white/8"></div>
		</div>
	</div>
</SettingsSectionLayout>
