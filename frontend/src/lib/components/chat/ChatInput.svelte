<script lang="ts">
	// import LiquidMetal from '$lib/components/effects/LiquidMetal.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Stop from '$lib/components/icons/Stop.svelte'
	import * as Tooltip from '$lib/components/ui/tooltip'

	interface ChatInputProps {
		value?: string
		placeholder?: string
		disabled?: boolean
		isGenerating?: boolean
		focusToken?: number
		onSubmit?: (message: string) => void
		onStop?: () => void
		onKeyDown?: (event: KeyboardEvent) => boolean | void
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
	}: ChatInputProps = $props()

	let textarea: HTMLTextAreaElement
	let isComposing = $state(false)
	let isFocused = $state(false)
	let isAddMenuOpen = $state(false)

	let fileInput: HTMLInputElement
	let imageInput: HTMLInputElement

	$effect(() => {
		if (!textarea) return
		if (!focusToken) return
		if (disabled) return
		requestAnimationFrame(() => {
			textarea.focus()
			const end = textarea.value.length
			textarea.setSelectionRange(end, end)
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
		textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
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

	function handleFormSubmit(event: SubmitEvent) {
		event.preventDefault()
		handleSubmit()
	}
</script>

<form class="w-full" onsubmit={handleFormSubmit}>
	<div
		class="liquid-glass chat-input relative w-full rounded-full transition-all duration-300"
		class:liquid-glass--frosted={isFocused}
	>
		<div class="relative z-10 px-1 py-1">
			<div class="flex items-center gap-2 px-2.5 py-2.5">
				<div class="ml-1 flex shrink-0 items-center" data-chat-add-menu-root>
					<Tooltip.Root>
						<Tooltip.Trigger>
							<button
								type="button"
								aria-label="Add attachment"
								aria-haspopup="menu"
								aria-expanded={isAddMenuOpen}
								class="flex h-8 w-8 items-center justify-center rounded-full bg-transparent text-black/65 transition-all duration-200 hover:bg-black/5 hover:text-black/95 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 dark:text-white/65 dark:hover:bg-white/5 dark:hover:text-white/95"
								{disabled}
								onclick={toggleAddMenu}
							>
								<Plus className="h-5.5 w-5.5" strokeWidth="2" />
							</button>
						</Tooltip.Trigger>
						<Tooltip.Content>
							<p>add attachment</p>
						</Tooltip.Content>
					</Tooltip.Root>

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
							class="absolute bottom-full left-0 mb-3 w-56 overflow-hidden rounded-2xl border border-white/10 bg-black/85 p-1 text-white/85 shadow-[0_24px_48px_rgba(0,0,0,0.35)] backdrop-blur-sm"
							role="menu"
						>
							<button
								type="button"
								class="flex w-full items-center rounded-xl px-3 py-2 text-left text-sm transition-colors hover:bg-white/10"
								role="menuitem"
								onclick={() => fileInput?.click()}
							>
								upload file
							</button>
							<button
								type="button"
								class="flex w-full items-center rounded-xl px-3 py-2 text-left text-sm transition-colors hover:bg-white/10"
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
						onfocus={() => (isFocused = true)}
						onblur={() => (isFocused = false)}
						rows="1"
						class="scrollbar-thin scrollbar-track-transparent scrollbar-thumb-black/20 hover:scrollbar-thumb-black/30 dark:scrollbar-thumb-white/20 dark:hover:scrollbar-thumb-white/30 m-0 max-h-96 min-h-6 w-full resize-none overflow-y-auto border-0 bg-transparent px-1 py-0 font-[inherit] text-[0.9375rem] leading-6 text-black/96 outline-none placeholder:text-black/40 dark:text-white/96 dark:placeholder:text-white/40"
					></textarea>
				</div>

				<div class="mr-1 flex shrink-0 items-center space-x-1">
					<Tooltip.Root>
						<Tooltip.Trigger>
							{#if isGenerating}
								<button
									type="button"
									aria-label="stop generating"
									class="flex h-8 w-8 items-center justify-center rounded-full bg-black text-white transition-all duration-200 hover:bg-gray-800 active:scale-95 dark:bg-white dark:text-black dark:hover:bg-gray-100"
									onclick={onStop}
								>
									<Stop className="h-3.5 w-3.5" />
								</button>
							{:else}
								<button
									type="submit"
									aria-label="send message"
									class="send-btn flex h-8 w-8 items-center justify-center rounded-full transition-all duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 {!(
										value.trim() === '' || disabled
									)
										? 'hover:brightness-110'
										: 'bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}"
									disabled={value.trim() === '' || disabled}
								>
									<ArrowUp className="h-5 w-5" strokeWidth="2" />
								</button>
							{/if}
						</Tooltip.Trigger>
						<Tooltip.Content>
							<p>{isGenerating ? 'stop generating' : 'send message'}</p>
						</Tooltip.Content>
					</Tooltip.Root>
				</div>
			</div>
		</div>
	</div>
</form>

<style>
	.chat-input {
		--lg-blur: 12px;
		--lg-saturate: 1.2;
	}

	.chat-input.liquid-glass--frosted {
		--lg-blur: 28px;
		--lg-saturate: 1.25;
	}

	.send-btn {
		background-color: var(--accent-primary);
		color: white;
	}

	:global(.dark) .send-btn {
		background-color: white;
		color: var(--accent-primary);
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
