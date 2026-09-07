<script lang="ts">
	import Clipboard from '$lib/components/icons/Clipboard.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Link from '$lib/components/icons/Link.svelte'
	import Mail from '$lib/components/icons/Mail.svelte'
	import MimeIcon from '$lib/components/icons/MimeIcon.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import { ActionTile } from '$lib/components/primitives'
	import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'
	import type { ExportOptionsBinding } from './exportOptions'
	import ShareExportOptions from './ShareExportOptions.svelte'
	import type { ExportFormat, ShareTarget } from './shareModal'

	interface Props {
		panelClass: string
		mailHref: string
		shareTargets: ShareTarget[]
		workingAction: string | null
		/** mime type of the shared file, when the resource is one */
		fileMimeType?: string | null
		resourceType: ResourceAccessPayload['resourceType'] | undefined
		/** shown inside the export panel when the resource type declares options */
		exportOptions?: ExportOptionsBinding
		copyLink: () => void | Promise<void>
		nativeShare: () => void | Promise<void>
		copySnapshot: () => void | Promise<void>
		downloadSnapshot: (format: ExportFormat) => void | Promise<void>
		printSnapshotPdf: () => void | Promise<void>
		downloadOriginalFile: () => void | Promise<void>
	}

	let {
		panelClass,
		mailHref,
		shareTargets,
		workingAction,
		fileMimeType = null,
		resourceType,
		exportOptions,
		copyLink,
		nativeShare,
		copySnapshot,
		downloadSnapshot,
		printSnapshotPdf,
		downloadOriginalFile,
	}: Props = $props()

	const SNAPSHOT_FORMATS: { format: ExportFormat; label: string; mimeType: string }[] = [
		{ format: 'md', label: 'markdown', mimeType: 'text/markdown' },
		{ format: 'txt', label: 'txt', mimeType: 'text/plain' },
		{ format: 'json', label: 'json', mimeType: 'application/json' },
	]

	const sectionClass = $derived(`${panelClass} flex min-w-0 flex-col gap-4 p-5`)
	const headingClass = 'text-foreground/90 flex items-center gap-2 text-sm font-semibold'
	// the tile row scrolls sideways like a share sheet rather than wrapping into a
	// tall stack, so both panels keep their shape from the widest split view down
	// to the narrowest phone.
	const rowClass =
		'-mx-1 flex snap-x gap-1 overflow-x-auto px-1 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden'
	const busy = $derived(workingAction !== null)

	function workingLabel(action: string, label: string): string | null {
		return workingAction === action ? label : null
	}
</script>

<div class="grid min-w-0 gap-3 md:grid-cols-2">
	<section class={sectionClass}>
		<p class={headingClass}>
			<Link class="text-foreground/50 h-4 w-4" />
			send link
		</p>
		<div class={rowClass}>
			<ActionTile label="copy" icon={Clipboard} onclick={copyLink} />
			<ActionTile label="share" icon={Share} onclick={nativeShare} />
			<ActionTile label="mail" icon={Mail} href={mailHref} newTab={false} />
			{#each shareTargets as target (target.id)}
				<ActionTile
					label={target.label}
					icon={target.icon ?? GlobeAlt}
					href={target.href}
				/>
			{/each}
		</div>
	</section>

	<section class={sectionClass}>
		<p class={headingClass}>
			<Download class="text-foreground/50 h-4 w-4" />
			export
		</p>
		<div class={rowClass}>
			<ActionTile
				label="copy text"
				icon={Clipboard}
				onclick={copySnapshot}
				disabled={busy}
				workingLabel={workingLabel('copy-snapshot', 'copying')}
			/>
			{#each SNAPSHOT_FORMATS as snapshot (snapshot.format)}
				<ActionTile
					label={snapshot.label}
					onclick={() => downloadSnapshot(snapshot.format)}
					disabled={busy}
					workingLabel={workingLabel(`download-snapshot-${snapshot.format}`, 'preparing')}
				>
					<MimeIcon mimeType={snapshot.mimeType} class="h-6 w-6" />
				</ActionTile>
			{/each}
			<ActionTile
				label="pdf"
				onclick={printSnapshotPdf}
				disabled={busy}
				workingLabel={workingLabel('print-snapshot', 'preparing')}
			>
				<MimeIcon mimeType="application/pdf" class="h-6 w-6" />
			</ActionTile>
			{#if resourceType === 'file'}
				<ActionTile
					label="file"
					onclick={downloadOriginalFile}
					disabled={busy}
					workingLabel={workingLabel('download-file', 'downloading')}
				>
					<MimeIcon mimeType={fileMimeType} class="h-6 w-6" />
				</ActionTile>
			{/if}
		</div>
		{#if exportOptions && exportOptions.definitions.length > 0}
			<ShareExportOptions binding={exportOptions} />
		{/if}
	</section>
</div>
