<script lang="ts">
	import type { DocParticipant } from '$lib/collaboration'
	import SharedEditor from '$lib/components/editor/SharedEditor.svelte'
	import ArrowUturnLeft from '$lib/components/icons/ArrowUturnLeft.svelte'
	import ArrowUturnRight from '$lib/components/icons/ArrowUturnRight.svelte'
	import Bars3BottomLeft from '$lib/components/icons/Bars3BottomLeft.svelte'
	import Bold from '$lib/components/icons/Bold.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import Cloud from '$lib/components/icons/Cloud.svelte'
	import Code from '$lib/components/icons/Code.svelte'
	import CodeBracket from '$lib/components/icons/CodeBracket.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import H1 from '$lib/components/icons/H1.svelte'
	import H2 from '$lib/components/icons/H2.svelte'
	import H3 from '$lib/components/icons/H3.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Italic from '$lib/components/icons/Italic.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import NumberedList from '$lib/components/icons/NumberedList.svelte'
	import PencilSquare from '$lib/components/icons/PencilSquare.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Strikethrough from '$lib/components/icons/Strikethrough.svelte'
	import Underline from '$lib/components/icons/Underline.svelte'
	import { MenuItem, PopupMenu, Switch } from '$lib/components/primitives'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { notes } from '$lib/stores/notes.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { getUserInitials } from '$lib/utils'
	import { marked } from 'marked'
	import { onDestroy } from 'svelte'
	// storage format: markdown (in notes store)
	// normal mode: shared collaborative tiptap editor (Yjs CRDT)
	// markdown mode: textarea showing raw markdown source (manual save / Ctrl+S)

	interface Props {
		noteId: string
		onBack?: () => void | Promise<void>
	}

	let { noteId, onBack }: Props = $props()

	const chrome = useSystemChrome()

	$effect(() => {
		void notes.load()
	})

	const note = $derived(notes.get(noteId))

	let title = $state('')
	let content = $state('') // markdown string
	let isRawMode = $state(false)
	let menuOpen = $state(false)
	let menuButtonEl: HTMLButtonElement | null = $state(null)
	let saveTimeout: number | null = null
	let textareaEl: HTMLTextAreaElement | null = $state(null)
	let sharedEditor: SharedEditor | null = $state(null)
	let collabParticipants = $state<DocParticipant[]>([])
	let rawDirty = $state(false) // track unsaved raw edits

	const documentId = $derived(`note:${noteId}`)
	// all participants except self (per-session: same user can appear multiple times)
	const peers = $derived(collabParticipants.filter((p) => p.sessionId !== currentSessionId))
	let currentSessionId: string = ''

	// user info for awareness (cursor labels)
	const userInfo = $derived.by(() => {
		const u = session.currentUser
		if (!u) return undefined
		return {
			id: String(u.id),
			name: u.display_name ?? u.email?.split('@')[0] ?? 'user',
			avatarUrl: u.avatar_url ?? null,
		}
	})

	const wordCount = $derived.by(() => {
		const text = content.trim()
		if (!text) return 0
		return text.split(/\s+/).filter(Boolean).length
	})

	const charCount = $derived(content.length)

	// undo/redo always enabled in rich mode (tiptap handles internally)
	const canUndo = $derived(!isRawMode)
	const canRedo = $derived(!isRawMode)

	let lastNoteId: string | null = $state(null)
	let isSyncingFromStore = false
	let lastSyncedTitle = ''
	let lastSyncedContent = ''

	// sync state from store
	$effect(() => {
		const current = note
		if (!current) return

		if (current.id !== lastNoteId) {
			lastNoteId = current.id
			isSyncingFromStore = true
			title = current.title
			content = current.content
			lastSyncedTitle = current.title
			lastSyncedContent = current.content
			isRawMode = false
			rawDirty = false
			menuOpen = false
			queueMicrotask(() => {
				isSyncingFromStore = false
			})
			return
		}

		const titleChanged = current.title !== lastSyncedTitle
		const contentChanged = current.content !== lastSyncedContent
		if (titleChanged || contentChanged) {
			if (saveTimeout !== null) {
				window.clearTimeout(saveTimeout)
				saveTimeout = null
			}
			isSyncingFromStore = true
			if (titleChanged) title = current.title
			// in raw mode, don't overwrite user's edits
			if (contentChanged && !isRawMode) content = current.content
			lastSyncedTitle = current.title
			lastSyncedContent = current.content
			queueMicrotask(() => {
				isSyncingFromStore = false
			})
		}
	})

	// inject island context actions
	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	function scheduleSave(): void {
		if (saveTimeout !== null) window.clearTimeout(saveTimeout)
		saveTimeout = window.setTimeout(() => {
			saveTimeout = null
			lastSyncedTitle = title
			lastSyncedContent = content
			void notes.update(noteId, { title, content })
		}, 200)
	}

	/** manual save for raw mode (Ctrl+S) */
	function saveRaw(): void {
		if (!rawDirty) return
		// push raw markdown into the SharedEditor's Yjs doc so it syncs to peers
		const editor = sharedEditor?.getEditor()
		if (editor) {
			const html = String(marked.parse(content, { gfm: true, breaks: true }))
			editor.commands.setContent(html)
		}
		rawDirty = false
		// persist to API
		lastSyncedTitle = title
		lastSyncedContent = content
		void notes.update(noteId, { title, content })
	}

	onDestroy(() => {
		if (saveTimeout !== null) window.clearTimeout(saveTimeout)
	})

	function handleContentChange(markdown: string): void {
		if (isSyncingFromStore) return
		content = markdown
		scheduleSave()
	}

	function handleTitleInput(): void {
		if (isSyncingFromStore) return
		scheduleSave()
	}

	function handleRawInput(): void {
		if (isSyncingFromStore) return
		rawDirty = true
	}

	function undo(): void {
		if (isRawMode) return
		sharedEditor?.undo()
	}

	function redo(): void {
		if (isRawMode) return
		sharedEditor?.redo()
	}

	function handleShare(): void {
		menuOpen = false
		console.log('share note:', noteId)
	}

	function setRawMode(next: boolean): void {
		if (next === isRawMode) return
		if (next) {
			// switching TO raw: grab latest markdown from SharedEditor
			const md = sharedEditor?.getMarkdown()
			if (md !== undefined) content = md
			rawDirty = false
			isRawMode = true
			requestAnimationFrame(() => textareaEl?.focus())
		} else {
			// switching FROM raw: push raw edits into Yjs doc so they sync
			if (rawDirty) {
				saveRaw()
			}
			isRawMode = false
			queueMicrotask(() => sharedEditor?.focus())
		}
	}

	function handleProperties(): void {
		menuOpen = false
		console.log('show properties for:', noteId)
	}

	// keyboard shortcuts for raw mode
	function handleRawKeyDown(event: KeyboardEvent): void {
		const isMod = event.metaKey || event.ctrlKey
		if (isMod && event.key === 's') {
			event.preventDefault()
			saveRaw()
		}
	}

	// capture session_id from provider for peer filtering
	function handleSynced(): void {
		const provider = sharedEditor?.getProvider()
		if (provider) {
			const sid = provider.getSessionId()
			if (sid) currentSessionId = sid
		}
	}

	// non-passive wheel handler: allows preventDefault for horizontal scroll redirect
	function wheelToHScroll(node: HTMLElement): { destroy: () => void } {
		function handler(event: WheelEvent): void {
			if (event.deltaY === 0) return
			event.preventDefault()
			node.scrollLeft += event.deltaY
		}
		node.addEventListener('wheel', handler, { passive: false })
		return { destroy: () => node.removeEventListener('wheel', handler) }
	}
</script>

{#snippet islandContextActions()}
	{#if onBack && device.isMobile}
		<button
			type="button"
			class="rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
			onclick={() => onBack?.()}
			aria-label="back to notes"
		>
			<ChevronLeft strokeWidth="2" />
		</button>
	{/if}

	<!-- undo/redo buttons -->
	<button
		type="button"
		class="rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
		onclick={undo}
		disabled={isRawMode || !canUndo}
		aria-label="undo"
	>
		<ArrowUturnLeft />
	</button>
	<button
		type="button"
		class="rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
		onclick={redo}
		disabled={isRawMode || !canRedo}
		aria-label="redo"
	>
		<ArrowUturnRight />
	</button>

	<!-- 3-dot menu -->
	<button
		type="button"
		bind:this={menuButtonEl}
		class="rounded-pill flex cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={() => (menuOpen = !menuOpen)}
		aria-label="note options"
		aria-haspopup="menu"
		aria-expanded={menuOpen}
	>
		<EllipsisHorizontal />
	</button>
	<PopupMenu open={menuOpen} anchorEl={menuButtonEl} onClose={() => (menuOpen = false)}>
		<button
			type="button"
			role="menuitemcheckbox"
			aria-checked={isRawMode}
			class="rounded-pill flex w-full cursor-pointer items-center gap-3 border-none bg-transparent px-3 py-2 text-left text-sm text-white/85 transition-all duration-150 hover:bg-white/10 hover:text-white"
			onclick={() => setRawMode(!isRawMode)}
		>
			<span class="flex h-5 w-5 shrink-0 items-center justify-center *:h-full *:w-full">
				<Code class="h-4 w-4" />
			</span>
			<span class="flex-1 truncate">markdown mode</span>
			<Switch size="sm" checked={isRawMode} />
		</button>
		{#if device.isMobile}
			<div class="my-1 h-px w-full bg-white/10"></div>
			<MenuItem onclick={handleShare}>
				{#snippet icon()}<Share class="h-4 w-4" />{/snippet}
				share
			</MenuItem>
			<MenuItem onclick={handleProperties}>
				{#snippet icon()}<InfoCircle class="h-4 w-4" />{/snippet}
				properties
			</MenuItem>
		{/if}
	</PopupMenu>
{/snippet}

{#if !note}
	<div class="mx-auto mt-10 max-w-3xl">
		<div
			class="rounded-container liquid-glass liquid-glass--frosted border border-white/10 p-5 text-sm text-white/70"
		>
			note not found.
		</div>
	</div>
{:else}
	<div class="flex w-full flex-1 flex-col" id="note-editor">
		<!-- header section -->
		<div class="rounded-container liquid-glass liquid-glass--frosted px-5 py-5 pb-6">
			<!-- title row -->
			<div class="mb-2 flex w-full items-center gap-2">
				<input
					class="min-w-0 flex-1 bg-transparent text-2xl font-medium text-white/95 outline-none placeholder:text-white/42"
					placeholder="title"
					bind:value={title}
					oninput={handleTitleInput}
				/>
			</div>

			<!-- meta row -->
			<div class="scrollbar-none flex w-full overflow-x-auto" use:wheelToHScroll>
				<div class="flex w-fit items-center gap-1 text-xs font-medium text-white/55">
					<div class="flex w-fit min-w-fit items-center gap-1 px-0.5 py-1">
						<Calendar class="h-3.5 w-3.5" strokeWidth="2" />
						<Timestamp timestamp={{ getTime: () => note.updatedAt }} mode="calendar" />
					</div>
					<span class="text-white/25">·</span>
					<div class="flex min-w-fit items-center gap-1 px-0.5 py-1">
						<Bars3BottomLeft class="h-3 w-3" strokeWidth="2" />
						<span>{wordCount} words</span>
						<span class="text-white/25">·</span>
						<span>{charCount} chars</span>
					</div>
					<span class="text-white/25">·</span>
					{#if isRawMode && rawDirty}
						<div
							class="flex min-w-fit items-center gap-1 px-0.5 py-1 text-amber-400/80"
						>
							<PencilSquare class="h-3 w-3" />
							<span>unsaved</span>
						</div>
					{:else}
						<div class="flex min-w-fit items-center gap-1 px-0.5 py-1">
							<Cloud class="h-3 w-3" />
							<span>autosaved</span>
						</div>
					{/if}
				</div>
			</div>

			<!-- viewers row (sessions editing this document) -->
			{#if peers.length > 0}
				<div
					class="scrollbar-none mt-3 flex items-center gap-3 overflow-x-auto pt-2"
					use:wheelToHScroll
				>
					{#each peers as peer, idx (peer.sessionId + ':' + idx)}
						{@const name = peer.userName || 'user'}
						{@const initials = getUserInitials(name)}
						{@const color = peer.color || '#85C1E9'}
						<!-- TODO: clicking on a viewer should open the User Profile modal once implemented -->
						<div class="flex shrink-0 items-center gap-2">
							<div
								class="flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold text-white shadow-sm"
								style:background-color={color}
							>
								{#if peer.avatarUrl}
									<img
										src={peer.avatarUrl}
										alt={name}
										class="h-full w-full rounded-full object-cover"
									/>
								{:else}
									{initials}
								{/if}
							</div>
							<span class="text-sm font-bold whitespace-nowrap text-white/70"
								>{name}</span
							>
						</div>
					{/each}
				</div>
			{/if}

			<!-- formatting toolbar row - hidden in raw mode -->
			<div
				class="formatting-toolbar overflow-hidden transition-all duration-200 ease-out {isRawMode
					? 'max-h-0 opacity-0'
					: 'max-h-20 opacity-100'}"
			>
				<div
					class="scrollbar-none mt-3 flex items-center justify-between overflow-x-auto border-t border-white/10 pt-3"
					use:wheelToHScroll
				>
					<div class="flex min-w-fit items-center gap-0.5">
						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleHeading(1)}
							title="heading 1"
						>
							<H1 class="h-4 w-4" />
						</button>
						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleHeading(2)}
							title="heading 2"
						>
							<H2 class="h-4 w-4" />
						</button>
						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleHeading(3)}
							title="heading 3"
						>
							<H3 class="h-4 w-4" />
						</button>

						<div class="mx-1 h-4 w-px bg-white/15"></div>

						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleBold()}
							title="bold (ctrl+b)"
						>
							<Bold class="h-4 w-4" />
						</button>
						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleItalic()}
							title="italic (ctrl+i)"
						>
							<Italic class="h-4 w-4" />
						</button>
						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleUnderline()}
							title="underline (ctrl+u)"
						>
							<Underline class="h-4 w-4" />
						</button>
						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleStrike()}
							title="strikethrough"
						>
							<Strikethrough class="h-4 w-4" />
						</button>

						<div class="mx-1 h-4 w-px bg-white/15"></div>

						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleBulletList()}
							title="bullet list"
						>
							<ListBullet class="h-4 w-4" />
						</button>
						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleOrderedList()}
							title="numbered list"
						>
							<NumberedList class="h-4 w-4" />
						</button>

						<div class="mx-1 h-4 w-px bg-white/15"></div>

						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleCode()}
							title="inline code"
						>
							<CodeBracket class="h-4 w-4" />
						</button>
						<button
							type="button"
							class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
							onclick={() => sharedEditor?.toggleCodeBlock()}
							title="code block"
						>
							<Code class="h-4 w-4" />
						</button>
					</div>
					<div></div>
				</div>
			</div>
		</div>

		<!-- content area -->
		<div
			class="relative flex w-full flex-1 flex-col px-3.5 pt-4 pb-6"
			id="note-content-container"
		>
			{#if isRawMode}
				<textarea
					bind:this={textareaEl}
					class="min-h-24 w-full flex-1 resize-none bg-transparent font-mono text-sm leading-relaxed text-white/90 outline-none placeholder:text-white/42"
					placeholder="write something... (Ctrl+S to save)"
					bind:value={content}
					oninput={handleRawInput}
					onkeydown={handleRawKeyDown}
				></textarea>
			{/if}

			<!-- SharedEditor stays mounted (hidden in raw mode) so Yjs stays connected -->
			<div class={isRawMode ? 'hidden' : 'flex flex-1 flex-col'}>
				<SharedEditor
					bind:this={sharedEditor}
					{documentId}
					initialContent={content}
					user={userInfo}
					placeholder="write something..."
					onchange={handleContentChange}
					onparticipantschange={(p) => (collabParticipants = p)}
					onsynced={handleSynced}
					class="min-h-24 flex-1 text-[0.95rem] leading-relaxed"
				/>
			</div>
		</div>
	</div>
{/if}
