<script lang="ts">
	import { browser } from '$app/environment'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import type { ShareResourcePayload } from '$lib/stores/modals.svelte'

	interface ShareResourceModalProps {
		open: boolean
		payload: ShareResourcePayload | null
		onClose: () => void
	}

	let { open, payload, onClose }: ShareResourceModalProps = $props()

	let copied = $state(false)

	const canNativeShare = $derived.by((): boolean => {
		if (!browser) return false
		return 'share' in navigator
	})

	const shareUrl = $derived.by((): string => {
		if (!browser) return ''
		if (!payload) return ''

		switch (payload.resource) {
			case 'thread': {
				const path = resolve(`/c/${payload.id}`)
				return new URL(path, page.url.origin).toString()
			}
		}
	})

	async function copyLink(): Promise<void> {
		if (!shareUrl) return
		await navigator.clipboard.writeText(shareUrl)
		copied = true
		window.setTimeout(() => {
			copied = false
		}, 1600)
	}

	async function shareNative(): Promise<void> {
		if (!shareUrl) return
		if (!canNativeShare) return
		const share = (
			navigator as Navigator & {
				share: (data: { title?: string; text?: string; url?: string }) => Promise<void>
			}
		).share
		await share({
			title: payload?.title ?? undefined,
			url: shareUrl,
		})
	}
</script>

<BaseModal
	{open}
	title="share"
	description="copy a link to share this"
	{onClose}
	widthClassName="max-w-sm"
>
	<div class="space-y-4">
		<div class="space-y-1">
			<div class="text-foreground/60 text-xs font-semibold uppercase">link</div>
			<div class="rounded-pill border-foreground/10 bg-foreground/5 border px-3 py-2">
				<div class="text-foreground/80 truncate text-sm" title={shareUrl}>{shareUrl}</div>
			</div>
		</div>

		<div class="flex items-center justify-end gap-2">
			{#if canNativeShare}
				<button
					type="button"
					class="rounded-pill border-foreground/10 text-foreground/80 hover:bg-foreground/5 border bg-transparent px-4 py-2 text-sm transition-colors duration-150"
					onclick={() => void shareNative()}
					disabled={!shareUrl}
				>
					share
				</button>
			{/if}
			<button
				type="button"
				class="rounded-pill border-foreground/10 bg-foreground/10 text-foreground/90 hover:bg-foreground/15 border px-4 py-2 text-sm transition-colors duration-150 disabled:opacity-60"
				onclick={() => void copyLink()}
				disabled={!shareUrl}
			>
				{copied ? 'copied' : 'copy link'}
			</button>
		</div>
	</div>
</BaseModal>
