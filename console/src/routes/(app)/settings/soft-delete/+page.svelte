<script lang="ts">
	import { api } from '$lib/api'
	import SettingsSoftDelete from '$lib/components/settings/SettingsSoftDelete.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'

	const ctx = getSettingsContext()

	let threads = $state(true)
	let notes = $state(true)
	let files = $state(true)

	type Original = { threads: boolean; notes: boolean; files: boolean }
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const sd = r.data.soft_delete
		threads = sd?.threads ?? true
		notes = sd?.notes ?? true
		files = sd?.files ?? true
		original = { threads, notes, files }
	})

	const hasChanges = $derived(
		original !== null &&
			(threads !== original.threads || notes !== original.notes || files !== original.files)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		threads = original.threads
		notes = original.notes
		files = original.files
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const sdPatch: Record<string, unknown> = {}
			if (threads !== original.threads) sdPatch.threads = threads
			if (notes !== original.notes) sdPatch.notes = notes
			if (files !== original.files) sdPatch.files = files

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { soft_delete: sdPatch },
					expected_versions: ctx.response.versions ?? null,
				},
			})
			if (result.error) {
				if (result.response.status === 409) {
					saveError = 'settings were updated elsewhere. reload and try again.'
				} else {
					const detail = result.error?.detail
					saveError = typeof detail === 'string' ? detail : 'failed to save settings'
				}
				return
			}
			ctx.setFromResponse(result.data!)
			saveSuccess = 'saved'
		} catch (e) {
			console.error('Failed to save soft-delete settings', e)
			saveError = 'failed to save settings'
		} finally {
			isSaving = false
		}
	}
</script>

<div class="flex flex-col gap-4">
	<div class="flex items-center justify-between gap-2">
		<div>
			{#if saveError}
				<p class="text-sm text-red-400">{saveError}</p>
			{:else if saveSuccess}
				<p class="text-sm text-emerald-400">{saveSuccess}</p>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={ctx.fetchSettings}
				disabled={ctx.isFetching || isSaving}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				reload
			</Button>
			<Button
				variant="secondary"
				class="rounded-xl"
				onclick={resetDraft}
				disabled={!hasChanges || isSaving}
			>
				<RotateCcw class="mr-1.5 h-4 w-4" />
				reset
			</Button>
			<Button class="rounded-xl" onclick={save} disabled={!hasChanges || isSaving}>
				<Save class="mr-1.5 h-4 w-4" />
				{isSaving ? 'saving...' : 'save'}
			</Button>
		</div>
	</div>

	<SettingsSoftDelete bind:threads bind:notes bind:files />
</div>
