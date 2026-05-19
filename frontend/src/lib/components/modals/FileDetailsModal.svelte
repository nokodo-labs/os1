<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { getApiOrigin } from '$lib/api/origin'
	import ImageLightbox from '$lib/components/chat/ImageLightbox.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowsPointingOut from '$lib/components/icons/ArrowsPointingOut.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import Eye from '$lib/components/icons/Eye.svelte'
	import MimeIcon from '$lib/components/icons/MimeIcon.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { resourceAccentStyle } from '$lib/resources/resourceVisuals'
	import { downloadFile, fetchAuthenticatedBlob, files } from '$lib/stores/files.svelte'
	import type { FileDetailsPayload, ResourceAccessPayload } from '$lib/stores/modals.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { canDeleteAccessLevel, resourceAccess } from '$lib/stores/resourceAccess.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { describeFileType, formatFileSize } from '$lib/utils/fileTypes'
	import { byAuthor, metadataLine } from '$lib/utils/resourceAuthors'

	interface Props {
		open: boolean
		payload: FileDetailsPayload | null
		onClose: () => void
	}

	let { open, payload, onClose }: Props = $props()

	const file = $derived(payload ? files.get(payload.fileId) : null)
	const fileAccessLevel = $derived(
		file ? resourceAccess.level('file', file.id, file.owner_id) : null
	)
	const canDeleteFile = $derived(canDeleteAccessLevel(fileAccessLevel))

	// fetch the file into cache if not already present (e.g. after page refresh)
	$effect(() => {
		if (open && payload?.fileId && !file) {
			void files.ensure(payload.fileId)
		}
	})

	$effect(() => {
		const accessKey = open && file ? `${file.id}:${resourceAccess.version}` : ''
		if (open && file && accessKey) void resourceAccess.ensure('file', file.id, file.owner_id)
	})

	const fileAuthorLabel = $derived(session.authorLabel(file?.owner_id))

	$effect(() => {
		if (open && file?.owner_id && file.owner_id !== session.currentUserId) {
			void session.ensureUsers([file.owner_id])
		}
	})

	let previewBlobUrl = $state<string | null>(null)
	let pdfPreviewBlobUrl = $state<string | null>(null)
	let previewOpen = $state(false)
	let imageDimensions = $state<{ w: number; h: number } | null>(null)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)
	let downloadError = $state<string | null>(null)
	let previewError = $state<string | null>(null)
	let isDownloading = $state(false)
	let isOpeningPreview = $state(false)
	const fileAccentStyle = resourceAccentStyle('file')

	const mimeType = $derived(file?.mime_type ?? '')
	const fileType = $derived(describeFileType(mimeType, file?.filename ?? null))
	const headerMeta = $derived(
		metadataLine(
			byAuthor(fileAuthorLabel),
			fileType,
			file?.size_bytes ? formatFileSize(file.size_bytes) : null
		)
	)
	const primaryType = $derived(mimeType.split('/')[0] || 'file')
	const isImage = $derived(primaryType === 'image')
	const isVideo = $derived(primaryType === 'video')
	const isAudio = $derived(primaryType === 'audio')
	const isPdf = $derived(mimeType.toLowerCase().split(';')[0]?.trim() === 'application/pdf')
	const hasPreview = $derived(isImage || isVideo || isAudio)

	const threadId = $derived.by(() => {
		const v = (file?.metadata_ as Record<string, unknown> | undefined)?.thread_id
		return typeof v === 'string' && v.startsWith('thread_') ? v : undefined
	})

	const genPrompt = $derived(
		(file?.metadata_ as Record<string, unknown> | undefined)?.prompt as string | undefined
	)
	const genAgentId = $derived(
		(file?.metadata_ as Record<string, unknown> | undefined)?.agent_id as string | undefined
	)
	const isGenerated = $derived(file?.source === 'generated')

	function formatDate(iso: string | null | undefined): string {
		if (!iso) return '-'
		return new Date(iso).toLocaleDateString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
		})
	}

	$effect(() => {
		if (!open || !file || !isImage) {
			if (previewBlobUrl) {
				URL.revokeObjectURL(previewBlobUrl)
				previewBlobUrl = null
			}
			imageDimensions = null
			return
		}
		let cancelled = false
		let currentUrl: string | null = null
		const url = `${getApiOrigin()}/v1/files/${file.id}/content`
		void fetchAuthenticatedBlob(url).then((blobUrl) => {
			if (cancelled) {
				URL.revokeObjectURL(blobUrl)
				return
			}
			currentUrl = blobUrl
			previewBlobUrl = blobUrl
			const img = new Image()
			img.onload = () => {
				if (!cancelled) imageDimensions = { w: img.naturalWidth, h: img.naturalHeight }
			}
			img.src = blobUrl
		})
		return () => {
			cancelled = true
			if (currentUrl) {
				URL.revokeObjectURL(currentUrl)
				if (previewBlobUrl === currentUrl) previewBlobUrl = null
			} else if (previewBlobUrl) {
				URL.revokeObjectURL(previewBlobUrl)
				previewBlobUrl = null
			}
		}
	})

	$effect(() => {
		if (!open || !file || !isPdf) {
			if (pdfPreviewBlobUrl) {
				URL.revokeObjectURL(pdfPreviewBlobUrl)
				pdfPreviewBlobUrl = null
			}
			isOpeningPreview = false
			return
		}
		let cancelled = false
		let currentUrl: string | null = null
		isOpeningPreview = true
		previewError = null
		const url = `${getApiOrigin()}/v1/files/${file.id}/content`
		void fetchAuthenticatedBlob(url, 'application/pdf')
			.then((blobUrl) => {
				if (cancelled) {
					URL.revokeObjectURL(blobUrl)
					return
				}
				currentUrl = blobUrl
				pdfPreviewBlobUrl = blobUrl
			})
			.catch(() => {
				if (!cancelled) previewError = 'preview failed'
			})
			.finally(() => {
				if (!cancelled) isOpeningPreview = false
			})
		return () => {
			cancelled = true
			if (currentUrl) {
				URL.revokeObjectURL(currentUrl)
				if (pdfPreviewBlobUrl === currentUrl) pdfPreviewBlobUrl = null
			}
		}
	})

	async function handleDownload(): Promise<void> {
		if (!file) return
		isDownloading = true
		downloadError = null
		try {
			await downloadFile(file.id, file.filename ?? undefined)
		} catch {
			downloadError = 'download failed'
		} finally {
			isDownloading = false
		}
	}

	function handlePdfPreviewClick(): void {
		if (!pdfPreviewBlobUrl) return
		window.open(pdfPreviewBlobUrl, '_blank', 'noopener,noreferrer')
	}

	async function handleDelete(): Promise<void> {
		if (!file || !canDeleteFile) return
		modals.open('confirm-delete', {
			title: 'delete file?',
			description: file.filename ?? 'this file will be permanently deleted.',
			onDelete: async () => {
				const ok = await files.remove(file.id)
				if (ok) onClose()
				return ok
			},
		})
	}

	function handleShare(): void {
		if (!file) return
		const accessPayload = {
			resourceType: 'file' as const,
			resourceId: file.id,
			title: file.filename ?? 'file',
		} satisfies ResourceAccessPayload
		modals.open('resource-access', accessPayload)
	}

	function handleClose(): void {
		if (isDeleting) return
		deleteError = null
		downloadError = null
		previewError = null
		onClose()
	}

	$effect(() => {
		if (!open) {
			isDeleting = false
			deleteError = null
			downloadError = null
			previewError = null
			isOpeningPreview = false
			previewOpen = false
		}
	})
</script>

<BaseModal
	{open}
	title={file?.filename ?? 'file details'}
	onClose={handleClose}
	widthClassName="max-w-2xl"
>
	{#if file}
		<div class="flex flex-col gap-5 overflow-hidden" style={fileAccentStyle}>
			<!-- preview area -->
			{#if isImage && previewBlobUrl}
				<button
					class="group relative -mx-6 -mt-1 h-64 cursor-zoom-in overflow-hidden rounded-xl bg-black/20"
					style="width: calc(100% + 3rem);"
					onclick={() => (previewOpen = true)}
					aria-label="open full preview"
				>
					<img
						src={previewBlobUrl}
						alt={file.filename ?? 'preview'}
						class="h-full w-full object-contain transition-transform duration-300 group-hover:scale-[1.02]"
						draggable="false"
					/>
					<div
						class="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-200 group-hover:opacity-100"
					>
						<div class="rounded-full bg-black/50 p-3">
							<ArrowsPointingOut class="size-5 text-white" />
						</div>
					</div>
				</button>
			{:else if isVideo && file}
				<!-- svelte-ignore a11y_media_has_caption -->
				<video
					class="-mx-6 -mt-1 max-h-64 rounded-xl bg-black/20 object-contain"
					style="width: calc(100% + 3rem);"
					controls
					src="{getApiOrigin()}/v1/files/{file.id}/content"
				></video>
			{:else if isAudio && file}
				<audio class="w-full" controls src="{getApiOrigin()}/v1/files/{file.id}/content"
				></audio>
			{/if}

			<section
				class="border-foreground/13 bg-background/70 flex min-w-0 items-center gap-4 rounded-[18px] border p-4 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-lg backdrop-saturate-[1.08]"
			>
				<div
					class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
				>
					<MimeIcon {mimeType} class="h-5 w-5" />
				</div>
				<div class="min-w-0 flex-1">
					<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
						file
					</p>
					<h3 class="text-foreground min-w-0 truncate text-lg font-semibold">
						{file.filename ?? 'untitled file'}
					</h3>
					{#if headerMeta}
						<p class="text-foreground/55 mt-0.5 min-w-0 truncate text-xs">
							{headerMeta}
						</p>
					{/if}
				</div>
			</section>

			<!-- action buttons -->
			<div class="flex flex-wrap items-center gap-2">
				{#if isPdf}
					{#if pdfPreviewBlobUrl}
						<button
							type="button"
							class="liquid-glass rounded-pill flex cursor-pointer items-center gap-1.5 px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97]"
							onclick={handlePdfPreviewClick}
						>
							<Eye class="size-4" />
							preview
						</button>
					{:else}
						<button
							class="liquid-glass rounded-pill flex cursor-pointer items-center gap-1.5 px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97] disabled:opacity-50"
							disabled
						>
							<Eye class="size-4" />
							{#if isOpeningPreview}<ShimmerText className="inline-block"
									>preparing</ShimmerText
								>{:else}preview{/if}
						</button>
					{/if}
				{/if}
				{#if hasPreview && isImage}
					<button
						class="liquid-glass rounded-pill flex cursor-pointer items-center gap-1.5 px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97]"
						onclick={() => (previewOpen = true)}
					>
						<ArrowsPointingOut class="size-4" />
						preview
					</button>
				{/if}
				<button
					class="liquid-glass rounded-pill flex cursor-pointer items-center gap-1.5 px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97] disabled:opacity-50"
					onclick={handleDownload}
					disabled={isDownloading}
				>
					<Download class="size-4" />
					{#if isDownloading}<ShimmerText className="inline-block"
							>downloading</ShimmerText
						>{:else}download{/if}
				</button>
				{#if file}
					<button
						class="liquid-glass rounded-pill flex cursor-pointer items-center gap-1.5 px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97]"
						onclick={handleShare}
					>
						<Share class="size-4" />
						share
					</button>
				{/if}
				{#if threadId}
					<button
						class="liquid-glass rounded-pill flex cursor-pointer items-center gap-1.5 px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97]"
						onclick={() => {
							handleClose()
							void goto(resolve(`/c/${threadId}`))
						}}
					>
						<ChatBubble class="size-4" />
						view thread
					</button>
				{/if}
				{#if canDeleteFile}
					<button
						class="liquid-glass rounded-pill ml-auto flex cursor-pointer items-center gap-1.5 px-4 py-2 text-sm text-red-400 transition-all hover:brightness-110 active:scale-[0.97] disabled:opacity-50"
						onclick={handleDelete}
						disabled={isDeleting}
					>
						<Trash class="size-4" />
						{#if isDeleting}<ShimmerText className="inline-block">deleting</ShimmerText
							>{:else}delete{/if}
					</button>
				{/if}
			</div>

			{#if deleteError}
				<p class="text-sm text-red-400">{deleteError}</p>
			{/if}
			{#if downloadError}
				<p class="text-sm text-red-400">{downloadError}</p>
			{/if}
			{#if previewError}
				<p class="text-sm text-red-400">{previewError}</p>
			{/if}

			<!-- metadata grid -->
			<div class="min-w-0 rounded-2xl border border-white/8 bg-white/4 p-4">
				<dl class="grid min-w-0 grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
					{#if fileAuthorLabel}
						<div class="min-w-0">
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								author
							</dt>
							<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
								{fileAuthorLabel}
							</dd>
						</div>
					{/if}
					<div class="min-w-0">
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">type</dt>
						<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
							{fileType}
						</dd>
					</div>
					<div class="min-w-0">
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">category</dt>
						<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
							{primaryType}
						</dd>
					</div>
					<div class="min-w-0">
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">size</dt>
						<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
							{formatFileSize(file.size_bytes)}
						</dd>
					</div>
					<div class="min-w-0">
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">source</dt>
						<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
							{file.source}
						</dd>
					</div>
					<div class="min-w-0">
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">created</dt>
						<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
							{formatDate(file.created_at)}
						</dd>
					</div>
					<div class="min-w-0">
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">updated</dt>
						<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
							{formatDate(file.updated_at)}
						</dd>
					</div>
					{#if file.status}
						<div class="min-w-0">
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								status
							</dt>
							<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
								{file.status}
							</dd>
						</div>
					{/if}
					{#if file.checksum_sha256}
						<div class="min-w-0 sm:col-span-2">
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								sha256
							</dt>
							<dd class="text-foreground/60 mt-0.5 font-mono text-xs break-all">
								{file.checksum_sha256}
							</dd>
						</div>
					{/if}
					{#if isGenerated && genPrompt}
						<div class="min-w-0 sm:col-span-2">
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								prompt
							</dt>
							<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
								{genPrompt}
							</dd>
						</div>
					{/if}
					{#if imageDimensions}
						<div class="min-w-0">
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								dimensions
							</dt>
							<dd class="text-foreground/80 mt-0.5 min-w-0 wrap-break-word">
								{imageDimensions.w} x {imageDimensions.h}
							</dd>
						</div>
					{/if}
					{#if isGenerated && genAgentId}
						<div class="min-w-0 sm:col-span-2">
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								agent
							</dt>
							<dd
								class="text-foreground/60 mt-0.5 min-w-0 font-mono text-xs break-all"
							>
								{genAgentId}
							</dd>
						</div>
					{/if}
				</dl>
			</div>
		</div>
	{:else if open}
		<div class="text-foreground/55 flex min-h-40 items-center justify-center text-sm">
			<ShimmerText>loading file</ShimmerText>
		</div>
	{/if}
</BaseModal>

{#if file && isImage && previewBlobUrl}
	<ImageLightbox
		open={previewOpen}
		src={previewBlobUrl}
		alt={file.filename ?? 'preview'}
		onClose={() => (previewOpen = false)}
	/>
{/if}
