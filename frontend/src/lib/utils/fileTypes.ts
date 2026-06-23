const KNOWN_MIME_LABELS: Record<string, string> = {
	'application/pdf': 'PDF document',
	'application/rtf': 'rich text document',
	'application/msword': 'Word document',
	'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word document',
	'application/vnd.ms-excel': 'Excel spreadsheet',
	'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel spreadsheet',
	'application/vnd.ms-powerpoint': 'PowerPoint presentation',
	'application/vnd.openxmlformats-officedocument.presentationml.presentation':
		'PowerPoint presentation',
	'application/zip': 'zip archive',
	'application/x-zip-compressed': 'zip archive',
	'application/json': 'JSON file',
	'application/xml': 'XML file',
	'application/yaml': 'YAML file',
	'application/x-yaml': 'YAML file',
	'text/plain': 'text file',
	'text/markdown': 'markdown document',
	'text/csv': 'CSV file',
}

const EXTENSION_LABELS: Record<string, string> = {
	doc: 'Word document',
	docx: 'Word document',
	xls: 'Excel spreadsheet',
	xlsx: 'Excel spreadsheet',
	ppt: 'PowerPoint presentation',
	pptx: 'PowerPoint presentation',
	pdf: 'PDF document',
	md: 'Markdown document',
	csv: 'CSV file',
	json: 'JSON file',
	xml: 'XML file',
	yaml: 'YAML file',
	yml: 'YAML file',
	zip: 'zip archive',
}

function filenameExtension(filename: string | null | undefined): string | null {
	const clean = filename?.trim()
	if (!clean) return null
	const dot = clean.lastIndexOf('.')
	if (dot < 0 || dot === clean.length - 1) return null
	return clean.slice(dot + 1).toLowerCase()
}

function subtypeLabel(value: string): string {
	return value
		.replace(/^x-/, '')
		.replace(/^vnd\./, '')
		.split(/[.+-]/)
		.filter(Boolean)
		.slice(-2)
		.join(' ')
}

export function describeFileType(
	mimeType: string | null | undefined,
	filename?: string | null
): string {
	const mime = (mimeType ?? '').split(';')[0]?.trim().toLowerCase() ?? ''
	if (mime && KNOWN_MIME_LABELS[mime]) return KNOWN_MIME_LABELS[mime]

	const extension = filenameExtension(filename)
	if (extension && EXTENSION_LABELS[extension]) return EXTENSION_LABELS[extension]

	if (!mime || mime === 'application/octet-stream') {
		return extension ? `${extension.toUpperCase()} file` : 'file'
	}
	if (mime.startsWith('image/')) return `${subtypeLabel(mime.slice(6)) || 'image'} image`
	if (mime.startsWith('audio/')) return `${subtypeLabel(mime.slice(6)) || 'audio'} audio`
	if (mime.startsWith('video/')) return `${subtypeLabel(mime.slice(6)) || 'video'} video`
	if (mime.startsWith('text/')) return `${subtypeLabel(mime.slice(5)) || 'plain'} text`
	if (mime.endsWith('+json')) return 'JSON file'
	if (mime.endsWith('+xml')) return 'XML file'
	if (mime.startsWith('application/')) {
		const label = subtypeLabel(mime.slice(12))
		return label ? `${label} file` : 'file'
	}

	const type = mime.split('/')[0]
	return type ? `${type} file` : 'file'
}

export function formatFileSize(value: number | null | undefined): string {
	if (!value || value < 0) return '-'
	if (value < 1024) return `${value} B`
	if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
	if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`
	return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`
}
