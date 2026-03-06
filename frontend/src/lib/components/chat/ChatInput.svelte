<script lang="ts">
	import {
		categorizeMediaType,
		type PendingAttachment,
		revokePreviewUrls,
		type RunModifiers,
		uploadFile,
	} from '$lib/chat/attachments'
	import type { ThreadAttachment } from '$lib/chat/types'
	import AddContext from '$lib/components/chat/AddContext.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Stop from '$lib/components/icons/Stop.svelte'
	import type { ResourceItem } from '$lib/components/widgets/types'
	import { device } from '$lib/stores/device.svelte'
	import { files } from '$lib/stores/files.svelte'
	import { tick } from 'svelte'

	interface ChatInputProps {
		value?: string
		placeholder?: string
		disabled?: boolean
		isGenerating?: boolean
		focusToken?: number
		threadAttachments?: ThreadAttachment[]
		onSubmit?: (message: string, modifiers?: RunModifiers) => void
		onStop?: () => void
		onKeyDown?: (event: KeyboardEvent) => boolean | void
		onToggleAttachmentStatus?: (fileId: string, action: 'reveal' | 'reference') => void
		viewTransitionName?: string
	}

	let {
		value = $bindable(''),
		placeholder = 'send a message',
		disabled = false,
		isGenerating = false,
		focusToken,
		threadAttachments = [],
		onSubmit,
		onStop,
		onKeyDown,
		onToggleAttachmentStatus,
		viewTransitionName,
	}: ChatInputProps = $props()

	let textarea: HTMLTextAreaElement
	let formEl = $state<HTMLFormElement | null>(null)
	let isComposing = $state(false)
	let isAddContextOpen = $state(false)
	let isMultiLine = $state(false)

	// attachment + modifier state
	let webSearchEnabled = $state(false)
	let thinkLongerEnabled = $state(false)
	let generateImageEnabled = $state(false)
	let pendingAttachments = $state<PendingAttachment[]>([])
	let isUploading = $state(false)

	// combine pending uploads and thread-level attachments for the tray
	const pendingAsNative = $derived(
		pendingAttachments.map((att) => ({
			id: att.fileId,
			filename: att.filename,
			type: att.category as 'image' | 'audio' | 'video' | 'file',
			status: 'active' as const,
			isPending: true,
			previewUrl: att.previewUrl,
		}))
	)
	const threadAsNative = $derived(
		threadAttachments.map((att) => ({
			id: att.fileId,
			filename: att.filename ?? att.fileId,
			type: att.category,
			status: att.status,
			isPending: false,
		}))
	)
	const activeAttachments = $derived([...pendingAsNative, ...threadAsNative])

	// track whether context is active for the badge indicator
	const hasContextActive = $derived(
		pendingAttachments.length > 0 ||
			threadAttachments.length > 0 ||
			webSearchEnabled ||
			thinkLongerEnabled ||
			generateImageEnabled
	)

	$effect(() => {
		if (!textarea) return
		if (!focusToken) return
		if (disabled) return
		requestAnimationFrame(() => {
			const target = textarea
			if (!target) return
			target.focus()
			const end = target.value.length
			target.setSelectionRange(end, end)
		})
	})

	// trigger resize when value is changed externally (e.g. quote insertion)
	$effect(() => {
		void value
		tick().then(resize)
	})

	function closeAddContext() {
		isAddContextOpen = false
	}

	function toggleAddContext() {
		isAddContextOpen = !isAddContextOpen
	}

	async function handleFileUpload(files: FileList) {
		isUploading = true
		try {
			const uploads = await Promise.all(Array.from(files).map(uploadFile))
			pendingAttachments = [...pendingAttachments, ...uploads]
		} catch (e) {
			console.error('file upload failed:', e)
		} finally {
			isUploading = false
		}
	}

	function removeAttachment(fileId: string) {
		const att = pendingAttachments.find((a) => a.fileId === fileId)
		if (att?.previewUrl) URL.revokeObjectURL(att.previewUrl)
		pendingAttachments = pendingAttachments.filter((a) => a.fileId !== fileId)
		// only delete the backend file if it was uploaded in this chat session
		if (att?.source === 'upload') {
			void files.remove(fileId)
		}
	}

	function handleAttachResource(resource: ResourceItem) {
		if (resource.type !== 'file') return
		if (pendingAttachments.some((a) => a.fileId === resource.id)) return
		const mime = (resource.meta?.mime_type as string) ?? 'application/octet-stream'
		pendingAttachments = [
			...pendingAttachments,
			{
				fileId: resource.id,
				filename: resource.title,
				mediaType: mime,
				category: categorizeMediaType(mime),
				previewUrl: files.getThumbnailUrl(resource.id),
				source: 'resource',
			},
		]
	}

	function resize() {
		if (!textarea) return
		textarea.style.height = 'auto'
		const newHeight = Math.min(textarea.scrollHeight, 200)
		textarea.style.height = `${newHeight}px`
		isMultiLine = textarea.scrollHeight > 32
	}

	function handleInput() {
		resize()
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (onKeyDown?.(event)) return
		// on touch devices, enter inserts a newline (users need it for multiline).
		// on desktop, bare enter sends the message.
		if (event.key === 'Enter' && !event.shiftKey && !isComposing && !device.isTouch) {
			event.preventDefault()
			handleSubmit()
		}
	}

	function handleSubmit() {
		const hasAttachments = pendingAttachments.length > 0
		if ((!value.trim() && !hasAttachments) || disabled || !onSubmit) return

		const modifiers: RunModifiers = {
			webSearch: webSearchEnabled,
			thinkLonger: thinkLongerEnabled,
			generateImage: generateImageEnabled,
			attachments: [...pendingAttachments],
		}

		const hasModifiers =
			modifiers.webSearch ||
			modifiers.thinkLonger ||
			modifiers.generateImage ||
			modifiers.attachments.length > 0

		onSubmit(value, hasModifiers ? modifiers : undefined)

		// reset state after send
		value = ''
		isMultiLine = false
		revokePreviewUrls(pendingAttachments)
		pendingAttachments = []
		webSearchEnabled = false
		thinkLongerEnabled = false
		generateImageEnabled = false
		if (textarea) {
			textarea.style.height = 'auto'
		}
	}

	function handleCompositionStart() {
		isComposing = true
	}

	function handleCompositionEnd() {
		isComposing = false
	}

	/**
	 * form submit handler. on mobile, the virtual keyboard may dismiss when
	 * the user taps the send button (due to blur). re-focus the textarea
	 * after the submit to keep the keyboard open.
	 */
	async function handleFormSubmit(event: SubmitEvent) {
		event.preventDefault()
		if (device.virtualKeyboardOpen) {
			await tick()
			textarea.focus()
		}
		handleSubmit()
	}
</script>

<form class="w-full" bind:this={formEl} onsubmit={handleFormSubmit}>
	<div
		class="liquid-glass chat-input relative rounded-3xl w-full transition-all duration-300"
		data-chat-input
		style={viewTransitionName ? `view-transition-name: ${viewTransitionName};` : undefined}
	>
		<div class="relative z-10 px-1 py-1">
			<div
				class="flex px-1 py-1"
				class:items-center={!isMultiLine}
				class:items-end={isMultiLine}
			>
				<div
					class="flex shrink-0"
					class:items-center={!isMultiLine}
					class:items-end={isMultiLine}
				>
					<button
						type="button"
						aria-label="add context"
						aria-haspopup="dialog"
						aria-expanded={isAddContextOpen}
						class="text-foreground/65 hover:text-foreground relative flex cursor-pointer items-center justify-center bg-transparent p-0 transition-colors duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
						{disabled}
						onclick={toggleAddContext}
					>
						<Plus class="h-8 w-8" strokeWidth="2" />
						{#if hasContextActive}
							<span
								class="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full"
								style="background-color: var(--accent-primary);"
							></span>
						{/if}
					</button>
				</div>

				<div class="flex flex-1 px-1 items-center">
					<textarea
						bind:this={textarea}
						bind:value
						{placeholder}
						{disabled}
						oninput={handleInput}
						onkeydown={handleKeyDown}
						oncompositionstart={handleCompositionStart}
						oncompositionend={handleCompositionEnd}
						rows="1"
						class="scrollbar-thin scrollbar-track-transparent scrollbar-thumb-foreground/20 hover:scrollbar-thumb-foreground/30 text-foreground/96 placeholder:text-foreground/40 m-0 max-h-96 min-h-6 w-full resize-none overflow-y-auto border-0 bg-transparent px-1 py-0 font-[inherit] text-[0.9375rem] leading-6 outline-none"
					></textarea>
				</div>

				<div
					class="flex shrink-0 space-x-1"
					class:items-center={!isMultiLine}
					class:items-end={isMultiLine}
				>
					{#if isGenerating}
						<button
							type="button"
							aria-label="stop generating"
							class="rounded-circle bg-foreground text-background hover:bg-foreground/90 flex h-8 w-8 cursor-pointer items-center justify-center transition-all duration-200 active:scale-95"
							onclick={onStop}
						>
							<Stop class="h-5 w-5" />
						</button>
					{:else}
						<button
							type="submit"
							aria-label="send message"
							class="send-btn rounded-circle flex h-8 w-8 cursor-pointer items-center justify-center transition-all duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 {!(
								(value.trim() === '' && pendingAttachments.length === 0) ||
								disabled
							)
								? 'hover:brightness-110'
								: 'bg-foreground/10 text-foreground/35'}"
							disabled={(value.trim() === '' && pendingAttachments.length === 0) ||
								disabled}
						>
							<ArrowUp class="h-5 w-5" strokeWidth="2" />
						</button>
					{/if}
				</div>
			</div>
		</div>
	</div>
</form>

<AddContext
	open={isAddContextOpen}
	onClose={closeAddContext}
	{activeAttachments}
	{isUploading}
	{webSearchEnabled}
	{thinkLongerEnabled}
	{generateImageEnabled}
	onFileUpload={handleFileUpload}
	onAttachResource={handleAttachResource}
	onToggleWebSearch={() => (webSearchEnabled = !webSearchEnabled)}
	onToggleThinkLonger={() => (thinkLongerEnabled = !thinkLongerEnabled)}
	onToggleGenerateImage={() => (generateImageEnabled = !generateImageEnabled)}
	onToggleAttachmentStatus={(id, action) => onToggleAttachmentStatus?.(id, action)}
	onRemoveAttachment={removeAttachment}
/>

<style>
	.chat-input {
		--lg-blur: 8px;
		--lg-bg: color-mix(in oklch, var(--background) 12%, transparent);
	}

	:global(.dark) .chat-input {
		--lg-bg: color-mix(in oklch, var(--background) 35%, transparent);
	}

	.chat-input:hover {
		--lg-bg: color-mix(in oklch, var(--background) 16%, transparent);
		--lg-highlight-center: rgba(255, 255, 255, 0.24);
		--lg-border-start: rgba(80, 80, 80, 0.28);
		--lg-border-end: rgba(170, 170, 170, 0.42);
	}

	:global(.dark) .chat-input:hover {
		--lg-bg: color-mix(in oklch, var(--background) 40%, transparent);
	}

	.chat-input:has(textarea:focus) {
		--lg-bg: color-mix(in oklch, var(--background) 25%, transparent);
		--lg-highlight-center: rgba(255, 255, 255, 0.42);
		--lg-border-start: rgba(120, 120, 120, 0.35);
		--lg-border-end: rgba(200, 200, 200, 0.5);
	}

	:global(.dark) .chat-input:has(textarea:focus) {
		--lg-bg: color-mix(in oklch, var(--background) 45%, transparent);
		--lg-highlight-center: rgba(255, 255, 255, 0.42);
		--lg-border-start: rgba(120, 120, 120, 0.35);
		--lg-border-end: rgba(200, 200, 200, 0.5);
	}

	.send-btn {
		background-color: var(--foreground);
		color: var(--background);
	}
</style>
