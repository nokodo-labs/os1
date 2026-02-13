/**
 * generate rim light specular highlight for glass edges.
 * uses rounded-rectangle SDF so highlights follow the actual shape
 * (pill, rounded rect, circle) instead of always being circular.
 */

export interface SpecularConfig {
	width: number
	height: number
	bezelWidth: number
	cornerRadius?: number
	intensity?: number
	lightAngle?: number
	falloff?: number
}

/**
 * rounded rectangle SDF — same as displacement-map.ts.
 * returns outward normal direction at each point.
 */
function roundedRectSDF(
	px: number,
	py: number,
	w: number,
	h: number,
	r: number
): { dist: number; nx: number; ny: number } {
	const ax = Math.abs(px - w / 2)
	const ay = Math.abs(py - h / 2)
	const bx = w / 2 - r
	const by = h / 2 - r
	const dx = Math.max(ax - bx, 0)
	const dy = Math.max(ay - by, 0)

	let dist: number
	let nx: number
	let ny: number

	if (dx > 0 && dy > 0) {
		const len = Math.sqrt(dx * dx + dy * dy)
		dist = len - r
		nx = dx / len
		ny = dy / len
	} else if (ax - bx > ay - by) {
		dist = ax - bx - r
		nx = 1
		ny = 0
	} else {
		dist = ay - by - r
		nx = 0
		ny = 1
	}

	if (px < w / 2) nx = -nx
	if (py < h / 2) ny = -ny

	return { dist, nx, ny }
}

export function generateSpecularHighlight(config: SpecularConfig): string {
	const { width, height, bezelWidth, intensity = 0.6, lightAngle = 135, falloff = 2.0 } = config
	const cornerRadius = config.cornerRadius ?? Math.min(width, height) / 2

	const canvas = document.createElement('canvas')
	canvas.width = width
	canvas.height = height
	const ctx = canvas.getContext('2d')!
	const imageData = ctx.createImageData(width, height)

	const lightRad = (lightAngle * Math.PI) / 180
	const lightDir = { x: Math.cos(lightRad), y: Math.sin(lightRad) }

	for (let y = 0; y < height; y++) {
		for (let x = 0; x < width; x++) {
			const { dist, nx, ny } = roundedRectSDF(x + 0.5, y + 0.5, width, height, cornerRadius)
			const distFromEdge = -dist

			const idx = (y * width + x) * 4

			if (distFromEdge > 0 && distFromEdge < bezelWidth) {
				const dot = nx * lightDir.x + ny * lightDir.y
				const clamped = Math.max(0, dot)
				const highlightValue = Math.pow(clamped, falloff) * intensity * 255

				imageData.data[idx] = highlightValue
				imageData.data[idx + 1] = highlightValue
				imageData.data[idx + 2] = highlightValue
				imageData.data[idx + 3] = highlightValue
			} else {
				imageData.data[idx] = 0
				imageData.data[idx + 1] = 0
				imageData.data[idx + 2] = 0
				imageData.data[idx + 3] = 0
			}
		}
	}

	ctx.putImageData(imageData, 0, 0)
	return canvas.toDataURL('image/png')
}
