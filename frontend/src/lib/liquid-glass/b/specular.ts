import { getCachedSpecularMap, setCachedSpecularMap } from './cache'

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

export function generateSpecularHighlight(config: SpecularConfig): string {
	const { width, height, bezelWidth, intensity = 1, lightAngle = 135, falloff = 1 } = config
	const cornerRadius = config.cornerRadius ?? Math.min(width, height) / 2

	const cacheKey = `${width}-${height}-${bezelWidth}-${cornerRadius}-${intensity}-${lightAngle}-${falloff}`
	const cached = getCachedSpecularMap(cacheKey)
	if (cached) {
		return cached.imageDataUrl
	}

	const canvas = document.createElement('canvas')
	canvas.width = width
	canvas.height = height
	const ctx = canvas.getContext('2d')!
	const imageData = ctx.createImageData(width, height)

	const lightRad = (lightAngle * Math.PI) / 180
	const lightDir = { x: Math.cos(lightRad), y: Math.sin(lightRad) }

	const halfW = width / 2
	const halfH = height / 2
	const bx = halfW - cornerRadius
	const by = halfH - cornerRadius

	let idx = 0
	for (let y = 0; y < height; y++) {
		const py = y + 0.5
		const ay = Math.abs(py - halfH)
		const dy = Math.max(ay - by, 0)
		const isTop = py < halfH

		for (let x = 0; x < width; x++) {
			const px = x + 0.5
			const ax = Math.abs(px - halfW)
			const dx = Math.max(ax - bx, 0)
			const isLeft = px < halfW

			let dist: number
			let nx: number
			let ny: number

			if (dx > 0 && dy > 0) {
				const len = Math.sqrt(dx * dx + dy * dy)
				dist = len - cornerRadius
				nx = dx / len
				ny = dy / len
			} else if (ax - bx > ay - by) {
				dist = ax - bx - cornerRadius
				nx = 1
				ny = 0
			} else {
				dist = ay - by - cornerRadius
				nx = 0
				ny = 1
			}

			if (isLeft) nx = -nx
			if (isTop) ny = -ny

			const distFromEdge = -dist // positive inside

			// specular only within bezel region
			if (distFromEdge > 0 && distFromEdge < bezelWidth) {
				const dot = Math.abs(nx * lightDir.x + ny * lightDir.y)

				// reference formula: coefficient = dotProduct * sqrt(1 - (1 - d)^2)
				// where d = distFromEdge in pixels. naturally creates a ~2px wide
				// highlight peaking at 1px from edge, dropping to 0 at 0 and 2px.
				// beyond 2px: inner term goes negative → skip
				const inner = 1 - (1 - distFromEdge) * (1 - distFromEdge)
				if (inner <= 0) {
					imageData.data[idx++] = 0
					imageData.data[idx++] = 0
					imageData.data[idx++] = 0
					imageData.data[idx++] = 0
					continue
				}

				const coefficient = dot * Math.sqrt(inner)
				const color = 255 * coefficient * intensity
				const finalOpacity = color * Math.pow(coefficient, falloff)

				imageData.data[idx++] = color
				imageData.data[idx++] = color
				imageData.data[idx++] = color
				imageData.data[idx++] = finalOpacity
			} else {
				imageData.data[idx++] = 0
				imageData.data[idx++] = 0
				imageData.data[idx++] = 0
				imageData.data[idx++] = 0
			}
		}
	}

	ctx.putImageData(imageData, 0, 0)
	const result = canvas.toDataURL('image/png')
	setCachedSpecularMap(cacheKey, { imageDataUrl: result })
	return result
}
