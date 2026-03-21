<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { getApiOrigin } from '$lib/api/origin'
	import ImageLightbox from '$lib/components/chat/ImageLightbox.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowsPointingOut from '$lib/components/icons/ArrowsPointingOut.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import Download from '$lib/components/icons/Download.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { downloadFile, fetchAuthenticatedBlob, files } from '$lib/stores/files.svelte'
	import type { FileDetailsPayload, ResourceAccessPayload } from '$lib/stores/modals.svelte'
	import { modals } from '$lib/stores/modals.svelte'

	interface Props {
		open: boolean
		payload: FileDetailsPayload | null
		onClose: () => void
	}

	let { open, payload, onClose }: Props = $props()

	const file = $derived(payload ? files.get(payload.fileId) : null)

	// fetch the file into cache if not already present (e.g. after page refresh)
	$effect(() => {
		if (open && payload?.fileId && !file) {
			void files.ensure(payload.fileId)
		}
	})

	let previewBlobUrl = $state<string | null>(null)
	let previewOpen = $state(false)
	let imageDimensions = $state<{ w: number; h: number } | null>(null)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)
	let downloadError = $state<string | null>(null)
	let isDownloading = $state(false)

	const mimeType = $derived(file?.mime_type ?? '')
	const primaryType = $derived(mimeType.split('/')[0] ?? 'file')
	const isImage = $derived(primaryType === 'image')
	const isVideo = $derived(primaryType === 'video')
	const isAudio = $derived(primaryType === 'audio')
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

	function formatBytes(n: number | null | undefined): string {
		if (!n) return '—'
		if (n < 1024) return `${n} B`
		if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
		return `${(n / (1024 * 1024)).toFixed(1)} MB`
	}

	function formatDate(iso: string | null | undefined): string {
		if (!iso) return '—'
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
		const url = `${getApiOrigin()}/v1/files/${file.id}/content`
		void fetchAuthenticatedBlob(url).then((blobUrl) => {
			if (cancelled) return
			previewBlobUrl = blobUrl
			const img = new Image()
			img.onload = () => {
				if (!cancelled) imageDimensions = { w: img.naturalWidth, h: img.naturalHeight }
			}
			img.src = blobUrl
		})
		return () => {
			cancelled = true
			if (previewBlobUrl) {
				URL.revokeObjectURL(previewBlobUrl)
				previewBlobUrl = null
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

	async function handleDelete(): Promise<void> {
		if (!file) return
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
		onClose()
	}

	$effect(() => {
		if (!open) {
			isDeleting = false
			deleteError = null
			downloadError = null
			previewOpen = false
		}
	})
</script>

{#if file}
	<BaseModal
		{open}
		title={file.filename ?? 'file details'}
		onClose={handleClose}
		widthClassName="max-w-2xl"
	>
		<div class="flex flex-col gap-5 overflow-hidden">
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

			<!-- action buttons -->
			<div class="flex flex-wrap items-center gap-2">
				{#if hasPreview && isImage}
					<button
						class="liquid-glass flex cursor-pointer items-center gap-1.5 rounded-xl px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97]"
						onclick={() => (previewOpen = true)}
					>
						<ArrowsPointingOut class="size-4" />
						preview
					</button>
				{/if}
				<button
					class="liquid-glass flex cursor-pointer items-center gap-1.5 rounded-xl px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97] disabled:opacity-50"
					onclick={handleDownload}
					disabled={isDownloading}
				>
					<Download class="size-4" />
					{#if isDownloading}<ShimmerText className="inline-block"
							>downloading</ShimmerText
						>{:else}download{/if}
				</button>
				<button
					class="liquid-glass flex cursor-pointer items-center gap-1.5 rounded-xl px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97]"
					onclick={handleShare}
				>
					<Share class="size-4" />
					share
				</button>
				{#if threadId}
					<button
						class="liquid-glass flex cursor-pointer items-center gap-1.5 rounded-xl px-4 py-2 text-sm transition-all hover:brightness-110 active:scale-[0.97]"
						onclick={() => {
							handleClose()
							void goto(resolve(`/c/${threadId}`))
						}}
					>
						<ChatBubble class="size-4" />
						view thread
					</button>
				{/if}
				<button
					class="liquid-glass ml-auto flex cursor-pointer items-center gap-1.5 rounded-xl px-4 py-2 text-sm text-red-400 transition-all hover:brightness-110 active:scale-[0.97] disabled:opacity-50"
					onclick={handleDelete}
					disabled={isDeleting}
				>
					<Trash class="size-4" />
					{#if isDeleting}<ShimmerText className="inline-block">deleting</ShimmerText
						>{:else}delete{/if}
				</button>
			</div>

			{#if deleteError}
				<p class="text-sm text-red-400">{deleteError}</p>
			{/if}
			{#if downloadError}
				<p class="text-sm text-red-400">{downloadError}</p>
			{/if}

			<!-- metadata grid -->
			<div class="rounded-2xl border border-white/8 bg-white/4 p-4">
				<dl class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
					<div>
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">type</dt>
						<dd class="text-foreground/80 mt-0.5">{mimeType || '—'}</dd>
					</div>
					<div>
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">category</dt>
						<dd class="text-foreground/80 mt-0.5">{primaryType}</dd>
					</div>
					<div>
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">size</dt>
						<dd class="text-foreground/80 mt-0.5">{formatBytes(file.size_bytes)}</dd>
					</div>
					<div>
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">source</dt>
						<dd class="text-foreground/80 mt-0.5">{file.source}</dd>
					</div>
					<div>
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">created</dt>
						<dd class="text-foreground/80 mt-0.5">{formatDate(file.created_at)}</dd>
					</div>
					<div>
						<dt class="text-foreground/40 text-xs tracking-wide uppercase">updated</dt>
						<dd class="text-foreground/80 mt-0.5">{formatDate(file.updated_at)}</dd>
					</div>
					{#if file.status}
						<div>
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								status
							</dt>
							<dd class="text-foreground/80 mt-0.5">{file.status}</dd>
						</div>
					{/if}
					{#if file.checksum_sha256}
						<div class="col-span-2">
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								sha256
							</dt>
							<dd class="text-foreground/60 mt-0.5 font-mono text-xs break-all">
								{file.checksum_sha256}
							</dd>
						</div>
					{/if}
					{#if isGenerated && genPrompt}
						<div class="col-span-2">
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								prompt
							</dt>
							<dd class="text-foreground/80 mt-0.5">{genPrompt}</dd>
						</div>
					{/if}
					{#if imageDimensions}
						<div>
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								dimensions
							</dt>
							<dd class="text-foreground/80 mt-0.5">
								{imageDimensions.w} x {imageDimensions.h}
							</dd>
						</div>
					{/if}
					{#if isGenerated && genAgentId}
						<div class="col-span-2">
							<dt class="text-foreground/40 text-xs tracking-wide uppercase">
								agent
							</dt>
							<dd class="text-foreground/60 mt-0.5 font-mono text-xs">
								{genAgentId}
							</dd>
						</div>
					{/if}
				</dl>
			</div>
		</div>
	</BaseModal>

	{#if isImage && previewBlobUrl}
		<ImageLightbox
			open={previewOpen}
			src={previewBlobUrl}
			alt={file.filename ?? 'preview'}
			onClose={() => (previewOpen = false)}
		/>
	{/if}
{/if}
