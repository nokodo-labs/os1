/**
 * @param {string} filename
 * @param {string} content
 * @param {string} mimeType
 */
export const save = (filename, content, mimeType) => {
	const blob = new Blob([content], { type: mimeType })
	const url = URL.createObjectURL(blob)
	const link = document.createElement('a')
	link.href = url
	link.download = filename
	document.body.appendChild(link)
	link.click()
	document.body.removeChild(link)
	URL.revokeObjectURL(url)
}
