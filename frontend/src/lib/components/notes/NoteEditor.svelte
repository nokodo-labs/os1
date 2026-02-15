<script lang="ts">
	import RichTextEditor from '$lib/components/editor/RichTextEditor.svelte'
	import ArrowUturnLeft from '$lib/components/icons/ArrowUturnLeft.svelte'
	import ArrowUturnRight from '$lib/components/icons/ArrowUturnRight.svelte'
	import Bold from '$lib/components/icons/Bold.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import Code from '$lib/components/icons/Code.svelte'
	import CodeBracket from '$lib/components/icons/CodeBracket.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import H1 from '$lib/components/icons/H1.svelte'
	import H2 from '$lib/components/icons/H2.svelte'
	import H3 from '$lib/components/icons/H3.svelte'
	import Italic from '$lib/components/icons/Italic.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import NumberedList from '$lib/components/icons/NumberedList.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Strikethrough from '$lib/components/icons/Strikethrough.svelte'
	import Underline from '$lib/components/icons/Underline.svelte'
	import { MenuItem, Switch } from '$lib/components/primitives'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { notes } from '$lib/stores/notes.svelte'
	import { onDestroy } from 'svelte'
	import { scale } from 'svelte/transition'

	// storage format: markdown (in notes store)
	// normal mode: tiptap rich text editor (stores markdown via turndown)
	// markdown mode: textarea showing raw markdown source

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
	let content = $state('') // markdown string (source of truth)
	let isRawMode = $state(false)
	let menuOpen = $state(false)
	let menuButtonEl: HTMLButtonElement | null = $state(null)
	let menuEl: HTMLDivElement | null = $state(null)
	let saveTimeout: number | null = null
	let textareaEl: HTMLTextAreaElement | null = $state(null)
	let richEditor: RichTextEditor | null = $state(null)

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

	// sync state from store when note changes
	$effect(() => {
		const current = note
		if (!current) return
		if (current.id === lastNoteId) return
		lastNoteId = current.id

		isSyncingFromStore = true
		title = current.title
		content = current.content
		isRawMode = false
		menuOpen = false
		queueMicrotask(() => {
			isSyncingFromStore = false
		})
	})

	// inject island context actions
	$effect(() => {
		chrome.setContextActions(islandContextActions)
		return () => chrome.setContextActions(null)
	})

	// close menu on outside click/escape
	$effect(() => {
		if (!menuOpen) return

		const onPointerDown = (event: PointerEvent) => {
			const path = event.composedPath()
			if (menuEl && path.includes(menuEl)) return
			if (menuButtonEl && path.includes(menuButtonEl)) return
			menuOpen = false
		}

		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Escape') {
				event.preventDefault()
				menuOpen = false
			}
		}

		window.addEventListener('pointerdown', onPointerDown)
		window.addEventListener('keydown', onKeyDown)
		return () => {
			window.removeEventListener('pointerdown', onPointerDown)
			window.removeEventListener('keydown', onKeyDown)
		}
	})

	function scheduleSave(): void {
		if (saveTimeout !== null) window.clearTimeout(saveTimeout)
		saveTimeout = window.setTimeout(() => {
			saveTimeout = null
			void notes.update(noteId, { title, content })
		}, 200)
	}

	$effect(() => {
		// auto-save on edits
		void title
		void content
		if (!note) return
		if (isSyncingFromStore) return
		scheduleSave()
	})

	onDestroy(() => {
		if (saveTimeout !== null) window.clearTimeout(saveTimeout)
	})

	function handleContentChange(markdown: string): void {
		if (isSyncingFromStore) return
		content = markdown
	}

	function undo(): void {
		if (isRawMode) {
			// markdown mode doesn't have undo support for now
			return
		}
		richEditor?.undo()
	}

	function redo(): void {
		if (isRawMode) {
			// markdown mode doesn't have redo support for now
			return
		}
		richEditor?.redo()
	}

	function handleShare(): void {
		menuOpen = false
		// todo: implement share modal for notes
		console.log('share note:', noteId)
	}

	function setRawMode(next: boolean): void {
		if (next === isRawMode) return
		isRawMode = next
		if (next) {
			// switching to raw: show markdown in textarea
			requestAnimationFrame(() => textareaEl?.focus())
		} else {
			// switching to rich: tiptap will sync from content automatically
			queueMicrotask(() => richEditor?.focus())
		}
	}

	function handleProperties(): void {
		menuOpen = false
		// todo: implement properties panel for notes
		console.log('show properties for:', noteId)
	}

	// keyboard shortcuts for markdown mode
	function handleRawKeyDown(event: KeyboardEvent): void {
		const isMod = event.metaKey || event.ctrlKey
		if (isMod && event.key === 'z' && !event.shiftKey) {
			event.preventDefault()
			// native browser undo in textarea
		} else if (isMod && event.key === 'z' && event.shiftKey) {
			event.preventDefault()
			// native browser redo in textarea
		} else if (isMod && event.key === 'y') {
			event.preventDefault()
			// native browser redo in textarea
		}
	}
</script>

{#snippet islandContextActions()}
	<div class="relative flex items-center gap-1">
		{#if onBack && device.isMobile}
			<button
				type="button"
				class="rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]"
				onclick={() => onBack?.()}
				aria-label="back to notes"
			>
				<ChevronLeft class="h-5 w-5" strokeWidth="2" />
			</button>
		{/if}

		<!-- undo/redo buttons -->
		<button
			type="button"
			class="rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
			onclick={undo}
			disabled={isRawMode || !canUndo}
			aria-label="undo"
		>
			<ArrowUturnLeft class="h-5 w-5" />
		</button>
		<button
			type="button"
			class="rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
			onclick={redo}
			disabled={isRawMode || !canRedo}
			aria-label="redo"
		>
			<ArrowUturnRight class="h-5 w-5" />
		</button>

		<!-- 3-dot menu -->
		<div class="relative">
			<button
				type="button"
				bind:this={menuButtonEl}
				class="rounded-pill flex h-12 w-12 cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
				onclick={() => (menuOpen = !menuOpen)}
				aria-label="note options"
				aria-haspopup="menu"
				aria-expanded={menuOpen}
			>
				<EllipsisHorizontal class="h-5 w-5" />
			</button>

			{#if menuOpen}
				<div
					transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
					bind:this={menuEl}
					role="menu"
					class="liquid-metal rounded-container animate-popup-right absolute top-full left-0 z-50 mt-2 min-w-44 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)]"
				>
					<button
						type="button"
						role="menuitemcheckbox"
						aria-checked={isRawMode}
						class="rounded-pill flex w-full cursor-pointer items-center gap-3 border-none bg-transparent px-3 py-2 text-left text-sm text-white/85 transition-all duration-150 hover:bg-white/10 hover:text-white"
						onclick={() => setRawMode(!isRawMode)}
					>
						<span
							class="flex h-5 w-5 shrink-0 items-center justify-center *:h-full *:w-full"
						>
							<Code class="h-4 w-4" />
						</span>
						<span class="flex-1 truncate">markdown mode</span>
						<Switch size="sm" checked={isRawMode} />
					</button>
					<div class="my-1 h-px w-full bg-white/10"></div>
					<MenuItem onclick={handleShare}>
						{#snippet icon()}<Share class="h-4 w-4" />{/snippet}
						share
					</MenuItem>
					<MenuItem onclick={handleProperties}>
						{#snippet icon()}<CodeBracket class="h-4 w-4" />{/snippet}
						properties
					</MenuItem>
				</div>
			{/if}
		</div>
	</div>
{/snippet}

{#if !note}
	<div class="mx-auto mt-10 max-w-3xl">
		<div class="rounded-container border border-white/10 bg-white/5 p-5 text-sm text-white/70">
			note not found.
		</div>
	</div>
{:else}
	<div class="w-full" id="note-editor">
		<div class="flex w-full flex-col">
			<!-- header section with background -->
			<div class="rounded-container border border-white/10 bg-white/5 px-3 py-5 pb-6">
				<!-- title row -->
				<div class="mb-2 flex w-full items-center">
					<input
						class="w-full bg-transparent text-2xl font-medium text-white/95 outline-none placeholder:text-white/42"
						placeholder="title"
						bind:value={title}
					/>
				</div>

				<!-- meta row -->
				<div
					class="scrollbar-none flex w-full overflow-x-auto"
					onwheel={(event) => {
						if (event.deltaY === 0) return
						event.preventDefault()
						const target = event.currentTarget
						if (target instanceof HTMLElement) target.scrollLeft += event.deltaY
					}}
				>
					<div class="flex w-fit items-center gap-1 text-xs font-medium text-white/55">
						<div class="flex w-fit min-w-fit items-center gap-1 px-0.5 py-1">
							<Calendar class="h-3.5 w-3.5" strokeWidth="2" />
							<Timestamp
								timestamp={{ getTime: () => note.updatedAt }}
								mode="calendar"
							/>
						</div>
						<div class="flex min-w-fit items-center gap-2 px-1">
							<span>{wordCount} words</span>
							<span>·</span>
							<span>{charCount} chars</span>
							<span>·</span>
							<span>autosaved</span>
						</div>
					</div>
				</div>

				<!-- formatting toolbar row - uses max-height reveal animation -->
				<div
					class="formatting-toolbar overflow-hidden transition-all duration-200 ease-out {isRawMode
						? 'max-h-0 opacity-0'
						: 'max-h-20 opacity-100'}"
				>
					<div
						class="mt-3 flex items-center justify-between border-t border-white/10 pt-3"
					>
						<div class="flex items-center gap-0.5">
							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleHeading(1)}
								title="heading 1"
							>
								<H1 class="h-4 w-4" />
							</button>
							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleHeading(2)}
								title="heading 2"
							>
								<H2 class="h-4 w-4" />
							</button>
							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleHeading(3)}
								title="heading 3"
							>
								<H3 class="h-4 w-4" />
							</button>

							<div class="mx-1 h-4 w-px bg-white/15"></div>

							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleBold()}
								title="bold (ctrl+b)"
							>
								<Bold class="h-4 w-4" />
							</button>
							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleItalic()}
								title="italic (ctrl+i)"
							>
								<Italic class="h-4 w-4" />
							</button>
							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleUnderline()}
								title="underline (ctrl+u)"
							>
								<Underline class="h-4 w-4" />
							</button>
							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleStrike()}
								title="strikethrough"
							>
								<Strikethrough class="h-4 w-4" />
							</button>

							<div class="mx-1 h-4 w-px bg-white/15"></div>

							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleBulletList()}
								title="bullet list"
							>
								<ListBullet class="h-4 w-4" />
							</button>
							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleOrderedList()}
								title="numbered list"
							>
								<NumberedList class="h-4 w-4" />
							</button>

							<div class="mx-1 h-4 w-px bg-white/15"></div>

							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleCode()}
								title="inline code"
							>
								<CodeBracket class="h-4 w-4" />
							</button>
							<button
								type="button"
								class="rounded-pill cursor-pointer p-1.5 text-white transition hover:bg-white/8"
								onclick={() => richEditor?.toggleCodeBlock()}
								title="code block"
							>
								<Code class="h-4 w-4" />
							</button>
						</div>
						<div></div>
					</div>
				</div>
			</div>

			<!-- content area (no background) -->
			<div
				class="relative w-full flex-1 overflow-auto px-3.5 pt-4 pb-20"
				id="note-content-container"
			>
				{#if isRawMode}
					<textarea
						bind:this={textareaEl}
						class="min-h-[56vh] w-full resize-none bg-transparent font-mono text-sm leading-relaxed text-white/90 outline-none placeholder:text-white/42"
						placeholder="write something..."
						bind:value={content}
						onkeydown={handleRawKeyDown}
					></textarea>
				{:else}
					<RichTextEditor
						bind:this={richEditor}
						value={content}
						placeholder="write something..."
						onchange={handleContentChange}
						class="min-h-[56vh] text-[0.95rem] leading-relaxed"
					/>
				{/if}
			</div>
		</div>
	</div>
{/if}
