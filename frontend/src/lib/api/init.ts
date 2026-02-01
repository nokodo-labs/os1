import { initApiOrigin } from './origin'

// single shared initialization promise for the API layer.
// importing this module is the supported way to ensure api origin is available.
export const apiOriginReady = initApiOrigin()
