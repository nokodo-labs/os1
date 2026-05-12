import { marked } from 'marked'
import TurndownService from 'turndown'

const BLANK_LINE_SENTINEL = String.fromCharCode(8203)
const BLANK_LINE_HTML = `<p>${BLANK_LINE_SENTINEL}</p>`
const BLANK_LINE_TOKEN = '%%NOKODO_PRESERVED_BLANK_LINE%%'
const BLANK_LINE_TOKEN_PATTERN = /%%NOKODO_PRESERVED_BLANK_LINE%%/g
const PRESERVED_BLANK_LINE_RUN_PATTERN = /\n\n(?:%%NOKODO_PRESERVED_BLANK_LINE%%)+\n\n/g

function isBlankParagraph(node: HTMLElement): boolean {
	if (node.nodeName !== 'P') return false
	const text = node.textContent ?? ''
	if (text === BLANK_LINE_SENTINEL) return true
	if (text.length > 0) return false
	return [...node.childNodes].every((child) => child.nodeName === 'BR')
}

function injectPreservedBlankLines(markdown: string): string {
	return markdown.replace(/\n{3,}/g, (match) => {
		const extraBlankLineCount = match.length - 2
		return `\n\n${BLANK_LINE_HTML.repeat(extraBlankLineCount)}\n\n`
	})
}

function restorePreservedBlankLines(markdown: string): string {
	return markdown
		.replace(PRESERVED_BLANK_LINE_RUN_PATTERN, (match) => {
			const tokenCount = match.match(BLANK_LINE_TOKEN_PATTERN)?.length ?? 0
			return '\n'.repeat(tokenCount + 2)
		})
		.replace(BLANK_LINE_TOKEN_PATTERN, '\n')
}

export function createMarkdownTurndown(): TurndownService {
	const turndown = new TurndownService({
		headingStyle: 'atx',
		codeBlockStyle: 'fenced',
		blankReplacement: (_content, node) => (node.nodeName === 'P' ? BLANK_LINE_TOKEN : ''),
	})

	turndown.addRule('preservedBlankParagraph', {
		filter: (node) => isBlankParagraph(node),
		replacement: () => BLANK_LINE_TOKEN,
	})
	turndown.addRule('underline', {
		filter: ['u'],
		replacement: (inner: string) => (inner ? `<u>${inner}</u>` : ''),
	})

	return turndown
}

export function markdownToEditorHtml(markdown: string): string {
	return String(marked.parse(injectPreservedBlankLines(markdown), { gfm: true, breaks: true }))
}

export function editorHtmlToMarkdown(turndown: TurndownService, html: string): string {
	return restorePreservedBlankLines(turndown.turndown(html))
}
