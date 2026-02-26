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

function vectorRefract(normalX: number, normalY: number, eta: number): [number, number] | null {
	const dot = normalY
	const k = 1 - eta * eta * (1 - dot * dot)
	if (k < 0) return null

	const kSqrt = Math.sqrt(k)
	return [-(eta * dot + kSqrt) * normalX, eta - (eta * dot + kSqrt) * normalY]
}

export function calculateDisplacement(
	distanceFromBorder: number,
	bezelWidth: number,
	surfaceFn: SurfaceFunction,
	thickness: number,
	n1 = 1.0,
	n2 = 1.5,
	mirrorDepth = 26
): number {
	if (distanceFromBorder >= bezelWidth) return 0

	const t = distanceFromBorder / bezelWidth
	const eta = n1 / n2

	const y = surfaceFn(t, 1)
	const epsilon = 0.0001
	const y2 = surfaceFn(Math.min(1, t + epsilon), 1)
	const derivative = ((y2 - y) * thickness) / (epsilon * bezelWidth)

	const magnitude = Math.sqrt(derivative * derivative + 1)
	const normalX = -derivative / magnitude
	const normalY = -1 / magnitude

	const refracted = vectorRefract(normalX, normalY, eta)
	if (!refracted) return 0
	if (Math.abs(refracted[1]) < 1e-10) return 0

	const remainingHeight = y * thickness + mirrorDepth
	return refracted[0] * (remainingHeight / refracted[1])
}
