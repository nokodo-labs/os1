<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Clipboard from '$lib/components/icons/Clipboard.svelte'
	import DocumentArrowDown from '$lib/components/icons/DocumentArrowDown.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Link from '$lib/components/icons/Link.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'
	import type { ExportFormat, ShareTarget, ShareTargetId } from './resourceAccessModal'

	interface Props {
		panelClass: string
		quietButtonClass: string
		mailHref: string
		shareTargets: ShareTarget[]
		workingAction: string | null
		resourceType: ResourceAccessPayload['resourceType'] | undefined
		activeShareIconUrl: (target: ShareTarget) => string | undefined
		markShareIconFailed: (targetId: ShareTargetId, url: string) => void
		copyLink: () => void | Promise<void>
		nativeShare: () => void | Promise<void>
		copySnapshot: () => void | Promise<void>
		downloadSnapshot: (format: ExportFormat) => void | Promise<void>
		printSnapshotPdf: () => void | Promise<void>
		downloadOriginalFile: () => void | Promise<void>
	}

	let {
		panelClass,
		quietButtonClass,
		mailHref,
		shareTargets,
		workingAction,
		resourceType,
		activeShareIconUrl,
		markShareIconFailed,
		copyLink,
		nativeShare,
		copySnapshot,
		downloadSnapshot,
		printSnapshotPdf,
		downloadOriginalFile,
	}: Props = $props()
</script>

<div class="grid gap-3 md:grid-cols-2">
	<section class="{panelClass} p-5">
		<div class="mb-4 flex items-center gap-2">
			<Link class="text-foreground/50 h-4 w-4" />
			<p class="text-foreground/90 text-sm font-semibold">send link</p>
		</div>
		<div class="flex flex-wrap gap-2">
			<button class={quietButtonClass} onclick={copyLink}>
				<Clipboard class="h-4 w-4" />
				copy
			</button>
			<button class={quietButtonClass} onclick={nativeShare}>
				<Share class="h-4 w-4" />
				share
			</button>
			<a class={quietButtonClass} href={mailHref} rel="external noopener noreferrer">
				<DocumentArrowDown class="h-4 w-4" />
				mail
			</a>
			{#each shareTargets as target (target.id)}
				{@const iconUrl = activeShareIconUrl(target)}
				<a
					class={quietButtonClass}
					href={target.href}
					target="_blank"
					rel="external noopener noreferrer"
				>
					{#if iconUrl}
						<img
							src={iconUrl}
							alt=""
							class="h-4 w-4 object-contain"
							onerror={() => markShareIconFailed(target.id, iconUrl)}
						/>
					{:else}
						<GlobeAlt class="h-4 w-4" />
					{/if}
					{target.label}
				</a>
			{/each}
		</div>
	</section>

	<section class="{panelClass} p-5">
		<div class="mb-4 flex items-center gap-2">
			<Download class="text-foreground/50 h-4 w-4" />
			<p class="text-foreground/90 text-sm font-semibold">export</p>
		</div>
		<div class="flex flex-wrap gap-2">
			<button
				class={quietButtonClass}
				onclick={copySnapshot}
				disabled={workingAction !== null}
			>
				<Clipboard class="h-4 w-4" />
				{#if workingAction === 'copy-snapshot'}
					<ShimmerText className="inline-block">copying</ShimmerText>
				{:else}
					copy text
				{/if}
			</button>
			<button
				class={quietButtonClass}
				onclick={() => downloadSnapshot('md')}
				disabled={workingAction !== null}
			>
				<DocumentArrowDown class="h-4 w-4" />
				{#if workingAction === 'download-snapshot-md'}
					<ShimmerText className="inline-block">preparing</ShimmerText>
				{:else}
					markdown
				{/if}
			</button>
			<button
				class={quietButtonClass}
				onclick={() => downloadSnapshot('txt')}
				disabled={workingAction !== null}
			>
				<DocumentArrowDown class="h-4 w-4" />
				{#if workingAction === 'download-snapshot-txt'}
					<ShimmerText className="inline-block">preparing</ShimmerText>
				{:else}
					txt
				{/if}
			</button>
			<button
				class={quietButtonClass}
				onclick={() => downloadSnapshot('json')}
				disabled={workingAction !== null}
			>
				<DocumentArrowDown class="h-4 w-4" />
				{#if workingAction === 'download-snapshot-json'}
					<ShimmerText className="inline-block">preparing</ShimmerText>
				{:else}
					json
				{/if}
			</button>
			<button
				class={quietButtonClass}
				onclick={printSnapshotPdf}
				disabled={workingAction !== null}
			>
				<DocumentArrowDown class="h-4 w-4" />
				{#if workingAction === 'print-snapshot'}
					<ShimmerText className="inline-block">preparing</ShimmerText>
				{:else}
					pdf
				{/if}
			</button>
			{#if resourceType === 'file'}
				<button
					class={quietButtonClass}
					onclick={downloadOriginalFile}
					disabled={workingAction !== null}
				>
					<Download class="h-4 w-4" />
					{#if workingAction === 'download-file'}
						<ShimmerText className="inline-block">downloading</ShimmerText>
					{:else}
						file
					{/if}
				</button>
			{/if}
		</div>
	</section>
</div>
