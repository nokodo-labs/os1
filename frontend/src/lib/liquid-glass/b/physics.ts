/**
 * snell-descartes law implementation for refraction calculations
 * n1 * sin(θ1) = n2 * sin(θ2)
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

export function calculateDisplacement(
	distanceFromBorder: number,
	bezelWidth: number,
	surfaceFn: SurfaceFunction,
	thickness: number,
	n1 = 1.0,
	n2 = 1.5
): number {
	if (distanceFromBorder >= bezelWidth) return 0

	const t = distanceFromBorder / bezelWidth
	const normal = calculateNormal(surfaceFn, t, thickness, bezelWidth)
	const incidentAngle = Math.acos(normal.y)

	const refractedAngle = calculateRefractionAngle({ n1, n2, incidentAngle })
	if (refractedAngle === null) return 0

	// ray travels through local glass height at this point, not max thickness
	const localHeight = surfaceFn(t, thickness)
	return localHeight * Math.tan(incidentAngle - refractedAngle)
}
