import BackgroundManager from '$lib/components/backgrounds/BackgroundManager.svelte'
import { device } from '$lib/stores/device.svelte'
import { render } from '@testing-library/svelte'
import { tick, type ComponentProps } from 'svelte'
import { afterEach, describe, expect, it } from 'vitest'
import BackgroundShellFixture from './BackgroundShellFixture.svelte'

type ManagerProps = ComponentProps<typeof BackgroundManager>

/** the wallpaper layer BackgroundManager owns */
const WALLPAPER_LAYER = '[class~="-z-10"]'

function shell(): HTMLElement | null {
	return document.querySelector('[data-testid="app-shell"]')
}

/** the wallpaper swap runs through a rAF and a paint */
async function settleSwap(): Promise<void> {
	await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
	await tick()
}

describe('BackgroundManager sizing', () => {
	afterEach(() => {
		device.stableViewportHeight = 0
	})

	it('sizes the wallpaper from the stable viewport height, clipped', () => {
		// the layer follows the LAYOUT viewport, which the virtual keyboard now
		// shrinks - it holds the ratcheted height instead and clips the overflow,
		// so it still paints edge to edge behind the shrunken viewport.
		device.stableViewportHeight = 860
		const { container } = render(BackgroundManager, { props: { type: 'static' } })
		const layer = container.querySelector(WALLPAPER_LAYER)

		expect(layer?.getAttribute('style')).toContain('height: 860px')
		expect(layer?.className).toContain('overflow-hidden')
	})

	it('falls back to the inset-0 stretch before the device store syncs', () => {
		const { container } = render(BackgroundManager, { props: { type: 'static' } })
		const layer = container.querySelector(WALLPAPER_LAYER)

		expect(layer?.getAttribute('style') ?? '').not.toContain('height')
	})
})

describe('BackgroundManager composition', () => {
	it('takes no children, so the app can never be nested inside it', () => {
		// a `children` prop would put the whole app back inside a fixed, -z-10
		// stacking context, and a wallpaper swap could remount it again.
		const acceptsChildren: 'children' extends keyof ManagerProps ? true : false = false
		expect(acceptsChildren).toBe(false)
	})

	it('renders the wallpaper layer and nothing else', () => {
		const { container } = render(BackgroundManager, { props: { type: 'static' } })

		const layer = container.querySelector(WALLPAPER_LAYER)
		expect(layer).not.toBeNull()
		expect(container.children).toHaveLength(1)
	})

	it('keeps the app shell outside the wallpaper stacking context', () => {
		const { container } = render(BackgroundShellFixture, { props: { type: 'static' } })

		const layer = container.querySelector(WALLPAPER_LAYER)
		const mounted = shell()
		expect(layer).not.toBeNull()
		expect(mounted).not.toBeNull()
		expect(layer?.contains(mounted)).toBe(false)
	})

	it('keeps the same app shell nodes when the wallpaper changes', async () => {
		// boot renders 'none' until preferences settle, then swaps to the resolved
		// wallpaper. as a sibling the shell is untouched by that swap, so the app
		// never remounts and never re-runs every boot request.
		const { rerender } = render(BackgroundShellFixture, { props: { type: 'none' } })
		const mounted = shell()
		const content = document.querySelector('[data-testid="app-content"]')
		expect(mounted).not.toBeNull()
		expect(content).not.toBeNull()

		await rerender({ type: 'static' })
		await settleSwap()

		expect(document.querySelectorAll('[data-testid="app-shell"]')).toHaveLength(1)
		expect(shell()).toBe(mounted)
		expect(document.querySelector('[data-testid="app-content"]')).toBe(content)
	})
})
