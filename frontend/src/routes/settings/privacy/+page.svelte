<script lang="ts">
	import Lock from '$lib/components/icons/Lock.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
</script>

<SettingsSectionLayout
	icon={Lock}
	label="privacy & security"
	description="control your data, permissions, and access settings"
>
	<div class="space-y-4">
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
		<div class="rounded-container bg-white/5 p-5">
			<div class="text-sm font-semibold text-white/85">sessions</div>
			<div class="mt-1 text-sm text-white/55">
				manage active sessions and sign out of other devices.
			</div>
			<div class="rounded-pill mt-4 h-10 w-full bg-white/8"></div>
		</div>
	</div>
</SettingsSectionLayout>
