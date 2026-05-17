<script lang="ts">
	import ChatBottomPanel from '$lib/components/chat/ChatBottomPanel.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowUpTray from '$lib/components/icons/ArrowUpTray.svelte'
	import Brain from '$lib/components/icons/Brain.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import Film from '$lib/components/icons/Film.svelte'
	import Folder from '$lib/components/icons/Folder.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Photo from '$lib/components/icons/Photo.svelte'
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import ResourcePickerModal from '$lib/components/modals/ResourcePickerModal.svelte'
	import Switch from '$lib/components/primitives/ResolverSwitch.svelte'
	import type { ResourceItem } from '$lib/components/widgets/types'
	import { modals } from '$lib/stores/modals.svelte'

	// -- types --

	type AttachmentAction = 'reveal' | 'reference'

	interface NativeAttachment {
		id: string
		filename: string
		type: 'image' | 'audio' | 'video' | 'file'
		status: 'active' | 'reference'
		/** true for newly attached files (pending send); false for thread-level */
		isPending?: boolean
		/** local object URL for image/video preview */
		previewUrl?: string
		summary?: string
	}

	// -- props --

	interface Props {
		open: boolean
		onClose: () => void
		activeAttachments?: NativeAttachment[]
		isUploading?: boolean
		webSearchEnabled?: boolean
		thinkLongerEnabled?: boolean
		generateImageEnabled?: boolean
		onFileUpload?: (files: FileList) => void
		onAttachResource?: (resource: ResourceItem) => void
		onToggleWebSearch?: () => void
		onToggleThinkLonger?: () => void
		onToggleGenerateImage?: () => void
		onToggleAttachmentStatus?: (id: string, action: AttachmentAction) => void
		onRemoveAttachment?: (id: string) => void
	}

	let {
		open,
		onClose,
		activeAttachments = [],
		isUploading = false,
		webSearchEnabled = false,
		thinkLongerEnabled = false,
		generateImageEnabled = false,
		onFileUpload,
		onAttachResource,
		onToggleWebSearch,
		onToggleThinkLonger,
		onToggleGenerateImage,
		onToggleAttachmentStatus,
		onRemoveAttachment,
	}: Props = $props()

	// -- state --

	let fileInput = $state<HTMLInputElement | null>(null)
	let isResourcePickerOpen = $state(false)

	const hasInputContext = $derived(activeAttachments.length > 0 || isUploading)

	// -- other handlers --

	function handleFileChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement
		if (input.files && input.files.length > 0) {
			onFileUpload?.(input.files)
		}
		input.value = ''
	}

	function handleResourcePicked(resource: ResourceItem) {
		onAttachResource?.(resource)
		isResourcePickerOpen = false
	}
</script>

<ChatBottomPanel {open} {onClose} ariaLabel="add context panel">
	{#if hasInputContext}
		<!-- input context section -->
		<div class="max-h-[30dvh] overflow-y-auto px-4 pt-3 pb-2">
			<div class="text-foreground/45 mb-3 text-[11px] font-semibold tracking-widest">
				input context
			</div>

			<div class="space-y-1">
				{#each activeAttachments as attachment (attachment.id)}
					<div class="flex items-center gap-2.5 rounded-xl px-2 py-1.5">
						<!-- clickable area: dot + thumbnail + filename -->
						<button
							type="button"
							class="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5"
							onclick={() =>
								modals.open('file-details', {
									fileId: attachment.id,
								})}
						>
							<!-- status dot -->
							<span class="relative flex h-2.5 w-2.5 shrink-0">
								{#if attachment.status === 'active'}
									<span
										class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"
									></span>
									<span
										class="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-500"
									></span>
								{:else}
									<span
										class="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-400"
									></span>
								{/if}
							</span>

							<!-- thumbnail or type icon -->
							{#if attachment.previewUrl && (attachment.type === 'image' || attachment.type === 'video')}
								<img
									src={attachment.previewUrl}
									alt={attachment.filename}
									class="h-8 w-8 shrink-0 rounded-md object-cover"
									draggable="false"
								/>
							{:else}
								<span class="text-foreground/50 shrink-0">
									{#if attachment.type === 'image'}
										<Photo class="h-3.5 w-3.5" />
									{:else if attachment.type === 'audio'}
										<SoundHigh class="h-3.5 w-3.5" />
									{:else if attachment.type === 'video'}
										<Film class="h-3.5 w-3.5" />
									{:else}
										<Document class="h-3.5 w-3.5" />
									{/if}
								</span>
							{/if}

							<!-- filename -->
							<span
								class="text-foreground/80 min-w-0 flex-1 truncate text-left text-xs font-medium"
							>
								{attachment.filename}
							</span>
						</button>

						<!-- native attachment toggle -->
						<Switch
							size="sm"
							checked={attachment.status === 'active'}
							onchange={() =>
								onToggleAttachmentStatus?.(
									attachment.id,
									attachment.status === 'active' ? 'reference' : 'reveal'
								)}
						/>

						<!-- remove button (only for pending attachments) -->
						{#if attachment.isPending !== false}
							<button
								type="button"
								aria-label="remove attachment"
								class="text-foreground/35 hover:text-foreground/65 cursor-pointer transition-colors duration-150"
								onclick={() => onRemoveAttachment?.(attachment.id)}
							>
								<XMark class="h-3.5 w-3.5" />
							</button>
						{/if}
					</div>
				{/each}

				{#if isUploading}
					<div class="flex items-center gap-2.5 rounded-xl px-2 py-1.5">
						<span class="relative flex h-2.5 w-2.5 shrink-0">
							<span
								class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"
							></span>
							<span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-500"
							></span>
						</span>
						<ArrowUpTray class="text-foreground/50 h-3.5 w-3.5 shrink-0" />
						<ShimmerText className="text-foreground/60 text-xs font-medium">
							uploading
						</ShimmerText>
					</div>
				{/if}
			</div>
		</div>

		<div class="border-foreground/10 mx-4 my-1 border-t"></div>
	{/if}

	<!-- add to context -->
	<div class="px-4 pt-3 pb-2">
		<div class="text-foreground/45 mb-3 text-[11px] font-semibold tracking-widest">
			add to context
		</div>
		<div class="grid grid-cols-3 gap-2">
			<button type="button" class="context-action-btn" onclick={() => fileInput?.click()}>
				<span class="context-action-icon">
					<ArrowUpTray class="h-5 w-5" />
				</span>
				<span class="context-action-label">upload</span>
			</button>
			<button
				type="button"
				class="context-action-btn"
				onclick={() => {
					isResourcePickerOpen = true
				}}
			>
				<span class="context-action-icon">
					<Folder class="h-5 w-5" />
				</span>
				<span class="context-action-label">attach resource</span>
			</button>
		</div>
	</div>

	<div class="border-foreground/10 mx-4 border-t"></div>

	<!-- actions -->
	<div class="px-4 py-2">
		<div class="text-foreground/45 pt-1 pb-2 text-[11px] font-semibold tracking-widest">
			actions
		</div>

		<div class="space-y-0.5">
			<!-- web search -->
			<button
				type="button"
				class="rounded-pill hover:bg-foreground/8 flex w-full cursor-pointer items-center gap-3 px-3 py-2.5 transition-colors duration-150"
				onclick={() => onToggleWebSearch?.()}
			>
				<GlobeAlt class="text-foreground/60 h-5 w-5 shrink-0" />
				<span class="text-foreground/80 flex-1 text-left text-sm font-medium">
					search the web
				</span>
				<Switch
					size="sm"
					checked={webSearchEnabled}
					onchange={() => onToggleWebSearch?.()}
				/>
			</button>

			<!-- think longer -->
			<button
				type="button"
				class="rounded-pill hover:bg-foreground/8 flex w-full cursor-pointer items-center gap-3 px-3 py-2.5 transition-colors duration-150"
				onclick={() => onToggleThinkLonger?.()}
			>
				<Brain class="text-foreground/60 h-5 w-5 shrink-0" />
				<span class="text-foreground/80 flex-1 text-left text-sm font-medium">
					think longer
				</span>
				<Switch
					size="sm"
					checked={thinkLongerEnabled}
					onchange={() => onToggleThinkLonger?.()}
				/>
			</button>

			<!-- generate image -->
			<button
				type="button"
				class="rounded-pill hover:bg-foreground/8 flex w-full cursor-pointer items-center gap-3 px-3 py-2.5 transition-colors duration-150"
				onclick={() => onToggleGenerateImage?.()}
			>
				<Sparkles class="text-foreground/60 h-5 w-5 shrink-0" />
				<span class="text-foreground/80 flex-1 text-left text-sm font-medium">
					generate image
				</span>
				<Switch
					size="sm"
					checked={generateImageEnabled}
					onchange={() => onToggleGenerateImage?.()}
				/>
			</button>
		</div>
	</div>

	<!-- hidden file input -->
</ChatBottomPanel>

{#if open}
	<input bind:this={fileInput} type="file" class="hidden" multiple onchange={handleFileChange} />
{/if}

<ResourcePickerModal
	open={isResourcePickerOpen}
	onClose={() => (isResourcePickerOpen = false)}
	onSelect={handleResourcePicked}
	title="attach resource"
/>

<style>
	.context-action-btn {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.875rem 0.5rem;
		border-radius: var(--radius-container);
		background: color-mix(in oklch, var(--foreground) 14%, transparent);
		border: 1px solid color-mix(in oklch, var(--foreground) 10%, transparent);
		cursor: pointer;
		transition:
			background 0.15s ease,
			transform 0.1s ease;
		-webkit-tap-highlight-color: transparent;
	}

	.context-action-btn:hover {
		background: color-mix(in oklch, var(--foreground) 20%, transparent);
	}

	.context-action-btn:active {
		transform: scale(0.96);
		background: color-mix(in oklch, var(--foreground) 17%, transparent);
	}

	.context-action-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		color: color-mix(in oklch, var(--foreground) 72%, transparent);
	}

	.context-action-label {
		font-size: 0.72rem;
		font-weight: 500;
		color: color-mix(in oklch, var(--foreground) 65%, transparent);
		text-align: center;
		line-height: 1.2;
	}
</style>
