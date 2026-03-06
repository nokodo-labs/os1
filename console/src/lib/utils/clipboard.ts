/**
 * Copy text to clipboard. Uses Clipboard API when available (secure context),
 * falls back to execCommand for environments where the API is blocked (e.g.
 * inside a focus-trapped dialog).
 *
 * Returns true on success, false on failure.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
	try {
		if (navigator.clipboard && window.isSecureContext) {
			await navigator.clipboard.writeText(text)
		} else {
			const el = document.createElement('textarea')
			el.value = text
			el.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none'
			document.body.appendChild(el)
			el.select()
			document.execCommand('copy')
			el.remove()
		}
		return true
	} catch {
		return false
	}
}
