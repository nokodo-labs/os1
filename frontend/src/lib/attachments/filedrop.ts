/**
 * file drop gesture: files dragged onto the node are handed to `onDrop`.
 *
 * only a drag that actually carries files arms it, so a text selection or an
 * in-app row reorder passing over the same node is left alone. `dragover` must
 * be prevented or the browser refuses the drop and opens the file instead.
 *
 * enter/leave are counted, because moving between the node's children fires a
 * leave before the next enter - `onActiveChange` would otherwise flicker.
 */

import type { Attachment } from 'svelte/attachments'

export interface FileDropOptions {
	onDrop: (files: FileList) => void
	/** true while a file drag is over the node, for the drop-target visual. */
	onActiveChange?: (active: boolean) => void
	disabled?: boolean
}

function carriesFiles(transfer: DataTransfer | null): boolean {
	return transfer !== null && Array.from(transfer.types).includes('Files')
}

export function filedrop(options: FileDropOptions): Attachment<HTMLElement> {
	return (node) => {
		if (options.disabled) return
		let depth = 0

		function clearActive(): void {
			if (depth === 0) return
			depth = 0
			options.onActiveChange?.(false)
		}

		function onDragEnter(event: DragEvent): void {
			if (!carriesFiles(event.dataTransfer)) return
			event.preventDefault()
			depth += 1
			if (depth === 1) options.onActiveChange?.(true)
		}

		function onDragOver(event: DragEvent): void {
			if (!carriesFiles(event.dataTransfer)) return
			event.preventDefault()
			if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
		}

		function onDragLeave(event: DragEvent): void {
			if (!carriesFiles(event.dataTransfer)) return
			depth = Math.max(0, depth - 1)
			if (depth === 0) options.onActiveChange?.(false)
		}

		function onDrop(event: DragEvent): void {
			if (!carriesFiles(event.dataTransfer)) return
			event.preventDefault()
			const files = event.dataTransfer?.files ?? null
			clearActive()
			if (files && files.length > 0) options.onDrop(files)
		}

		node.addEventListener('dragenter', onDragEnter)
		node.addEventListener('dragover', onDragOver)
		node.addEventListener('dragleave', onDragLeave)
		node.addEventListener('drop', onDrop)

		return () => {
			clearActive()
			node.removeEventListener('dragenter', onDragEnter)
			node.removeEventListener('dragover', onDragOver)
			node.removeEventListener('dragleave', onDragLeave)
			node.removeEventListener('drop', onDrop)
		}
	}
}
