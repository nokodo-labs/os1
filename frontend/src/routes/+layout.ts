// This file is used to configure the static adapter for SPA mode
import { initRuntimeConfig } from '$lib/config/runtime'

export const ssr = false

export const load = async () => {
    const config = await initRuntimeConfig()
    return { config }
}
