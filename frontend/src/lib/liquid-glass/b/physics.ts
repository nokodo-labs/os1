/**
 * snell-descartes law implementation for refraction calculations.
 * uses vector refraction matching the kube.io reference implementation:
 *   eta = n1 / n2
 *   refract(normal, incident) → refracted direction vector
 *   displacement = refractedX * remainingHeight / refractedY
 */

export interface RefractionParams {
	n1: number
	n2: number
	incidentAngle: number
}

export function calculateRefractionAngle(params: RefractionParams): number | null {
	const { n1, n2, incidentAngle } = params
	const sinTheta2 = (n1 / n2) * Math.sin(incidentAngle)

	if (Math.abs(sinTheta2) > 1) return null

	return Math.asin(sinTheta2)
}

/**
 * surface profile functions for glass shape definition
 * t ∈ [0, 1] where 0 = outer edge, 1 = end of bezel
 */
export type SurfaceFunction = (t: number, thickness: number) => number

export const circularSurface: SurfaceFunction = (t, thickness) => {
	return thickness * Math.sqrt(1 - (1 - t) * (1 - t))
}

export const squircleSurface: SurfaceFunction = (t, thickness) => {
	const n = 4
	return thickness * Math.pow(1 - Math.pow(1 - t, n), 1 / n)
}

export const concaveSurface: SurfaceFunction = (t, thickness) => {
	return thickness * (1 - Math.sqrt(1 - (1 - t) * (1 - t)))
}

export const lipSurface: SurfaceFunction = (t, thickness) => {
	const blend = t * t * t * (t * (t * 6 - 15) + 10)
	const convex = squircleSurface(t, thickness)
	const concave = concaveSurface(t, thickness)
	return convex * (1 - blend) + concave * blend
}

export function calculateNormal(
	surfaceFn: SurfaceFunction,
	t: number,
	thickness: number,
	bezelWidth: number,
	epsilon = 0.001
): { x: number; y: number } {
	const h1 = surfaceFn(Math.max(0, t - epsilon), thickness)
	const h2 = surfaceFn(Math.min(1, t + epsilon), thickness)
	// derivative is in t-space; divide by bezelWidth to convert to pixel-space slope
	const slope = (h2 - h1) / (2 * epsilon * bezelWidth)

	const length = Math.sqrt(1 + slope * slope)
	return {
		x: -slope / length,
		y: 1 / length,
	}
}

/**
 * vector refraction for a vertical incident ray [0, 1] hitting a surface
 * with the given normal. matches the reference implementation exactly.
 *
 * @returns [refractedX, refractedY] or null for total internal reflection
 */
function vectorRefract(normalX: number, normalY: number, eta: number): [number, number] | null {
	// incident ray is [0, 1], dot product with normal is just normalY
	const dot = normalY
	const k = 1 - eta * eta * (1 - dot * dot)
	if (k < 0) return null // total internal reflection

	const kSqrt = Math.sqrt(k)
	return [-(eta * dot + kSqrt) * normalX, eta - (eta * dot + kSqrt) * normalY]
}

/**
 * calculate pixel displacement at a given distance from the shape border.
 * uses vector refraction and accounts for remaining glass height
 * (bezel surface height + flat glass body thickness).
 *
 * @param glassThickness - thickness of the flat glass body beyond the bezel (px).
 *   this is the main parameter controlling displacement strength.
 *   the refracted ray travels through both the bezel surface AND this flat body.
 */
export function calculateDisplacement(
	distanceFromBorder: number,
	bezelWidth: number,
	surfaceFn: SurfaceFunction,
	thickness: number,
	n1 = 1.0,
	n2 = 1.5,
	glassThickness = 0
): number {
	if (distanceFromBorder >= bezelWidth) return 0

	const t = distanceFromBorder / bezelWidth
	const eta = n1 / n2

	// normalized surface height (0..1) — matches reference convention
	const y = surfaceFn(t, 1)

	// normalized derivative for slope calculation (reference uses normalized coords)
	const epsilon = 0.0001
	const y2 = surfaceFn(Math.min(1, t + epsilon), 1)
	const derivative = (y2 - y) / epsilon

	// normal pointing INTO the glass (reference convention: negative y)
	const magnitude = Math.sqrt(derivative * derivative + 1)
	const normalX = -derivative / magnitude
	const normalY = -1 / magnitude

	const refracted = vectorRefract(normalX, normalY, eta)
	if (!refracted) return 0
	if (Math.abs(refracted[1]) < 1e-10) return 0

	// remaining height = bezel surface height + flat glass body
	// reference: remainingHeight = y * bezelWidth + glassThickness
	// our equivalent: y * thickness + glassThickness
	const remainingHeight = y * thickness + glassThickness

	return refracted[0] * (remainingHeight / refracted[1])
}
