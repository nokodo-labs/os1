<script lang="ts">
	import { CollaborationProvider, type DocParticipant } from '$lib/collaboration'
	import { Editor, Extension } from '@tiptap/core'
	import Placeholder from '@tiptap/extension-placeholder'
	import Typography from '@tiptap/extension-typography'
	import { StarterKit } from '@tiptap/starter-kit'
	import { marked } from 'marked'
	import { keymap } from 'prosemirror-keymap'
	import { onDestroy, onMount } from 'svelte'
	import TurndownService from 'turndown'
	import {
		yCursorPlugin,
		redo as yRedo,
		ySyncPlugin,
		undo as yUndo,
		yUndoPlugin,
	} from 'y-prosemirror'

	/**
	 * collaborative rich text editor backed by Yjs CRDT.
	 *
	 * generic: works for notes, threads, or any document type.
	 * content is synced in real-time between all editors sharing the same
	 * documentId. the Yjs doc is the single source of truth - there is
	 * no external `value` prop. markdown is emitted via `onchange` for
	 * persistence (auto-save).
	 */

	interface Props {
		/** document room identifier (e.g. "note:{id}", "thread:{id}") */
		documentId: string
		/** markdown to populate if the Yjs doc is empty on first sync */
		initialContent?: string
		/** user info for cursor labels and awareness */
		user?: { id: string; name: string; avatarUrl?: string | null }
		placeholder?: string
		editable?: boolean
		class?: string
		/** called on content change with markdown string */
		onchange?: (markdown: string) => void
		/** called when participants join/leave */
		onparticipantschange?: (participants: DocParticipant[]) => void
		/** called when initial Yjs sync completes */
		onsynced?: () => void
		onfocus?: () => void
		onblur?: () => void
	}

	let {
		documentId,
		initialContent = '',
		user,
		placeholder = 'write something...',
		editable = true,
		class: className = '',
		onchange,
		onparticipantschange,
		onsynced,
		onfocus,
		onblur,
	}: Props = $props()

	// turndown config (html -> markdown)
	const turndown = new TurndownService({
		headingStyle: 'atx',
		codeBlockStyle: 'fenced',
	})
	turndown.addRule('underline', {
		filter: ['u'],
		replacement: (inner: string) => (inner ? `<u>${inner}</u>` : ''),
	})

	let editorElement: HTMLDivElement | null = $state(null)
	let editorState = $state<{ editor: Editor | null }>({ editor: null })
	let provider: CollaborationProvider | null = null
	let isSynced = $state(false)
	let lastEmittedMarkdown = ''

	function markdownToHtml(md: string): string {
		return String(marked.parse(md, { gfm: true, breaks: true }))
	}

	function htmlToMarkdown(html: string): string {
		return turndown.turndown(html)
	}

	// sync editable state
	$effect(() => {
		editorState.editor?.setEditable(editable)
	})

	onMount(() => {
		if (!editorElement) return

		// create collaboration provider (with user info for cursor awareness)
		provider = new CollaborationProvider({
			documentId,
			user,
			onSynced: () => {
				isSynced = true
				// if Yjs doc is empty AND we have initial content, migrate it
				const fragment = provider?.doc.getXmlFragment('content')
				if (fragment && fragment.length === 0 && initialContent) {
					const html = markdownToHtml(initialContent)
					editorState.editor?.commands.setContent(html)
				}
				onsynced?.()
			},
			onParticipantsChange: (p) => {
				onparticipantschange?.(p)
			},
		})

		const fragment = provider.doc.getXmlFragment('content')
		const awareness = provider.awareness

		// custom cursor builder: renders each remote user's color for the caret + label.
		// yCursorPlugin already skips the local awareness clientID, so our own
		// cursor is never rendered. for the same user on a different session
		// (different tab/device), we DO show the cursor.
		function cursorBuilder(userState: Record<string, string> | null): HTMLElement {
			const el = document.createElement('span')
			const color = userState?.color || 'orange'
			const name = userState?.name || 'anonymous'

			// thin caret line - must be inline styles so they work even before
			// the plugin adds .ProseMirror-yjs-cursor to the element
			el.style.borderLeft = `1px solid ${color}`
			el.style.borderRight = `1px solid ${color}`
			el.style.position = 'relative'
			el.style.marginLeft = '-1px'
			el.style.marginRight = '-1px'
			el.style.wordBreak = 'normal'
			el.style.pointerEvents = 'none'

			const label = document.createElement('div')
			label.textContent = name
			label.style.position = 'absolute'
			label.style.top = '-1.05em'
			label.style.left = '-1px'
			label.style.fontSize = '11px'
			label.style.fontWeight = '500'
			label.style.backgroundColor = color
			label.style.color = 'white'
			label.style.padding = '0 3px'
			label.style.borderRadius = '3px 3px 3px 0'
			label.style.whiteSpace = 'nowrap'
			label.style.lineHeight = '1.4'
			label.style.userSelect = 'none'
			el.appendChild(label)
			return el
		}

		// Yjs collaboration + cursors as a TipTap extension
		const yjsExtension = Extension.create({
			name: 'yjs-collaboration',
			addProseMirrorPlugins() {
				return [
					ySyncPlugin(fragment),
					yCursorPlugin(awareness as any, { cursorBuilder }),
					yUndoPlugin(),
					keymap({
						'Mod-z': yUndo,
						'Mod-y': yRedo,
						'Mod-Shift-z': yRedo,
					}),
				]
			},
		})

		editorState.editor = new Editor({
			element: editorElement,
			extensions: [
				StarterKit.configure({
					heading: { levels: [1, 2, 3] },
					undoRedo: false, // yUndoPlugin replaces built-in undo/redo
				}),
				Typography,
				Placeholder.configure({
					placeholder,
					showOnlyWhenEditable: true,
				}),
				yjsExtension,
			],
			editable,
			onTransaction: ({ editor }) => {
				editorState = { editor }
			},
			onUpdate: ({ editor }) => {
				const html = editor.getHTML()
				const md = htmlToMarkdown(html)
				if (md !== lastEmittedMarkdown) {
					lastEmittedMarkdown = md
					onchange?.(md)
				}
			},
			onFocus: () => onfocus?.(),
			onBlur: () => onblur?.(),
		})

		provider.connect()
	})

	onDestroy(() => {
		editorState.editor?.destroy()
		provider?.disconnect()
	})

	// --- public API (matches RichTextEditor interface) ---

	export function getEditor(): Editor | null {
		return editorState.editor
	}

	export function getProvider(): CollaborationProvider | null {
		return provider
	}

	export function focus(): void {
		editorState.editor?.commands.focus()
	}

	export function blur(): void {
		editorState.editor?.commands.blur()
	}

	export function toggleBold(): void {
		editorState.editor?.chain().focus().toggleBold().run()
	}

	export function toggleItalic(): void {
		editorState.editor?.chain().focus().toggleItalic().run()
	}

	export function toggleUnderline(): void {
		editorState.editor?.chain().focus().toggleUnderline().run()
	}

	export function toggleStrike(): void {
		editorState.editor?.chain().focus().toggleStrike().run()
	}

	export function toggleCode(): void {
		editorState.editor?.chain().focus().toggleCode().run()
	}

	export function toggleCodeBlock(): void {
		editorState.editor?.chain().focus().toggleCodeBlock().run()
	}

	export function toggleHeading(level: 1 | 2 | 3): void {
		editorState.editor?.chain().focus().toggleHeading({ level }).run()
	}

	export function toggleBulletList(): void {
		editorState.editor?.chain().focus().toggleBulletList().run()
	}

	export function toggleOrderedList(): void {
		editorState.editor?.chain().focus().toggleOrderedList().run()
	}

	export function setParagraph(): void {
		editorState.editor?.chain().focus().setParagraph().run()
	}

	export function undo(): void {
		editorState.editor?.chain().focus().undo().run()
	}

	export function redo(): void {
		editorState.editor?.chain().focus().redo().run()
	}

	export function isActive(name: string, attributes?: Record<string, unknown>): boolean {
		return editorState.editor?.isActive(name, attributes) ?? false
	}

	/** get the current content as markdown */
	export function getMarkdown(): string {
		const html = editorState.editor?.getHTML() ?? ''
		return htmlToMarkdown(html)
	}
</script>

<div
	bind:this={editorElement}
	class="shared-editor prose prose-invert max-w-none {className}"
></div>

<style>
	/* --- editor chrome --- */
	.shared-editor {
		outline: none;
	}

	.shared-editor :global(.tiptap) {
		outline: none;
		min-height: 100%;
	}

	.shared-editor :global(.tiptap:focus) {
		outline: none;
	}

	/* placeholder */
	.shared-editor :global(.tiptap p.is-editor-empty:first-child::before) {
		content: attr(data-placeholder);
		color: rgba(255, 255, 255, 0.35);
		pointer-events: none;
		float: left;
		height: 0;
	}

	/* --- rich text styling (dark theme) --- */
	.shared-editor :global(h1) {
		color: rgba(255, 255, 255, 0.95);
		font-size: 1.75rem;
		font-weight: 600;
		margin-top: 1.5rem;
		margin-bottom: 0.75rem;
	}

	.shared-editor :global(h2) {
		color: rgba(255, 255, 255, 0.92);
		font-size: 1.4rem;
		font-weight: 600;
		margin-top: 1.25rem;
		margin-bottom: 0.5rem;
	}

	.shared-editor :global(h3) {
		color: rgba(255, 255, 255, 0.9);
		font-size: 1.15rem;
		font-weight: 600;
		margin-top: 1rem;
		margin-bottom: 0.5rem;
	}

	.shared-editor :global(p) {
		color: rgba(255, 255, 255, 0.9);
		margin-top: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.shared-editor :global(ul),
	.shared-editor :global(ol) {
		color: rgba(255, 255, 255, 0.9);
		padding-left: 1.5rem;
		margin-top: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.shared-editor :global(ul) {
		list-style-type: disc;
	}

	.shared-editor :global(ol) {
		list-style-type: decimal;
	}

	.shared-editor :global(li) {
		margin-top: 0.25rem;
		margin-bottom: 0.25rem;
	}

	.shared-editor :global(code) {
		background: rgba(255, 255, 255, 0.1);
		border-radius: 0.25rem;
		padding: 0.125rem 0.375rem;
		font-size: 0.875em;
		color: rgba(255, 255, 255, 0.95);
	}

	.shared-editor :global(pre) {
		background: color-mix(in oklch, var(--accent-primary, #a855f7) 10%, transparent);
		border-radius: 0.5rem;
		padding: 0.75rem 1rem;
		margin-top: 0.75rem;
		margin-bottom: 0.75rem;
		overflow-x: auto;
	}

	.shared-editor :global(pre code) {
		background: transparent;
		padding: 0;
		font-size: 0.875rem;
	}

	.shared-editor :global(blockquote) {
		border-left: 3px solid rgba(255, 255, 255, 0.3);
		padding-left: 1rem;
		margin-left: 0;
		color: rgba(255, 255, 255, 0.75);
		font-style: italic;
	}

	.shared-editor :global(strong) {
		color: rgba(255, 255, 255, 0.95);
		font-weight: 600;
	}

	.shared-editor :global(em) {
		color: inherit;
	}

	.shared-editor :global(u) {
		text-decoration: underline;
	}

	.shared-editor :global(s) {
		text-decoration: line-through;
		color: rgba(255, 255, 255, 0.6);
	}

	.shared-editor :global(hr) {
		border: none;
		border-top: 1px solid rgba(255, 255, 255, 0.15);
		margin: 1.5rem 0;
	}

	.shared-editor :global(a) {
		color: rgba(140, 180, 255, 0.9);
		text-decoration: underline;
	}

	.shared-editor :global(a:hover) {
		color: rgba(160, 200, 255, 1);
	}

	/* --- yjs remote cursor caret --- */
	.shared-editor :global(.ProseMirror > .ProseMirror-yjs-cursor:first-child) {
		margin-top: 16px;
	}

	.shared-editor :global(.ProseMirror-yjs-cursor) {
		position: relative;
		margin-left: -1px;
		margin-right: -1px;
		border-left: 1px solid black;
		border-right: 1px solid black;
		border-color: orange;
		word-break: normal;
		pointer-events: none;
	}

	/* username label above the caret */
	.shared-editor :global(.ProseMirror-yjs-cursor > div) {
		position: absolute;
		top: -1.05em;
		left: -1px;
		font-size: 11px;
		font-weight: 500;
		background-color: rgb(250, 129, 0);
		user-select: none;
		color: white;
		padding: 0 3px;
		border-radius: 3px 3px 3px 0;
		white-space: nowrap;
		line-height: 1.4;
	}
</style>
