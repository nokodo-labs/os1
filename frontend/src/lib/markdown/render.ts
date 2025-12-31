import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({
	gfm: true,
	breaks: true,
})

function escapeHtml(text: string): string {
	return text
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&#39;')
}

export function renderMarkdownToHtml(markdown: string): string {
	if (!markdown) return ''
	if (typeof window === 'undefined') {
		return `<p>${escapeHtml(markdown)}</p>`
	}

	const raw = marked.parse(markdown, { async: false }) as string
	return DOMPurify.sanitize(raw, {
		USE_PROFILES: { html: true },
	})
}
