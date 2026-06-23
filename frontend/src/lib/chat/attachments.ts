/**
 * attachment upload utilities for the chat input flow.
 *
 * types are defined in $lib/chat/types.ts.
 * file operations (delete, download, blob fetch) live in $lib/stores/files.svelte.ts.
 *
 * two-step process: upload file -> get file_id -> include in run content parts.
 */

import { api } from '$lib/api/client'
import type {
	AttachmentMediaCategory,
	PendingAttachment,
	RunModifiers,
	ToolChoiceValue,
} from '$lib/chat/types'
import { categorizeMediaType } from '$lib/stores/files.svelte'

// re-export types for backward compatibility
export type { AttachmentMediaCategory, PendingAttachment, RunModifiers, ToolChoiceValue }

// re-export categorizeMediaType for callers that imported from here
export { categorizeMediaType }

/** upload a single file to the backend and return a PendingAttachment */
export async function uploadFile(file: File): Promise<PendingAttachment> {
	const formData = new FormData()
	formData.append('file', file)

	const { data, error } = await api.POST('/v1/files/upload', {
		// openapi-fetch does not support multipart natively via body typing,
		// so we pass the FormData directly via the fetch init
		body: formData as never,
	})

	if (error || !data) {
		const msg =
			error && typeof error === 'object' && 'detail' in error
				? String((error as Record<string, unknown>).detail)
				: 'file upload failed'
		throw new Error(msg)
	}

	const uploaded = data as Record<string, unknown>
	const fileId = String(uploaded.id ?? '')
	const filename = String(uploaded.filename ?? file.name)
	const mediaType = String(uploaded.media_type ?? file.type ?? 'application/octet-stream')
	const category = categorizeMediaType(mediaType)

	return {
		fileId,
		resourceType: 'file',
		filename,
		mediaType,
		category,
		previewUrl:
			category === 'image' || category === 'video' ? URL.createObjectURL(file) : undefined,
		source: 'upload',
	}
}

/** revoke all preview object URLs from a list of attachments */
export function revokePreviewUrls(attachments: PendingAttachment[]): void {
	for (const att of attachments) {
		if (att.previewUrl) URL.revokeObjectURL(att.previewUrl)
	}
}

/** derive tool_choice from run modifiers (null = default/auto) */
export function deriveToolChoice(modifiers: RunModifiers): ToolChoiceValue | null {
	if (modifiers.webSearch) return 'agentic_web_search'
	if (modifiers.thinkLonger) return 'think'
	if (modifiers.generateImage) return 'generate_image'
	return null
}
