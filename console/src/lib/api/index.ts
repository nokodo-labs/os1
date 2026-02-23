export { api, rawApi, refreshAccessToken, unwrap } from './client'
export type { ApiPaths } from './client'
export { SystemService } from './system'
export type { components, operations, paths } from './types'

// Schemas convenience alias - use Schemas['TypeName'] to reference API types
export type Schemas = import('./types').components['schemas']

// derived literal types
export type BackgroundType = NonNullable<Schemas['AppearancePreferences']['background']>
