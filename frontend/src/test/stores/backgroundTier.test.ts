import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
import type { BackgroundType as PersistedBackgroundType } from '$lib/stores/preferences.svelte'
import type { GpuTier } from '$lib/utils/gpuTier'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type MockedAppearance = {
	autoBackground: boolean
	background: PersistedBackgroundType | null
	staticColor: string
}

const mocked = vi.hoisted(
	(): {
		gpuTier: GpuTier
		appearance: MockedAppearance
		authBackground: BackgroundType | null
	} => ({
		gpuTier: 'mid',
		appearance: { autoBackground: true, background: 'darkveil', staticColor: '#171717' },
		authBackground: null,
	})
)

vi.mock('$lib/stores/device.svelte', () => ({
	device: {
		get gpuTier() {
			return mocked.gpuTier
		},
	},
}))

vi.mock('$lib/stores/preferences.svelte', () => ({
	preferences: {
		get data() {
			return { appearance: mocked.appearance }
		},
		updateWallpaper: vi.fn(),
	},
}))

vi.mock('$lib/stores/settings.svelte', () => ({
	settingsState: {
		get data() {
			if (mocked.authBackground === null) return null
			return { ui: { auth_pages_background: mocked.authBackground } }
		},
	},
}))

/**
 * the store's deriveds cache against the mocked (non-reactive) device, so every
 * tier is read from a freshly evaluated module.
 */
async function loadStore(tier: GpuTier) {
	mocked.gpuTier = tier
	vi.resetModules()
	return await import('$lib/stores/background.svelte')
}

beforeEach(() => {
	mocked.gpuTier = 'mid'
	mocked.appearance = { autoBackground: true, background: 'darkveil', staticColor: '#171717' }
	mocked.authBackground = null
})

describe('wallpaperMaxFps', () => {
	it('gives each GPU tier its own frame budget', async () => {
		expect((await loadStore('high')).background.wallpaperMaxFps).toBe(120)
		expect((await loadStore('mid')).background.wallpaperMaxFps).toBe(30)
		expect((await loadStore('low')).background.wallpaperMaxFps).toBe(0)
	})

	it('reports whether animated wallpapers may run at all', async () => {
		expect((await loadStore('high')).background.allowsAnimated).toBe(true)
		expect((await loadStore('mid')).background.allowsAnimated).toBe(true)
		expect((await loadStore('low')).background.allowsAnimated).toBe(false)
	})
})

describe('isAnimatedBackground', () => {
	it('separates wallpapers that run a frame loop from ones that paint once', async () => {
		const { isAnimatedBackground } = await loadStore('mid')

		// both siblings of a pair share a renderer, so both sides answer the same
		const stills: BackgroundType[] = [
			'static',
			'dither',
			'dither-light',
			'dots',
			'dots-dark',
			'none',
		]
		for (const bg of stills) expect(isAnimatedBackground(bg)).toBe(false)

		const animated: BackgroundType[] = [
			'darkveil',
			'darkveil-light',
			'lightrays',
			'clouds',
			'clouds-dark',
			'orbglow',
			'rain',
			'galaxy-light',
		]
		for (const bg of animated) expect(isAnimatedBackground(bg)).toBe(true)
	})
})

describe('low tier resolution', () => {
	it('falls back to static for an animated manual pick', async () => {
		mocked.appearance.autoBackground = false
		mocked.appearance.background = 'galaxy'

		expect((await loadStore('low')).background.resolved).toBe('static')
		expect((await loadStore('mid')).background.resolved).toBe('galaxy')
	})

	it('resolves auto mode to the tier default', async () => {
		expect((await loadStore('low')).background.resolved).toBe('static')
		expect((await loadStore('mid')).background.resolved).toBe('lightrays')
		expect((await loadStore('high')).background.resolved).toBe('darkveil')
	})

	it('leaves a page override that does not animate untouched', async () => {
		const { background } = await loadStore('low')

		background.setPage('dither')
		expect(background.resolved).toBe('dither')
	})

	it('clamps an animated page override unless it opts out for debugging', async () => {
		const { background } = await loadStore('low')

		background.setPage('galaxy')
		expect(background.resolved).toBe('static')

		background.setPage('galaxy', { allowAnimated: true })
		expect(background.resolved).toBe('galaxy')

		background.setPage('galaxy')
		expect(background.resolved).toBe('static')

		background.clearPage()
		expect(background.resolved).toBe('static')
	})

	it('leaves page overrides alone on a tier that can animate', async () => {
		const { background } = await loadStore('high')

		background.setPage('galaxy')
		expect(background.resolved).toBe('galaxy')

		background.clearPage()
		expect(background.resolved).toBe('darkveil')
	})
})

/**
 * the auth pages have no wallpaper of their own: the root layout is the only
 * place that mounts one, and it hands the admin-configured auth background to
 * the same `setPage` clamp every other page override goes through.
 */
describe('auth pages', () => {
	it('clamps the heavy auth wallpaper away on a tier that cannot animate', async () => {
		mocked.authBackground = 'galaxy'
		const { background } = await loadStore('low')

		background.setPage(background.auth)
		expect(background.auth).toBe('galaxy')
		expect(background.resolved).toBe('static')
		expect(background.wallpaperMaxFps).toBe(0)
	})

	it('keeps the auth wallpaper on tiers that animate, each at its own budget', async () => {
		mocked.authBackground = 'galaxy'

		const mid = (await loadStore('mid')).background
		mid.setPage(mid.auth)
		expect(mid.resolved).toBe('galaxy')
		expect(mid.wallpaperMaxFps).toBe(30)

		const high = (await loadStore('high')).background
		high.setPage(high.auth)
		expect(high.resolved).toBe('galaxy')
		expect(high.wallpaperMaxFps).toBe(120)
	})

	it('clamps a still auth wallpaper not at all', async () => {
		mocked.authBackground = 'dither'
		const { background } = await loadStore('low')

		background.setPage(background.auth)
		expect(background.resolved).toBe('dither')
	})

	it('falls back to the default wallpaper before settings load', async () => {
		const { background } = await loadStore('mid')
		expect(background.auth).toBe('lightrays')
	})
})

describe('wallpaperFrameCap', () => {
	async function loadCap(tier: GpuTier) {
		await loadStore(tier)
		return (await import('$lib/components/backgrounds/wallpaperLoop')).wallpaperFrameCap
	}

	it('paces a wallpaper loop at the device cap', async () => {
		expect((await loadCap('high'))()).toBe(120)
		expect((await loadCap('mid'))()).toBe(30)
	})

	it('keeps a tighter cap the wallpaper asked for', async () => {
		expect((await loadCap('high'))(24)).toBe(24)
		expect((await loadCap('mid'))(60)).toBe(30)
	})

	it('still paces a wallpaper that reached a tier with no frame budget', async () => {
		expect((await loadCap('low'))()).toBe(30)
	})
})
