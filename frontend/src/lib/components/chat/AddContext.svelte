<script lang="ts">
	import { portal } from '$lib/actions/portal'
	import LiquidMetal from '$lib/components/effects/LiquidMetal.svelte'
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
	import { device } from '$lib/stores/device.svelte'
	import { cubicOut } from 'svelte/easing'
	import { fly } from 'svelte/transition'

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

	// drag-to-close
	let dragStartY = $state(0)
	let dragCurrentY = $state(0)
	let isDragging = $state(false)
	let dragPointerId = $state<number | null>(null)

	const dragOffsetY = $derived(isDragging ? Math.max(0, dragCurrentY - dragStartY) : 0)
	const DRAG_CLOSE_THRESHOLD = 80

	const hasInputContext = $derived(activeAttachments.length > 0 || isUploading)

	// -- drag handlers --

	function onHandlePointerDown(e: PointerEvent) {
		dragPointerId = e.pointerId
		dragStartY = e.clientY
		dragCurrentY = e.clientY
		isDragging = true
		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
	}

	function onHandlePointerMove(e: PointerEvent) {
		if (!isDragging || e.pointerId !== dragPointerId) return
		dragCurrentY = e.clientY
	}

	function onHandlePointerUp(e: PointerEvent) {
		if (!isDragging || e.pointerId !== dragPointerId) return
		const delta = e.clientY - dragStartY
		isDragging = false
		dragPointerId = null
		if (delta > DRAG_CLOSE_THRESHOLD) {
			onClose()
		}
	}

	function onHandlePointerCancel(e: PointerEvent) {
		if (e.pointerId !== dragPointerId) return
		isDragging = false
		dragPointerId = null
	}

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

	function handlePanelKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.stopPropagation()
			onClose()
		}
	}
</script>

{#if open}
	<div use:portal>
		<!-- backdrop -->
		<div
			class="fixed inset-0 z-40"
			role="button"
			tabindex="-1"
			aria-label="close add context panel"
			onclick={onClose}
			onkeydown={(e) => e.key === 'Escape' && onClose()}
		></div>

		<!-- peninsula panel -->
		<div
			role="dialog"
			aria-label="add context panel"
			aria-modal="true"
			tabindex="-1"
			class="pointer-events-none fixed right-0 bottom-0 z-50"
			style="left: var(--island-left, 0);"
			in:fly={{ y: 480, duration: 400, easing: cubicOut }}
			out:fly={{ y: 480, duration: 280, easing: cubicOut }}
			onkeydown={handlePanelKeyDown}
		>
			<div
				class="pointer-events-auto mx-auto w-full {device.isMobile ? '' : 'max-w-7xl'}"
				style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); transform: translateY({dragOffsetY}px); transition: {isDragging
					? 'none'
					: 'transform 0.2s ease'};"
			>
				<LiquidMetal
					cornerRadius={24}
					class="add-context-panel"
					style="border-radius: var(--radius-popup) var(--radius-popup) 0 0; overflow: hidden;"
				>
					<div class="relative z-10 pb-12">
						<!-- drag handle -->
						<div
							class="flex cursor-grab justify-center pt-3 pb-2 active:cursor-grabbing"
							role="button"
							tabindex="0"
							aria-label="drag to close"
							style="touch-action: none;"
							onpointerdown={onHandlePointerDown}
							onpointermove={onHandlePointerMove}
							onpointerup={onHandlePointerUp}
							onpointercancel={onHandlePointerCancel}
							onkeydown={(e) => e.key === 'Enter' && onClose()}
						>
							<div class="bg-foreground/25 h-1 w-10 rounded-full"></div>
						</div>

						{#if hasInputContext}
							<!-- input context section -->
							<div class="px-4 pt-3 pb-2">
								<div
									class="text-foreground/45 mb-3 text-[11px] font-semibold tracking-widest"
								>
									input context
								</div>

								<div class="space-y-1">
									{#each activeAttachments as attachment (attachment.id)}
										<div
											class="flex items-center gap-2.5 rounded-xl px-2 py-1.5"
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
												class="text-foreground/80 min-w-0 flex-1 truncate text-xs font-medium"
											>
												{attachment.filename}
											</span>

											<!-- native attachment toggle -->
											<Switch
												size="sm"
												checked={attachment.status === 'active'}
												onchange={() =>
													onToggleAttachmentStatus?.(
														attachment.id,
														attachment.status === 'active'
															? 'reference'
															: 'reveal'
													)}
											/>

											<!-- remove button (only for pending attachments) -->
											{#if attachment.isPending !== false}
												<button
													type="button"
													aria-label="remove attachment"
													class="text-foreground/35 hover:text-foreground/65 cursor-pointer transition-colors duration-150"
													onclick={() =>
														onRemoveAttachment?.(attachment.id)}
												>
													<XMark class="h-3.5 w-3.5" />
												</button>
											{/if}
										</div>
									{/each}

									{#if isUploading}
										<div
											class="flex items-center gap-2.5 rounded-xl px-2 py-1.5"
										>
											<span class="relative flex h-2.5 w-2.5 shrink-0">
												<span
													class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"
												></span>
												<span
													class="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-500"
												></span>
											</span>
											<ArrowUpTray
												class="text-foreground/50 h-3.5 w-3.5 shrink-0"
											/>
											<ShimmerText
												className="text-foreground/60 text-xs font-medium"
											>
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
							<div
								class="text-foreground/45 mb-3 text-[11px] font-semibold tracking-widest"
							>
								add to context
							</div>
							<div class="grid grid-cols-3 gap-2">
								<button
									type="button"
									class="context-action-btn"
									onclick={() => fileInput?.click()}
								>
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
							<div
								class="text-foreground/45 pt-1 pb-2 text-[11px] font-semibold tracking-widest"
							>
								actions
							</div>

							<div class="space-y-0.5">
								<!-- web search -->
								<button
									type="button"
									class="hover:bg-foreground/8 flex w-full items-center gap-3 rounded-xl px-2 py-2.5 transition-colors duration-150"
									onclick={() => onToggleWebSearch?.()}
								>
									<GlobeAlt class="text-foreground/60 h-5 w-5 shrink-0" />
									<span
										class="text-foreground/80 flex-1 text-left text-sm font-medium"
									>
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
									class="hover:bg-foreground/8 flex w-full items-center gap-3 rounded-xl px-2 py-2.5 transition-colors duration-150"
									onclick={() => onToggleThinkLonger?.()}
								>
									<Brain class="text-foreground/60 h-5 w-5 shrink-0" />
									<span
										class="text-foreground/80 flex-1 text-left text-sm font-medium"
									>
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
									class="hover:bg-foreground/8 flex w-full items-center gap-3 rounded-xl px-2 py-2.5 transition-colors duration-150"
									onclick={() => onToggleGenerateImage?.()}
								>
									<Sparkles class="text-foreground/60 h-5 w-5 shrink-0" />
									<span
										class="text-foreground/80 flex-1 text-left text-sm font-medium"
									>
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
					</div>
				</LiquidMetal>
			</div>
		</div>

		<!-- hidden file input -->
		<input
			bind:this={fileInput}
			type="file"
			class="hidden"
			multiple
			onchange={handleFileChange}
		/>
	</div>
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
