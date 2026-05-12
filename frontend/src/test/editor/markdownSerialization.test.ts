import {
	createMarkdownTurndown,
	editorHtmlToMarkdown,
	markdownToEditorHtml,
} from '$lib/editor/markdownSerialization'
import { describe, expect, it } from 'vitest'

describe('markdownSerialization', () => {
	it('preserves extra blank lines across markdown and editor html', () => {
		const source = 'alpha\n\n\nbravo\n\n\n\ncharlie'
		const html = markdownToEditorHtml(source)

		expect(editorHtmlToMarkdown(createMarkdownTurndown(), html)).toBe(source)
	})

	it('serializes consecutive empty editor paragraphs as consecutive newlines', () => {
		const html = '<p>alpha</p><p></p><p></p><p>bravo</p>'

		expect(editorHtmlToMarkdown(createMarkdownTurndown(), html)).toBe('alpha\n\n\n\nbravo')
	})
})
