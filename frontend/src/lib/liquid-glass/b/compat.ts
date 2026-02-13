/**
 * feature detection for liquid glass 2 SVG filter support
 */

export function supportsBackdropFilter(): boolean {
	if (typeof window === 'undefined') return false

	const testElement = document.createElement('div')
	const style = testElement.style as unknown as Record<string, string>
	style.backdropFilter = 'blur(1px)'
	style.webkitBackdropFilter = 'blur(1px)'

	return style.backdropFilter === 'blur(1px)' || style.webkitBackdropFilter === 'blur(1px)'
}

export function supportsSVGFilterAsBackdrop(): boolean {
	const isChrome =
		typeof navigator !== 'undefined' &&
		/Chrome/.test(navigator.userAgent) &&
		/Google Inc/.test(navigator.vendor)
	return isChrome && supportsBackdropFilter()
}

export function getFallbackStyles(): Record<string, string> {
	return {
		background: 'rgba(255, 255, 255, 0.1)',
		'backdrop-filter': 'blur(20px) saturate(180%)',
		'-webkit-backdrop-filter': 'blur(20px) saturate(180%)',
		border: '1px solid rgba(255, 255, 255, 0.18)',
	}
}
