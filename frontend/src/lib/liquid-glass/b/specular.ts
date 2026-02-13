/**
 * generate rim-light specular highlight for glass edges.
 * matches the reference implementation: a thin highlight
 * at the outer edge (~1-2px) using rounded-rectangle SDF
 * and directional dot product.
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
 * rounded rectangle SDF — returns signed distance and outward normal.
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
			const distFromEdge = -dist // positive inside

			const idx = (y * width + x) * 4

			// check if we're in the bezel region (between outer edge and bezelWidth inside)
			if (distFromEdge > -1 && distFromEdge < bezelWidth) {
				const dot = Math.abs(nx * lightDir.x + ny * lightDir.y)

				// anti-aliasing at outer edge
				const opacity = distFromEdge >= 0 ? 1 : 1 - Math.min(1, Math.max(0, -distFromEdge))

				// thin edge coefficient — only significant within ~1px of outer edge
				// matches reference: coefficient = dotProduct * sqrt(1 - (1 - d)^2)
				const edgeT = Math.min(1, Math.max(0, distFromEdge))
				const coefficient = dot * Math.sqrt(1 - (1 - edgeT) * (1 - edgeT))

				const color = 255 * coefficient * intensity
				const finalOpacity = color * Math.pow(coefficient, falloff) * opacity

				imageData.data[idx] = color
				imageData.data[idx + 1] = color
				imageData.data[idx + 2] = color
				imageData.data[idx + 3] = finalOpacity
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
