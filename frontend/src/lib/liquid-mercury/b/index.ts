export {
	calculateRefractionAngle,
	circularSurface,
	concaveSurface,
	lipSurface,
	squircleSurface,
} from './physics'
export type { RefractionParams, SurfaceFunction } from './physics'

export { generateDisplacementMap } from './displacement-map'
export type { DisplacementMapConfig, DisplacementResult } from './displacement-map'

export { generateSpecularHighlight } from './specular'
export type { SpecularConfig } from './specular'

export { clearCache, getCachedDisplacementMap, setCachedDisplacementMap } from './cache'
