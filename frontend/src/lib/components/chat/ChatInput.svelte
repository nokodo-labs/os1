<script lang="ts">
	import { SEARCH_RESOURCE_TYPES, type SearchResourceType } from '$lib/api/streaming'
	import {
		categorizeMediaType,
		type PendingAttachment,
		revokePreviewUrls,
		type RunModifiers,
		uploadFile,
	} from '$lib/chat/attachments'
	import type { MessageAuthor } from '$lib/chat/participants'
	import type { ApiMessage } from '$lib/chat/types'
	import { getSourceConfig } from '$lib/citations/config'
	import AddContext from '$lib/components/chat/AddContext.svelte'
	import AgentAvatar from '$lib/components/chat/AgentAvatar.svelte'
	import ReplyPreview from '$lib/components/chat/ReplyPreview.svelte'
	import RotatingPlaceholder from '$lib/components/chat/RotatingPlaceholder.svelte'
	import SearchSettingsPanel from '$lib/components/chat/SearchSettingsPanel.svelte'
	import { swipe } from '$lib/attachments/swipe'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte'
	import Funnel from '$lib/components/icons/Funnel.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import Stop from '$lib/components/icons/Stop.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import MenuItem from '$lib/components/primitives/MenuItem.svelte'
	import MenuSectionHeader from '$lib/components/primitives/MenuSectionHeader.svelte'
	import PopupMenu from '$lib/components/primitives/PopupMenu.svelte'
	import type { ResourceItem } from '$lib/components/widgets/types'
	import { device } from '$lib/stores/device.svelte'
	import { apiFileToResource, files } from '$lib/stores/files.svelte'
	import { settingsState } from '$lib/stores/settings.svelte'
	import { tick } from 'svelte'
	import { backOut, cubicOut } from 'svelte/easing'
	import { fade, scale, type TransitionConfig } from 'svelte/transition'

	type QuickAction = 'none' | 'web_search' | 'think' | 'generate_image'

	interface ChatInputProps {
		value?: string
		mode?: 'chat' | 'search'
		placeholder?: string
		/**
		 * example asks the placeholder rotates through while the field is empty.
		 * empty (the default) keeps the plain static placeholder.
		 */
		placeholderExamples?: readonly string[]
		disabled?: boolean
		isGenerating?: boolean
		clearOnSubmit?: boolean
		focusToken?: number
		onSubmit?: (message: string, modifiers?: RunModifiers) => void
		onClear?: () => void
		searchTypes?: SearchResourceType[]
		onSearchTypesChange?: (types: SearchResourceType[]) => void
		/**
		 * result-type filters belong to global find mode. a bar scoped to one app
		 * has nothing to filter, so it shows the plain search glyph instead.
		 */
		showSearchFilters?: boolean
		onStop?: () => void
		onKeyDown?: (event: KeyboardEvent) => boolean | void
		/** the textarea gained or lost focus - a live composer is a focused one. */
		onFocusChange?: (focused: boolean) => void
		viewTransitionName?: string
		/** message being replied to; the caller clears it once the send lands. */
		replyTo?: ApiMessage | null
		replyToAuthor?: string | null
		onCancelReply?: () => void
		/**
		 * agents this composer may invoke. empty (the default) hides the whole
		 * affordance, which is what a solo thread wants: there the send button
		 * already runs the composer's agent.
		 */
		invokableAgents?: readonly MessageAuthor[]
		/** the one agent armed for the next send; owned by the caller. */
		armedAgentId?: string | null
		onArmAgent?: (agentId: string | null) => void
		/** the agent a swipe-up on the send button sends to, without arming. */
		swipeInvokeAgent?: MessageAuthor | null
	}

	let {
		value = $bindable(''),
		mode = 'chat',
		placeholder = 'send a message',
		placeholderExamples = [],
		disabled = false,
		isGenerating = false,
		clearOnSubmit = true,
		focusToken,
		onSubmit,
		onClear,
		searchTypes = SEARCH_RESOURCE_TYPES,
		onSearchTypesChange,
		showSearchFilters = true,
		onStop,
		onKeyDown,
		onFocusChange,
		viewTransitionName,
		replyTo = null,
		replyToAuthor = null,
		onCancelReply,
		invokableAgents = [],
		armedAgentId = null,
		onArmAgent,
		swipeInvokeAgent = null,
	}: ChatInputProps = $props()

	let textarea: HTMLTextAreaElement
	let formEl = $state<HTMLFormElement | null>(null)
	let isComposing = $state(false)
	let isAddContextOpen = $state(false)
	let isSearchSettingsOpen = $state(false)
	let isMultiLine = $state(false)
	let sendClusterEl = $state<HTMLDivElement | null>(null)
	let isInvokeMenuOpen = $state(false)
	const isSearchMode = $derived(mode === 'search')
	// the rotating layer only makes sense over an untouched chat composer: any
	// keystroke, a queued send, or find mode drops it back to the static line
	const showRotatingPlaceholder = $derived(
		placeholderExamples.length > 0 &&
			!isSearchMode &&
			!isGenerating &&
			!disabled &&
			value === ''
	)
	const chatInputMaxChars = $derived(settingsState.data?.limits?.max_chat_input_chars ?? null)
	const activeSearchTypes = $derived(searchTypes.length > 0 ? searchTypes : SEARCH_RESOURCE_TYPES)
	const isSearchFiltered = $derived(activeSearchTypes.length < SEARCH_RESOURCE_TYPES.length)

	// reply preview motion: the quote rises out of the composer glass when a
	// reply is armed and sinks back into it on every dismissal path. 260ms is the
	// family the bubble lift and the steering ghost already move in.
	const RISE_MS = 260
	const SWAP_MS = 140
	// how much further the quote travels than the opening clip reveals.
	const RISE_TRAVEL = 16
	const riseMs = $derived(device.prefersReducedMotion ? 0 : RISE_MS)
	const swapMs = $derived(device.prefersReducedMotion ? 0 : SWAP_MS)

	/**
	 * the composer's own height opening and closing around the quote. the
	 * transcript reads this box through a border-box resize observer, so it grows
	 * on a flat cubicOut: an overshoot here would bounce the whole transcript.
	 */
	function composerGrow(node: HTMLElement): TransitionConfig {
		if (riseMs === 0) return { duration: 0 }
		const style = getComputedStyle(node)
		const height = parseFloat(style.height) || 0
		const paddingTop = parseFloat(style.paddingTop) || 0
		const paddingBottom = parseFloat(style.paddingBottom) || 0
		return {
			duration: riseMs,
			easing: cubicOut,
			css: (t) =>
				`overflow: hidden; height: ${t * height}px; padding-top: ${t * paddingTop}px; padding-bottom: ${t * paddingBottom}px`,
		}
	}

	/** the quote itself, riding the same timeline on a spring. */
	function quoteRise(node: HTMLElement): TransitionConfig {
		if (riseMs === 0) return { duration: 0 }
		// never travel further than the quote is tall: past that the lift reads as
		// a jump rather than as the tail of the rise.
		const travel = Math.min(RISE_TRAVEL, node.offsetHeight * 0.4)
		return {
			duration: riseMs,
			easing: backOut,
			css: (t, u) => `transform: translateY(${u * travel}px); opacity: ${Math.min(1, t * 2)}`,
		}
	}

	// invocation: arming one agent for the next send. a separate mechanism from
	// mentions, and never a side effect of the plain send.
	const canInvoke = $derived(!isSearchMode && invokableAgents.length > 0)
	const armedAgent = $derived(
		canInvoke && armedAgentId
			? (invokableAgents.find((agent) => agent.id === armedAgentId) ?? null)
			: null
	)
	let swipeProgress = $state(0)

	// attachment + modifier state
	let webSearchEnabled = $state(false)
	let thinkLongerEnabled = $state(false)
	let generateImageEnabled = $state(false)
	const quickAction = $derived<QuickAction>(
		webSearchEnabled
			? 'web_search'
			: thinkLongerEnabled
				? 'think'
				: generateImageEnabled
					? 'generate_image'
					: 'none'
	)
	let extraPluginIds = $state<string[]>([])
	let pendingAttachments = $state<PendingAttachment[]>([])
	let isUploading = $state(false)

	// pending uploads + picked resources for THIS message's input tray
	const pendingAsNative = $derived(
		pendingAttachments.map((att) => ({
			id: att.fileId,
			resourceType: att.resourceType,
			filename: att.filename,
			type: att.category as 'image' | 'audio' | 'video' | 'file',
			isPending: true,
			previewUrl: att.previewUrl,
			resource: pendingToResource(att),
		}))
	)
	const activeAttachments = $derived(pendingAsNative)

	// track whether context is active for the badge indicator
	const hasContextActive = $derived(
		!isSearchMode &&
			(pendingAttachments.length > 0 ||
				webSearchEnabled ||
				thinkLongerEnabled ||
				generateImageEnabled ||
				extraPluginIds.length > 0)
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
		const maxChars = chatInputMaxChars
		if (maxChars !== null && value.length > maxChars) {
			value = value.slice(0, maxChars)
		}
		tick().then(resize)
	})

	function cappedInput(value: string): string {
		const maxChars = chatInputMaxChars
		return maxChars !== null && value.length > maxChars ? value.slice(0, maxChars) : value
	}

	function closeAddContext() {
		isAddContextOpen = false
	}

	function closeSearchSettings() {
		isSearchSettingsOpen = false
	}

	function toggleAddContext() {
		if (isSearchMode) return
		isAddContextOpen = !isAddContextOpen
	}

	function toggleSearchSettings() {
		if (!isSearchMode) return
		isSearchSettingsOpen = !isSearchSettingsOpen
	}

	$effect(() => {
		if (isSearchMode) {
			isAddContextOpen = false
			return
		}
		isSearchSettingsOpen = false
	})

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

	/** return the chat-attachable resource type for a picked item. */
	function attachmentTypeForResource(
		type: ResourceItem['type']
	): PendingAttachment['resourceType'] | null {
		switch (type) {
			case 'file':
			case 'note':
			case 'thread':
			case 'project':
			case 'reminder':
			case 'reminder_list':
			case 'calendar_event':
			case 'calendar':
				return type
			case 'message':
				return null
		}
	}

	/** build a display ResourceItem for a pending attachment (tray rendering). */
	function pendingToResource(att: PendingAttachment): ResourceItem {
		if (att.resource) return att.resource
		if (att.resourceType === 'file') {
			const cached = files.all.find((f) => f.id === att.fileId)
			if (cached) return apiFileToResource(cached)
			return {
				id: att.fileId,
				type: 'file',
				title: att.filename,
				href: getSourceConfig('file').href(att.fileId),
				updatedAt: Date.now(),
				createdAt: Date.now(),
				meta: {
					mime_type: att.mediaType,
					category: att.category,
					file_type: '',
					file_size: 0,
					source: '',
					owner_id: '',
					project_ids: [],
				},
			}
		}
		const cfg = getSourceConfig(att.resourceType)
		return {
			id: att.fileId,
			type: cfg.resourceType,
			title: att.filename,
			href: cfg.href(att.fileId),
			updatedAt: Date.now(),
			createdAt: Date.now(),
		}
	}

	/** convert a picker resource into the pending attachment list. */
	function handleAttachResource(resource: ResourceItem) {
		const resourceType = attachmentTypeForResource(resource.type)
		if (!resourceType) return
		if (
			pendingAttachments.some(
				(a) => a.resourceType === resourceType && a.fileId === resource.id
			)
		) {
			return
		}
		const mime =
			resourceType === 'file'
				? ((resource.meta?.mime_type as string) ?? 'application/octet-stream')
				: 'application/x-nokodo-resource'
		pendingAttachments = [
			...pendingAttachments,
			{
				fileId: resource.id,
				resourceType,
				filename: resource.title,
				mediaType: mime,
				category: resourceType === 'file' ? categorizeMediaType(mime) : 'file',
				previewUrl:
					resourceType === 'file' ? files.getThumbnailUrl(resource.id) : undefined,
				source: 'resource',
				resource,
			},
		]
	}

	function toggleExtraPlugin(pluginId: string) {
		if (extraPluginIds.includes(pluginId)) {
			extraPluginIds = extraPluginIds.filter((id) => id !== pluginId)
		} else {
			extraPluginIds = [...extraPluginIds, pluginId]
		}
	}

	function resize() {
		if (!textarea) return
		textarea.style.height = 'auto'
		const newHeight = Math.min(textarea.scrollHeight, 200)
		textarea.style.height = `${newHeight}px`
		isMultiLine = textarea.scrollHeight > 32
	}

	function handleInput(event: Event) {
		const target = event.currentTarget
		const maxChars = chatInputMaxChars
		if (
			target instanceof HTMLTextAreaElement &&
			maxChars !== null &&
			target.value.length > maxChars
		) {
			value = target.value.slice(0, maxChars)
			target.value = value
		}
		resize()
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (onKeyDown?.(event)) return
		// ctrl/cmd+enter is the invocation shortcut: pick an agent, or send to
		// the one already armed. plain enter stays a plain send.
		if (
			canInvoke &&
			event.key === 'Enter' &&
			(event.ctrlKey || event.metaKey) &&
			!isComposing
		) {
			event.preventDefault()
			if (armedAgent) handleSubmit()
			else void openInvokeMenu()
			return
		}
		// on touch devices, enter inserts a newline (users need it for multiline).
		// on desktop, bare enter sends the message. while a run is active,
		// submit still works - upstream routes it through steering (enqueue
		// into the running loop) instead of starting a new run.
		if (event.key === 'Enter' && !event.shiftKey && !isComposing && !device.isTouch) {
			event.preventDefault()
			handleSubmit()
		}
	}

	function handleSubmit(invokeAgentId: string | null = armedAgent?.id ?? null) {
		const hasAttachments = pendingAttachments.length > 0
		const message = cappedInput(value)
		if ((!message.trim() && (!hasAttachments || isSearchMode)) || disabled || !onSubmit) return

		if (isSearchMode) {
			onSubmit(message)
			if (clearOnSubmit) value = ''
			void tick().then(resize)
			return
		}

		const modifiers: RunModifiers = {
			webSearch: webSearchEnabled,
			thinkLonger: thinkLongerEnabled,
			generateImage: generateImageEnabled,
			extraPlugins: [...extraPluginIds],
			attachments: [...pendingAttachments],
			replyToMessageId: replyTo?.id ?? null,
			invokeAgentId,
		}

		const hasModifiers =
			modifiers.webSearch ||
			modifiers.thinkLonger ||
			modifiers.generateImage ||
			modifiers.extraPlugins.length > 0 ||
			modifiers.attachments.length > 0 ||
			modifiers.replyToMessageId !== null ||
			modifiers.invokeAgentId !== null

		onSubmit(message, hasModifiers ? modifiers : undefined)

		// reset state after send
		if (clearOnSubmit) value = ''
		isMultiLine = false
		revokePreviewUrls(pendingAttachments)
		pendingAttachments = []
		webSearchEnabled = false
		thinkLongerEnabled = false
		generateImageEnabled = false
		extraPluginIds = []
		onCancelReply?.()
		// arming is for one send only, however that send turns out.
		closeInvokeMenu()
		if (armedAgentId) onArmAgent?.(null)
		if (textarea) {
			textarea.style.height = 'auto'
		}
	}

	function handleClearSearch() {
		if (!isSearchMode || disabled) return
		value = ''
		onClear?.()
		void tick().then(() => {
			resize()
			textarea?.focus()
		})
	}

	function handleSearchTypesChange(types: SearchResourceType[]): void {
		onSearchTypesChange?.(types)
	}

	function setQuickAction(action: QuickAction): void {
		webSearchEnabled = action === 'web_search'
		thinkLongerEnabled = action === 'think'
		generateImageEnabled = action === 'generate_image'
	}

	function handleCompositionStart() {
		isComposing = true
	}

	function handleCompositionEnd() {
		isComposing = false
	}

	/**
	 * touching anything in the send cluster blurs the textarea, which dismisses
	 * the virtual keyboard. every path that does so re-focuses instead of
	 * fighting the blur, the same way the send button already does.
	 */
	async function keepKeyboardOpen() {
		if (!device.virtualKeyboardOpen) return
		await tick()
		textarea?.focus()
	}

	async function openInvokeMenu() {
		if (!canInvoke) return
		isInvokeMenuOpen = true
		await keepKeyboardOpen()
	}

	function closeInvokeMenu() {
		isInvokeMenuOpen = false
	}

	function toggleInvokeMenu() {
		if (isInvokeMenuOpen) closeInvokeMenu()
		else void openInvokeMenu()
	}

	/** picking the armed agent again disarms, so the list is its own off switch. */
	async function toggleArmedAgent(agentId: string) {
		isInvokeMenuOpen = false
		onArmAgent?.(armedAgentId === agentId ? null : agentId)
		await keepKeyboardOpen()
	}

	function handleSendContextMenu(event: MouseEvent) {
		if (!canInvoke) return
		event.preventDefault()
		void openInvokeMenu()
	}

	// esc disarms wherever focus is. while the list is open esc belongs to the
	// list, which closes itself on the same keystroke.
	$effect(() => {
		if (!armedAgentId) return
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key !== 'Escape' || isInvokeMenuOpen) return
			onArmAgent?.(null)
		}
		window.addEventListener('keydown', onKeyDown)
		return () => window.removeEventListener('keydown', onKeyDown)
	})

	// esc drops an armed reply, once the invoke menu and the armed agent - which
	// answer the same key - have had their turn.
	$effect(() => {
		if (!replyTo || isSearchMode || !onCancelReply) return
		const dismissOnEscape = (event: KeyboardEvent) => {
			if (event.key !== 'Escape' || event.defaultPrevented) return
			if (isInvokeMenuOpen || armedAgentId) return
			onCancelReply()
		}
		window.addEventListener('keydown', dismissOnEscape)
		return () => window.removeEventListener('keydown', dismissOnEscape)
	})

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
		class="liquid-glass chat-input relative w-full rounded-3xl transition-all duration-300"
		data-chat-input
		style={viewTransitionName ? `view-transition-name: ${viewTransitionName};` : undefined}
	>
		<div class="relative z-10 px-1 py-1">
			{#if replyTo && !isSearchMode}
				<div class="px-2 pt-1.5 pb-0.5" data-reply-preview transition:composerGrow|local>
					<div transition:quoteRise|local>
						<!-- retargeting a live reply swaps the quote in place: the
						     composer is already open, so the rise has nothing to do -->
						{#key replyTo.id}
							<div in:fade|local={{ duration: swapMs, easing: cubicOut }}>
								<ReplyPreview
									message={replyTo}
									authorName={replyToAuthor}
									onDismiss={onCancelReply}
								/>
							</div>
						{/key}
					</div>
				</div>
			{/if}
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
					{#if isSearchMode && showSearchFilters}
						<button
							type="button"
							aria-label="search filters"
							aria-haspopup="dialog"
							aria-expanded={isSearchSettingsOpen}
							class="text-foreground/65 hover:text-foreground relative flex h-8 w-8 cursor-pointer items-center justify-center bg-transparent p-0 transition-colors duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
							{disabled}
							onclick={toggleSearchSettings}
						>
							<Funnel class="h-5 w-5" strokeWidth="2" />
							{#if isSearchFiltered}
								<span
									class="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full"
									style="background-color: var(--accent-primary);"
								></span>
							{/if}
						</button>
					{:else if isSearchMode}
						<span
							class="text-foreground/45 flex h-8 w-8 items-center justify-center"
							aria-hidden="true"
						>
							<Search class="h-5 w-5" strokeWidth="2" />
						</span>
					{:else}
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
					{/if}
				</div>

				<div class="flex flex-1 items-center px-1">
					<div class="relative w-full">
						<textarea
							bind:this={textarea}
							bind:value
							maxlength={chatInputMaxChars ?? undefined}
							placeholder={isGenerating && !isSearchMode
								? 'enqueue a message'
								: placeholder}
							{disabled}
							oninput={handleInput}
							onkeydown={handleKeyDown}
							onfocus={() => onFocusChange?.(true)}
							onblur={() => onFocusChange?.(false)}
							oncompositionstart={handleCompositionStart}
							oncompositionend={handleCompositionEnd}
							rows="1"
							class="scrollbar-thumb-foreground/20 hover:scrollbar-thumb-foreground/30 text-foreground/96 m-0 block max-h-96 min-h-6 w-full resize-none scrollbar-thin scrollbar-track-transparent overflow-y-auto border-0 bg-transparent px-1 py-0 font-[inherit] text-[0.9375rem] leading-6 outline-none {showRotatingPlaceholder
								? 'placeholder:text-transparent'
								: 'placeholder:text-foreground/40'}"
						></textarea>
						{#if placeholderExamples.length > 0 && !isSearchMode}
							<RotatingPlaceholder
								examples={placeholderExamples}
								active={showRotatingPlaceholder}
							/>
						{/if}
					</div>
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
							class="rounded-circle bg-foreground/15 text-foreground hover:bg-foreground/25 flex h-8 w-8 cursor-pointer items-center justify-center transition-all duration-200 active:scale-95"
							onclick={onStop}
						>
							<Stop class="h-5 w-5" />
						</button>
					{/if}
					{#if isSearchMode}
						{#if value.length > 0}
							<button
								type="button"
								aria-label="clear search"
								class="rounded-circle bg-foreground/15 text-foreground hover:bg-foreground/25 flex h-8 w-8 cursor-pointer items-center justify-center transition-all duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
								{disabled}
								onclick={handleClearSearch}
							>
								<XMark class="h-5 w-5" />
							</button>
						{/if}
						<button
							type="submit"
							aria-label="search"
							class="send-btn rounded-circle flex h-8 w-8 cursor-pointer items-center justify-center transition-all duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 {value.trim() &&
							!disabled
								? 'hover:brightness-110'
								: 'bg-foreground/10 text-foreground/35'}"
							disabled={!value.trim() || disabled}
						>
							<Search class="h-4.5 w-4.5" strokeWidth="2" />
						</button>
					{:else}
						<div bind:this={sendClusterEl} class="group relative flex items-center">
							{#if canInvoke && !device.isTouch}
								<button
									type="button"
									aria-label="send and invoke an agent"
									aria-haspopup="menu"
									aria-expanded={isInvokeMenuOpen}
									class="rounded-circle border-foreground/12 bg-background/80 text-foreground/70 hover:text-foreground absolute -top-1.5 -left-1.5 z-10 flex h-4 w-4 cursor-pointer items-center justify-center border shadow-sm backdrop-blur-md transition-opacity duration-200 {isInvokeMenuOpen
										? 'opacity-100'
										: 'pointer-events-none opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 focus-visible:pointer-events-auto focus-visible:opacity-100'}"
									onclick={toggleInvokeMenu}
								>
									<ChevronUp class="h-3 w-3" strokeWidth="2.5" />
								</button>
							{/if}
							<button
								type="submit"
								aria-label={armedAgent
									? `send and invoke ${armedAgent.name}`
									: isGenerating
										? 'enqueue message'
										: 'send message'}
								title={armedAgent
									? `send and invoke ${armedAgent.name}`
									: isGenerating
										? 'enqueue into the running agent'
										: undefined}
								oncontextmenu={handleSendContextMenu}
								{@attach swipe({
									direction: 'up',
									threshold: 40,
									maxTravel: 56,
									enabled: canInvoke,
									onProgress: (progress) => (swipeProgress = progress),
									onTrigger: () => {
										swipeProgress = 0
										if (swipeInvokeAgent) handleSubmit(swipeInvokeAgent.id)
										void keepKeyboardOpen()
									},
								})}
								class="send-btn rounded-circle relative flex h-8 w-8 cursor-pointer items-center justify-center overflow-hidden transition-all duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 {!(
									(value.trim() === '' && pendingAttachments.length === 0) ||
									disabled
								)
									? 'hover:brightness-110'
									: 'bg-foreground/10 text-foreground/35'}"
								class:armed={armedAgent !== null}
								disabled={(value.trim() === '' &&
									pendingAttachments.length === 0) ||
									disabled}
							>
								{#if armedAgent}
									<span
										class="absolute inset-0 flex items-center justify-center"
										transition:scale|local={{ duration: 180, start: 0.5 }}
									>
										<AgentAvatar
											name={armedAgent.name}
											avatarUrl={armedAgent.avatarUrl}
											class="h-full w-full"
											textClass="text-xs"
										/>
									</span>
								{:else}
									<span
										class="absolute inset-0 flex items-center justify-center"
										style:opacity={1 - swipeProgress}
										style:scale={1 - swipeProgress * 0.4}
										transition:scale|local={{ duration: 180, start: 0.5 }}
									>
										<ArrowUp class="h-5 w-5" strokeWidth="2" />
									</span>
									{#if swipeInvokeAgent && swipeProgress > 0}
										<!-- who the swipe sends to, filling in as the gesture arms -->
										<span
											class="pointer-events-none absolute inset-0 flex items-center justify-center"
											style:opacity={swipeProgress}
											style:scale={0.6 + swipeProgress * 0.4}
										>
											<AgentAvatar
												name={swipeInvokeAgent.name}
												avatarUrl={swipeInvokeAgent.avatarUrl}
												class="h-full w-full"
												textClass="text-xs"
											/>
										</span>
									{/if}
								{/if}
							</button>
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>
</form>

{#if isSearchMode}
	{#if showSearchFilters}
		<SearchSettingsPanel
			open={isSearchSettingsOpen}
			onClose={closeSearchSettings}
			selectedTypes={activeSearchTypes}
			onChange={handleSearchTypesChange}
		/>
	{/if}
{:else}
	<AddContext
		open={isAddContextOpen}
		onClose={closeAddContext}
		{activeAttachments}
		{isUploading}
		{webSearchEnabled}
		{thinkLongerEnabled}
		{generateImageEnabled}
		{quickAction}
		{extraPluginIds}
		onFileUpload={handleFileUpload}
		onAttachResource={handleAttachResource}
		onQuickActionChange={setQuickAction}
		onToggleExtraPlugin={toggleExtraPlugin}
		onRemoveAttachment={removeAttachment}
	/>
{/if}

<PopupMenu
	open={isInvokeMenuOpen}
	anchorEl={sendClusterEl}
	onClose={closeInvokeMenu}
	class="min-w-56"
	estimatedHeight={64 + invokableAgents.length * 48}
>
	<MenuSectionHeader>send and invoke</MenuSectionHeader>
	{#each invokableAgents as agent (agent.id)}
		<MenuItem
			selected={agent.id === armedAgentId}
			onclick={() => void toggleArmedAgent(agent.id)}
		>
			{#snippet iconSnippet()}
				{#if agent.avatarUrl}
					<img
						src={agent.avatarUrl}
						alt=""
						class="rounded-circle h-full w-full object-cover"
					/>
				{:else}
					<span
						class="bg-foreground/10 text-foreground/80 rounded-circle flex h-full w-full items-center justify-center text-xs font-semibold uppercase"
					>
						{agent.name.charAt(0)}
					</span>
				{/if}
			{/snippet}
			{agent.name}
		</MenuItem>
	{/each}
</PopupMenu>

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

	/* armed: the arrow has become an agent, so it reads as the accent, not as
	   the neutral send affordance it replaced. */
	.send-btn.armed {
		background-color: var(--accent-primary);
		color: var(--foreground);
		box-shadow: 0 0 0 2px var(--accent-border);
	}
</style>
