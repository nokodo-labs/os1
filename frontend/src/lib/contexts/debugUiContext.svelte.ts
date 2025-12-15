import { getContext, setContext } from 'svelte'

const DEBUG_UI_KEY = Symbol('debug-ui')

export type AppsGridIconShape = 'default' | 'circle'

export interface DebugUiContext {
    readonly appsGridIconShape: AppsGridIconShape
    setAppsGridIconShape(shape: AppsGridIconShape): void
    toggleAppsGridIconShape(): void
}

const STORAGE_KEY = 'nokodo.debug.appsGridIconShape'

function readStoredShape(): AppsGridIconShape {
    if (typeof window === 'undefined') return 'default'
    const value = window.localStorage.getItem(STORAGE_KEY)
    return value === 'circle' ? 'circle' : 'default'
}

function writeStoredShape(shape: AppsGridIconShape) {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(STORAGE_KEY, shape)
}

export function createDebugUiContext(): DebugUiContext {
    let appsGridIconShape = $state<AppsGridIconShape>(readStoredShape())

    const context: DebugUiContext = {
        get appsGridIconShape() {
            return appsGridIconShape
        },
        setAppsGridIconShape(shape) {
            appsGridIconShape = shape
            writeStoredShape(shape)
        },
        toggleAppsGridIconShape() {
            const next = appsGridIconShape === 'circle' ? 'default' : 'circle'
            appsGridIconShape = next
            writeStoredShape(next)
        },
    }

    setContext(DEBUG_UI_KEY, context)
    return context
}

export function useDebugUi(): DebugUiContext {
    const context = getContext<DebugUiContext>(DEBUG_UI_KEY)
    if (!context) {
        throw new Error('useDebugUi must be used within a DebugUiProvider')
    }
    return context
}
