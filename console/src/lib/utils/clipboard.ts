export async function copyToClipboard(text: string): Promise<boolean> {
	try {
		if (navigator.clipboard && window.isSecureContext) {
			await navigator.clipboard.writeText(text)
			return true
		}

		const textarea = document.createElement('textarea')
		textarea.value = text
		textarea.setAttribute('readonly', '')
		textarea.style.cssText = [
			'position:fixed',
			'top:-9999px',
			'left:-9999px',
			'width:1px',
			'height:1px',
			'padding:0',
			'border:0',
			'opacity:0',
		].join(';')

		const selection = document.getSelection()
		const selectedRange = selection?.rangeCount ? selection.getRangeAt(0) : null
		document.body.appendChild(textarea)
		textarea.focus()
		textarea.select()
		const copied = document.execCommand('copy')
		textarea.remove()

		if (selectedRange && selection) {
			selection.removeAllRanges()
			selection.addRange(selectedRange)
		}

		return copied
	} catch {
		return false
	}
}
