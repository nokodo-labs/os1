<script lang="ts">
	import { api } from '$lib/api'
	import SettingsCodeInterpreter from '$lib/components/settings/SettingsCodeInterpreter.svelte'
	import { Button } from '$lib/components/ui/button'
	import { getSettingsContext } from '$lib/settings/context.svelte'
	import { parseCommaList, toStringOrEmpty } from '$lib/settings/utils'
	import { asNumberOrUndefined } from '$lib/utils/settingsNumbers'
	import { RefreshCw, RotateCcw, Save } from '@lucide/svelte'

	type CodeInterpreterEngine = 'e2b'

	const ctx = getSettingsContext()

	let enabled = $state(true)
	let engine = $state<CodeInterpreterEngine>('e2b')
	let e2bApiKey = $state('')
	let e2bTemplate = $state('')
	let e2bAvailablePackages = $state('')
	let timeout = $state('')
	let maxFileDownloadMb = $state('')
	let maxOutputChars = $state('')
	let truncationLines = $state('')

	type Original = {
		enabled: boolean
		engine: CodeInterpreterEngine
		e2bApiKey: string
		e2bTemplate: string
		e2bAvailablePackages: string
		timeout: string
		maxFileDownloadMb: string
		maxOutputChars: string
		truncationLines: string
	}
	let original = $state<Original | null>(null)

	$effect(() => {
		const r = ctx.response
		if (!r) return
		const ci = r.data.code_interpreter
		enabled = ci?.enabled ?? true
		engine = (ci?.engine ?? 'e2b') as CodeInterpreterEngine
		e2bApiKey = ci?.e2b?.api_key ?? ''
		e2bTemplate = toStringOrEmpty(ci?.e2b?.template)
		e2bAvailablePackages = (ci?.e2b?.available_packages ?? []).join(', ')
		timeout = toStringOrEmpty(ci?.timeout)
		maxFileDownloadMb = toStringOrEmpty(ci?.max_file_download_mb)
		maxOutputChars = toStringOrEmpty(ci?.max_output_chars)
		truncationLines = toStringOrEmpty(ci?.truncation_lines)
		original = {
			enabled,
			engine,
			e2bApiKey,
			e2bTemplate,
			e2bAvailablePackages,
			timeout,
			maxFileDownloadMb,
			maxOutputChars,
			truncationLines,
		}
	})

	const hasChanges = $derived(
		original !== null &&
			(enabled !== original.enabled ||
				engine !== original.engine ||
				e2bApiKey !== original.e2bApiKey ||
				e2bTemplate !== original.e2bTemplate ||
				e2bAvailablePackages !== original.e2bAvailablePackages ||
				timeout !== original.timeout ||
				maxFileDownloadMb !== original.maxFileDownloadMb ||
				maxOutputChars !== original.maxOutputChars ||
				truncationLines !== original.truncationLines)
	)

	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state<string | null>(null)

	function resetDraft() {
		if (!original) return
		enabled = original.enabled
		engine = original.engine
		e2bApiKey = original.e2bApiKey
		e2bTemplate = original.e2bTemplate
		e2bAvailablePackages = original.e2bAvailablePackages
		timeout = original.timeout
		maxFileDownloadMb = original.maxFileDownloadMb
		maxOutputChars = original.maxOutputChars
		truncationLines = original.truncationLines
		saveError = null
		saveSuccess = null
	}

	async function save() {
		if (!ctx.response || !hasChanges || !original) return
		isSaving = true
		saveError = null
		saveSuccess = null
		try {
			const ciPatch: Record<string, unknown> = {}
			if (enabled !== original.enabled) ciPatch.enabled = enabled
			if (engine !== original.engine) ciPatch.engine = engine
			if (
				e2bApiKey !== original.e2bApiKey ||
				e2bTemplate !== original.e2bTemplate ||
				e2bAvailablePackages !== original.e2bAvailablePackages
			) {
				const e2bPatch: Record<string, unknown> = {}
				if (e2bApiKey !== original.e2bApiKey) e2bPatch.api_key = e2bApiKey || null
				if (e2bTemplate !== original.e2bTemplate)
					e2bPatch.template = e2bTemplate || undefined
				if (e2bAvailablePackages !== original.e2bAvailablePackages)
					e2bPatch.available_packages = parseCommaList(e2bAvailablePackages)
				ciPatch.e2b = e2bPatch
			}
			if (timeout !== original.timeout) ciPatch.timeout = asNumberOrUndefined(timeout)
			if (maxFileDownloadMb !== original.maxFileDownloadMb)
				ciPatch.max_file_download_mb = asNumberOrUndefined(maxFileDownloadMb)
			if (maxOutputChars !== original.maxOutputChars)
				ciPatch.max_output_chars = asNumberOrUndefined(maxOutputChars)
			if (truncationLines !== original.truncationLines)
				ciPatch.truncation_lines = asNumberOrUndefined(truncationLines)

			const result = await api.PATCH('/v1/settings', {
				body: {
					data: { code_interpreter: ciPatch },
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
			console.error('Failed to save code interpreter settings', e)
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

	<SettingsCodeInterpreter
		bind:enabled
		bind:engine
		bind:e2bApiKey
		bind:e2bTemplate
		bind:e2bAvailablePackages
		bind:timeout
		bind:maxFileDownloadMb
		bind:maxOutputChars
		bind:truncationLines
	/>
</div>
