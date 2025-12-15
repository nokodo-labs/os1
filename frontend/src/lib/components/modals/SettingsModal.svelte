<script lang="ts">
	import AppModal from '$lib/components/common/AppModal.svelte'

	interface SettingsModalProps {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: SettingsModalProps = $props()
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
