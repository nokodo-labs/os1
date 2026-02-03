<script lang="ts">
	import { Editor } from '@tiptap/core'
	import Placeholder from '@tiptap/extension-placeholder'
	import Typography from '@tiptap/extension-typography'
	import Underline from '@tiptap/extension-underline'
	import { StarterKit } from '@tiptap/starter-kit'
	import { marked } from 'marked'
	import { onDestroy, onMount } from 'svelte'
	import TurndownService from 'turndown'

	// storage: markdown
	// on load: markdown -> html (via marked) -> tiptap
	// on edit: tiptap html -> markdown (via turndown) -> emit

	interface Props {
		/** markdown content (source of truth) */
		value?: string
		/** placeholder text when empty */
		placeholder?: string
		/** whether the editor is editable */
		editable?: boolean
		/** additional css classes for the editor wrapper */
		class?: string
		/** called when content changes, receives markdown string */
		onchange?: (markdown: string) => void
		/** called when editor gains focus */
		onfocus?: () => void
		/** called when editor loses focus */
		onblur?: () => void
	}

	let {
		value = '',
		placeholder = 'write something...',
		editable = true,
		class: className = '',
		onchange,
		onfocus,
		onblur,
	}: Props = $props()

	// turndown config (html -> markdown)
	const turndown = new TurndownService({
		headingStyle: 'atx',
		codeBlockStyle: 'fenced',
	})
	// preserve underline as html since markdown has no underline syntax
	turndown.addRule('underline', {
		filter: ['u'],
		replacement: (inner: string) => (inner ? `<u>${inner}</u>` : ''),
	})

	let editorElement: HTMLDivElement | null = $state(null)
	let editorState = $state<{ editor: Editor | null }>({ editor: null })
	let isSyncing = false
	let lastEmittedMarkdown = ''

	// convert markdown to html for tiptap
	function markdownToHtml(md: string): string {
		return String(marked.parse(md, { gfm: true, breaks: true }))
	}

	// convert html to markdown for storage
	function htmlToMarkdown(html: string): string {
		return turndown.turndown(html)
	}

	// sync tiptap content from external value change
	$effect(() => {
		const editor = editorState.editor
		if (!editor) return
		if (isSyncing) return

		// only sync if value differs from what we last emitted
		if (value !== lastEmittedMarkdown) {
			isSyncing = true
			const html = markdownToHtml(value)
			editor.commands.setContent(html, { emitUpdate: false })
			lastEmittedMarkdown = value
			queueMicrotask(() => {
				isSyncing = false
			})
		}
	})

	// sync editable state
	$effect(() => {
		editorState.editor?.setEditable(editable)
	})

	onMount(() => {
		if (!editorElement) return

		const initialHtml = markdownToHtml(value)
		lastEmittedMarkdown = value

		editorState.editor = new Editor({
			element: editorElement,
			extensions: [
				StarterKit.configure({
					heading: { levels: [1, 2, 3] },
				}),
				Underline,
				Typography,
				Placeholder.configure({
					placeholder,
					showOnlyWhenEditable: true,
				}),
			],
			content: initialHtml,
			editable,
			onTransaction: ({ editor }) => {
				// force re-render so editor.isActive works
				editorState = { editor }
			},
			onUpdate: ({ editor }) => {
				if (isSyncing) return
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
	})

	onDestroy(() => {
		editorState.editor?.destroy()
	})

	// expose editor instance and commands for external use
	export function getEditor(): Editor | null {
		return editorState.editor
	}

	export function focus(): void {
		editorState.editor?.commands.focus()
	}

	export function blur(): void {
		editorState.editor?.commands.blur()
	}

	// formatting commands
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

	// check if format is active
	export function isActive(name: string, attributes?: Record<string, unknown>): boolean {
		return editorState.editor?.isActive(name, attributes) ?? false
	}

	export function canUndo(): boolean {
		return editorState.editor?.can().undo() ?? false
	}

	export function canRedo(): boolean {
		return editorState.editor?.can().redo() ?? false
	}
</script>

<div
	bind:this={editorElement}
	class="rich-text-editor prose prose-invert max-w-none {className}"
></div>

<style>
	.rich-text-editor {
		outline: none;
	}

	.rich-text-editor :global(.tiptap) {
		outline: none;
		min-height: 100%;
	}

	.rich-text-editor :global(.tiptap p.is-editor-empty:first-child::before) {
		content: attr(data-placeholder);
		color: rgba(255, 255, 255, 0.35);
		pointer-events: none;
		float: left;
		height: 0;
	}

	.rich-text-editor :global(.tiptap:focus) {
		outline: none;
	}

	/* prose styling overrides for dark theme */
	.rich-text-editor :global(h1) {
		color: rgba(255, 255, 255, 0.95);
		font-size: 1.75rem;
		font-weight: 600;
		margin-top: 1.5rem;
		margin-bottom: 0.75rem;
	}

	.rich-text-editor :global(h2) {
		color: rgba(255, 255, 255, 0.92);
		font-size: 1.4rem;
		font-weight: 600;
		margin-top: 1.25rem;
		margin-bottom: 0.5rem;
	}

	.rich-text-editor :global(h3) {
		color: rgba(255, 255, 255, 0.9);
		font-size: 1.15rem;
		font-weight: 600;
		margin-top: 1rem;
		margin-bottom: 0.5rem;
	}

	.rich-text-editor :global(p) {
		color: rgba(255, 255, 255, 0.9);
		margin-top: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.rich-text-editor :global(ul),
	.rich-text-editor :global(ol) {
		color: rgba(255, 255, 255, 0.9);
		padding-left: 1.5rem;
		margin-top: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.rich-text-editor :global(li) {
		margin-top: 0.25rem;
		margin-bottom: 0.25rem;
	}

	.rich-text-editor :global(code) {
		background: rgba(255, 255, 255, 0.1);
		border-radius: 0.25rem;
		padding: 0.125rem 0.375rem;
		font-size: 0.875em;
		color: rgba(255, 255, 255, 0.95);
	}

	.rich-text-editor :global(pre) {
		background: rgba(0, 0, 0, 0.3);
		border-radius: 0.5rem;
		padding: 0.75rem 1rem;
		margin-top: 0.75rem;
		margin-bottom: 0.75rem;
		overflow-x: auto;
	}

	.rich-text-editor :global(pre code) {
		background: transparent;
		padding: 0;
		font-size: 0.875rem;
	}

	.rich-text-editor :global(blockquote) {
		border-left: 3px solid rgba(255, 255, 255, 0.3);
		padding-left: 1rem;
		margin-left: 0;
		color: rgba(255, 255, 255, 0.75);
		font-style: italic;
	}

	.rich-text-editor :global(strong) {
		color: rgba(255, 255, 255, 0.95);
		font-weight: 600;
	}

	.rich-text-editor :global(em) {
		color: inherit;
	}

	.rich-text-editor :global(u) {
		text-decoration: underline;
	}

	.rich-text-editor :global(s) {
		text-decoration: line-through;
		color: rgba(255, 255, 255, 0.6);
	}

	.rich-text-editor :global(hr) {
		border: none;
		border-top: 1px solid rgba(255, 255, 255, 0.15);
		margin: 1.5rem 0;
	}

	.rich-text-editor :global(a) {
		color: rgba(140, 180, 255, 0.9);
		text-decoration: underline;
	}

	.rich-text-editor :global(a:hover) {
		color: rgba(160, 200, 255, 1);
	}
</style>
