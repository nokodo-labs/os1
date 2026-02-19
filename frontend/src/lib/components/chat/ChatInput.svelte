<script lang="ts">
	// import LiquidMetal from '$lib/components/effects/LiquidMetal.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Stop from '$lib/components/icons/Stop.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { tick } from 'svelte'
	import { scale } from 'svelte/transition'

	interface ChatInputProps {
		value?: string
		placeholder?: string
		disabled?: boolean
		isGenerating?: boolean
		focusToken?: number
		onSubmit?: (message: string) => void
		onStop?: () => void
		onKeyDown?: (event: KeyboardEvent) => boolean | void
		viewTransitionName?: string
	}

	let {
		value = $bindable(''),
		placeholder = 'send a message',
		disabled = false,
		isGenerating = false,
		focusToken,
		onSubmit,
		onStop,
		onKeyDown,
		viewTransitionName,
	}: ChatInputProps = $props()

	let textarea: HTMLTextAreaElement
	let isComposing = $state(false)
	let isAddMenuOpen = $state(false)
	let isMultiLine = $state(false)

	let fileInput: HTMLInputElement
	let imageInput: HTMLInputElement

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

	function closeAddMenu() {
		isAddMenuOpen = false
	}

	function toggleAddMenu() {
		isAddMenuOpen = !isAddMenuOpen
	}

	function handleAddMenuKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.stopPropagation()
			closeAddMenu()
		}
	}

	function handleClickOutside(event: MouseEvent) {
		const target = event.target as HTMLElement
		if (!target.closest('[data-chat-add-menu-root]')) {
			closeAddMenu()
		}
	}

	$effect(() => {
		if (!isAddMenuOpen) return
		document.addEventListener('click', handleClickOutside)
		document.addEventListener('keydown', handleAddMenuKeyDown)
		return () => {
			document.removeEventListener('click', handleClickOutside)
			document.removeEventListener('keydown', handleAddMenuKeyDown)
		}
	})

	function handleFileSelected(event: Event) {
		const input = event.currentTarget as HTMLInputElement
		const files = Array.from(input.files ?? [])
		if (files.length === 0) return
		console.log(
			'Selected files:',
			files.map((f) => f.name)
		)
		input.value = ''
		closeAddMenu()
	}

	function handleInput() {
		if (!textarea) return
		textarea.style.height = 'auto'
		const newHeight = Math.min(textarea.scrollHeight, 200)
		textarea.style.height = `${newHeight}px`
		// Check if content spans multiple lines (scrollHeight > single line height ~24px)
		isMultiLine = textarea.scrollHeight > 32
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (onKeyDown?.(event)) return
		// Don't submit if composing (for IME input)
		if (event.key === 'Enter' && !event.shiftKey && !isComposing) {
			event.preventDefault()
			handleSubmit()
		}
	}

	function handleSubmit() {
		if (!value.trim() || disabled || !onSubmit) return
		onSubmit(value)
		value = ''
		isMultiLine = false
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
	 * on mobile, touching a button outside the textarea triggers the browser's
	 * built-in "blur on touch elsewhere" before any click/pointer events fire.
	 * touchstart fires FIRST in the event pipeline — calling preventDefault()
	 * here stops the browser from ever initiating the focus transfer, so the
	 * textarea keeps focus and the virtual keyboard stays up.
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

<form class="w-full" onsubmit={handleFormSubmit}>
	<div
		class="liquid-glass chat-input relative w-full transition-all duration-300"
		class:rounded-pill={!isMultiLine}
		class:rounded-container={isMultiLine}
		data-chat-input
		style={viewTransitionName ? `view-transition-name: ${viewTransitionName};` : undefined}
	>
		<div class="relative z-10 px-1 py-1">
			<div
				class="flex gap-2 px-2.5 py-2.5"
				class:items-center={!isMultiLine}
				class:items-end={isMultiLine}
			>
				<div
					class="ml-1 flex shrink-0"
					class:items-center={!isMultiLine}
					class:items-end={isMultiLine}
					class:pb-1={isMultiLine}
					data-chat-add-menu-root
				>
					<button
						type="button"
						aria-label="Add attachment"
						aria-haspopup="menu"
						aria-expanded={isAddMenuOpen}
						class="flex cursor-pointer items-center justify-center bg-transparent p-0 text-black/65 transition-colors duration-200 hover:text-black/95 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 dark:text-white dark:hover:text-white"
						{disabled}
						onclick={toggleAddMenu}
					>
						<Plus class="h-5.5 w-5.5" strokeWidth="2" />
					</button>

					<input
						bind:this={fileInput}
						type="file"
						class="hidden"
						onchange={handleFileSelected}
					/>
					<input
						bind:this={imageInput}
						type="file"
						accept="image/*"
						class="hidden"
						onchange={handleFileSelected}
					/>

					{#if isAddMenuOpen}
						<div
							transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
							class="animate-popup-up rounded-container absolute bottom-full left-0 mb-3 w-56 overflow-hidden border border-white/10 bg-black/85 p-1 text-white/85 shadow-[0_24px_48px_rgba(0,0,0,0.35)] backdrop-blur-sm"
							role="menu"
						>
							<button
								type="button"
								class="rounded-pill flex w-full cursor-pointer items-center px-3 py-2 text-left text-sm transition-colors hover:bg-white/10"
								role="menuitem"
								onclick={() => fileInput?.click()}
							>
								upload file
							</button>
							<button
								type="button"
								class="rounded-pill flex w-full cursor-pointer items-center px-3 py-2 text-left text-sm transition-colors hover:bg-white/10"
								role="menuitem"
								onclick={() => imageInput?.click()}
							>
								upload image
							</button>
						</div>
					{/if}
				</div>

				<div class="flex flex-1 items-center px-1.5">
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
						class="scrollbar-thin scrollbar-track-transparent scrollbar-thumb-black/20 hover:scrollbar-thumb-black/30 dark:scrollbar-thumb-white/20 dark:hover:scrollbar-thumb-white/30 m-0 max-h-96 min-h-6 w-full resize-none overflow-y-auto border-0 bg-transparent px-1 py-0 font-[inherit] text-[0.9375rem] leading-6 text-black/96 outline-none placeholder:text-black/40 dark:text-white/96 dark:placeholder:text-white/40"
					></textarea>
				</div>

				<div
					class="mr-1 flex shrink-0 space-x-1"
					class:items-center={!isMultiLine}
					class:items-end={isMultiLine}
					class:pb-1={isMultiLine}
				>
					{#if isGenerating}
						<button
							type="button"
							aria-label="stop generating"
							class="rounded-circle flex h-8 w-8 cursor-pointer items-center justify-center bg-black text-white transition-all duration-200 hover:bg-gray-800 active:scale-95 dark:bg-white dark:text-black dark:hover:bg-gray-100"
							onclick={onStop}
						>
							<Stop class="h-3.5 w-3.5" />
						</button>
					{:else}
						<button
							type="submit"
							aria-label="send message"
							class="send-btn rounded-circle flex h-8 w-8 cursor-pointer items-center justify-center transition-all duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 {!(
								value.trim() === '' || disabled
							)
								? 'hover:brightness-110'
								: 'bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}"
							disabled={value.trim() === '' || disabled}
							ontouchstart={handleSubmit}
							onclick={handleSubmit}
						>
							<ArrowUp class="h-5 w-5" strokeWidth="2" />
						</button>
					{/if}
				</div>
			</div>
		</div>
	</div>
</form>

<style>
	.chat-input {
		--lg-blur: 8px;
		--lg-bg: rgba(255, 255, 255, 0.12);
	}

	:global(.dark) .chat-input {
		--lg-bg: rgba(0, 0, 0, 0.35);
	}

	.chat-input:hover {
		--lg-bg: rgba(255, 255, 255, 0.16);
		--lg-highlight-center: rgba(255, 255, 255, 0.24);
		--lg-border-start: rgba(80, 80, 80, 0.28);
		--lg-border-end: rgba(170, 170, 170, 0.42);
	}

	:global(.dark) .chat-input:hover {
		--lg-bg: rgba(0, 0, 0, 0.4);
	}

	.chat-input:has(textarea:focus) {
		--lg-bg: rgba(255, 255, 255, 0.25);
		--lg-highlight-center: rgba(255, 255, 255, 0.42);
		--lg-border-start: rgba(120, 120, 120, 0.35);
		--lg-border-end: rgba(200, 200, 200, 0.5);
	}

	:global(.dark) .chat-input:has(textarea:focus) {
		--lg-bg: rgba(0, 0, 0, 0.45);
		--lg-highlight-center: rgba(255, 255, 255, 0.42);
		--lg-border-start: rgba(120, 120, 120, 0.35);
		--lg-border-end: rgba(200, 200, 200, 0.5);
	}

	.send-btn {
		background-color: var(--accent-primary);
		color: white;
	}

	:global(.dark) .send-btn {
		background-color: rgb(255 255 255);
		color: rgb(0 0 0);
	}

	.send-btn:disabled {
		background-color: rgb(229 231 235);
		color: rgb(107 114 128);
	}

	:global(.dark) .send-btn:disabled {
		background-color: rgb(55 65 81);
		color: rgb(156 163 175);
	}
</style>
