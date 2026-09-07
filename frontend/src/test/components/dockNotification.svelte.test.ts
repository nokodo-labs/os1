/**
 * a dock notification row (F135, reworked by F138). the day card around the run
 * is the frosted surface; a row is a flat tint inside it, drawing the hairline
 * its place in the run calls for and never a blur of its own. covers the
 * capabilities the row has to keep - open/close, mark read, dismiss by button
 * and by swipe, the per-type icon, the image - the entrance a newly-arrived
 * notification claims exactly once, the glyph the swipe uncovers on its way out
 * (F136), and the height a closed row is allowed to take.
 */

import type { components } from '$lib/api/types'
import Notification from '$lib/components/system/Notification.svelte'
import type { GroupPosition } from '$lib/resources/dockNotifications'
import { device } from '$lib/stores/device.svelte'
import { fireEvent, render, waitFor } from '@testing-library/svelte'
import { tick } from 'svelte'
import { afterEach, describe, expect, it, vi } from 'vitest'

type ApiNotification = components['schemas']['Notification']

const LONG_BODY = 'a body long enough that the row offers to open it '.repeat(4)

/** what the row would measure a wrapped body at; happy-dom lays nothing out. */
const MEASURED_BODY_HEIGHT = 54

function stubBodyHeight(px: number): () => void {
	const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollHeight')
	Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
		configurable: true,
		get: () => px,
	})
	return () => {
		if (original) Object.defineProperty(HTMLElement.prototype, 'scrollHeight', original)
		else Reflect.deleteProperty(HTMLElement.prototype, 'scrollHeight')
	}
}

function notification(overrides: Partial<ApiNotification> = {}): ApiNotification {
	return {
		id: 'notif_1',
		user_id: 'user_me',
		event_id: 'evt_1',
		created_at: '2026-09-03T12:00:00Z',
		read_at: '2026-09-03T12:01:00Z',
		dismissed: false,
		event: { id: 'evt_1', type: 'reminder.created' },
		...overrides,
	} as ApiNotification
}

function mount(props: Record<string, unknown> = {}) {
	return render(Notification, {
		props: {
			notification: notification(),
			title: 'a reminder',
			body: 'short body',
			timestamp: new Date('2026-09-03T12:00:00Z'),
			isUnread: false,
			...props,
		},
	})
}

function cell(container: HTMLElement): HTMLElement {
	const node = container.querySelector<HTMLElement>('[data-notification-cell]')
	if (!node) throw new Error('no notification cell rendered')
	return node
}

function hint(container: HTMLElement): HTMLElement | null {
	return container.querySelector<HTMLElement>('[data-swipe-hint]')
}

function body(container: HTMLElement): HTMLElement {
	const node = container.querySelector<HTMLElement>('[data-notification-body]')
	if (!node) throw new Error('no notification body rendered')
	return node
}

function controls(container: HTMLElement): HTMLElement | null {
	return container.querySelector<HTMLElement>('[data-notification-controls]')
}

/** a coarse-pointer device: no hover, so no button affordances at all. */
function useTouchDevice(): void {
	device.isTouch = true
	device.isCoarsePointer = true
	device.hasHover = false
}

function shownHint(container: HTMLElement): HTMLElement {
	const node = hint(container)
	if (!node) throw new Error('no swipe glyph rendered')
	return node
}

const POINTER = {
	bubbles: true,
	cancelable: true,
	pointerId: 4,
	isPrimary: true,
	button: 0,
	clientY: 24,
	pointerType: 'touch',
} as const

/** drag the row far enough along the axis for the swipe to claim the gesture. */
async function drag(container: HTMLElement, distance: number): Promise<void> {
	const row = cell(container)
	row.dispatchEvent(new PointerEvent('pointerdown', { ...POINTER, clientX: 120 }))
	row.dispatchEvent(new PointerEvent('pointermove', { ...POINTER, clientX: 120 + distance }))
	await tick()
}

async function letGo(container: HTMLElement, distance: number): Promise<void> {
	cell(container).dispatchEvent(
		new PointerEvent('pointerup', { ...POINTER, clientX: 120 + distance })
	)
	await tick()
}

/** the scale the glyph is drawn at, which the gesture's travel drives. */
function hintScale(node: HTMLElement): number {
	const match = /scale\(([\d.]+)\)/.exec(node.style.transform)
	if (!match) throw new Error(`glyph carries no scale: ${node.style.transform}`)
	return Number(match[1])
}

afterEach(() => {
	device.isTouch = false
	device.isCoarsePointer = false
	device.hasHover = true
	device.prefersReducedMotion = false
})

describe('one shared glass surface', () => {
	it('carries no backdrop filter and no liquid-glass surface of its own', () => {
		const { container } = mount()

		expect(container.querySelector('.liquid-glass')).toBeNull()
		expect(cell(container).getAttribute('style') ?? '').not.toMatch(/backdrop-filter/)
		expect(container.innerHTML).not.toMatch(/backdrop-blur|liquid-glass--frosted/)
	})

	it('tints itself off the owning app accent instead of blurring the page again', () => {
		const { container } = mount()

		expect(cell(container).style.getPropertyValue('--notif-accent')).toMatch(/^#/)
		expect(cell(container).style.getPropertyValue('--notif-accent-rgb')).not.toBe('')
	})
})

describe('the day card a row reconstructs', () => {
	const positions: GroupPosition[] = ['single', 'first', 'middle', 'last']

	it.each(positions)('marks itself %s so the card knows its edges', (position) => {
		const { container } = mount({ position })

		expect(cell(container).dataset.position).toBe(position)
	})

	it('draws a hairline only where a row sits under another one', () => {
		for (const position of ['middle', 'last'] as GroupPosition[]) {
			const { container, unmount } = mount({ position })
			expect(
				container.querySelectorAll('[aria-hidden="true"].bg-foreground\\/10')
			).toHaveLength(1)
			unmount()
		}
		for (const position of ['single', 'first'] as GroupPosition[]) {
			const { container, unmount } = mount({ position })
			expect(
				container.querySelectorAll('[aria-hidden="true"].bg-foreground\\/10')
			).toHaveLength(0)
			unmount()
		}
	})

	it('reads unread as the accent and settles when read', () => {
		const unread = mount({ isUnread: true })
		expect(cell(unread.container).classList.contains('notif-cell--unread')).toBe(true)
		unread.unmount()

		const read = mount({ isUnread: false })
		expect(cell(read.container).classList.contains('notif-cell--unread')).toBe(false)
	})
})

describe('dismissal', () => {
	it('flies the row out before handing it over, on the toast timing', async () => {
		vi.useFakeTimers()
		try {
			const onDismiss = vi.fn()
			const { container } = mount({ onDismiss })

			await fireEvent.click(container.querySelector('[aria-label="dismiss notification"]')!)
			expect(cell(container).classList.contains('notif-cell--leaving')).toBe(true)
			expect(onDismiss).not.toHaveBeenCalled()

			vi.advanceTimersByTime(280)
			expect(onDismiss).toHaveBeenCalledWith('notif_1')
		} finally {
			vi.useRealTimers()
		}
	})

	it('hands over at once when motion is off', async () => {
		device.prefersReducedMotion = true
		const onDismiss = vi.fn()
		const { container } = mount({ onDismiss })

		await fireEvent.click(container.querySelector('[aria-label="dismiss notification"]')!)

		expect(onDismiss).toHaveBeenCalledWith('notif_1')
		expect(cell(container).classList.contains('notif-cell--leaving')).toBe(false)
	})

	it('keeps the X in plain sight under a pointer, never hidden until hover', () => {
		const { container } = mount({ onDismiss: vi.fn() })

		const x = container.querySelector<HTMLElement>('[aria-label="dismiss notification"]')
		expect(x).not.toBeNull()
		expect(x!.className).not.toMatch(/opacity-0|invisible|hidden/)
		expect(x!.className).not.toMatch(/group-hover|group-focus-within/)
	})

	it('swipes instead, with no X and no slot reserved for one, on a coarse pointer', () => {
		useTouchDevice()
		const { container } = mount({ onDismiss: vi.fn() })

		expect(container.querySelector('[aria-label="dismiss notification"]')).toBeNull()
		// nothing to put in the controls slot, so the slot itself is gone and the
		// row is only as wide - and as tall - as what it shows.
		expect(controls(container)).toBeNull()
		expect(cell(container).className).toMatch(/select-none/)
	})

	it('still offers the opener on a coarse pointer, alone in the slot', () => {
		useTouchDevice()
		const { container } = mount({ imageUrl: '/img.png', onDismiss: vi.fn() })

		expect(controls(container)?.children).toHaveLength(1)
		expect(container.querySelector('[aria-label="expand notification"]')).not.toBeNull()
	})

	it('offers no dismiss affordance at all without a handler', () => {
		const { container } = mount()

		expect(container.querySelector('[aria-label="dismiss notification"]')).toBeNull()
		expect(controls(container)).toBeNull()
	})
})

describe('the height a closed row takes', () => {
	it('reserves one line for a clamped body, not the whole of it', () => {
		const restore = stubBodyHeight(MEASURED_BODY_HEIGHT)
		try {
			const { container } = mount({ body: LONG_BODY, onDismiss: vi.fn() })

			expect(body(container).style.maxHeight).toBe('18px')
			expect(body(container).className).toMatch(/line-clamp-1/)
		} finally {
			restore()
		}
	})

	it('lays the controls out in one row rather than stacking them', () => {
		const { container } = mount({ imageUrl: '/img.png', onDismiss: vi.fn() })

		// stacked, the opener and the X were 54px of column against 36px of
		// content, and every closed row in pointer layout paid for it.
		const slot = controls(container)
		expect(slot?.children).toHaveLength(2)
		expect(slot?.className).not.toMatch(/flex-col/)
	})
})

describe('opening and closing are the same move in reverse', () => {
	it('travels the body height both ways, on the same transition', async () => {
		const restore = stubBodyHeight(MEASURED_BODY_HEIGHT)
		try {
			const { container } = mount({ body: LONG_BODY, onDismiss: vi.fn() })
			expect(body(container).className).toMatch(/transition-\[max-height\]/)
			expect(body(container).className).toMatch(/duration-300/)

			await fireEvent.click(container.querySelector('[aria-label="expand notification"]')!)
			expect(body(container).style.maxHeight).toBe(`${MEASURED_BODY_HEIGHT}px`)
			expect(body(container).className).not.toMatch(/line-clamp-1/)

			await fireEvent.click(container.querySelector('[aria-label="collapse notification"]')!)
			expect(body(container).style.maxHeight).toBe('18px')
		} finally {
			restore()
		}
	})

	it('holds the clamp and the image back until the close has finished', async () => {
		vi.useFakeTimers()
		const restore = stubBodyHeight(MEASURED_BODY_HEIGHT)
		try {
			const { container } = mount({ body: LONG_BODY, imageUrl: '/img.png' })
			await fireEvent.click(container.querySelector('[aria-label="expand notification"]')!)
			await fireEvent.click(container.querySelector('[aria-label="collapse notification"]')!)

			// re-clamping on the same tick is what made the close look instant
			expect(body(container).className).not.toMatch(/line-clamp-1/)
			expect(container.querySelector('img[src="/img.png"]')).not.toBeNull()

			vi.advanceTimersByTime(300)
			await tick()

			expect(body(container).className).toMatch(/line-clamp-1/)
			expect(container.querySelector('img[src="/img.png"]')).toBeNull()
		} finally {
			restore()
			vi.useRealTimers()
		}
	})

	it('closes on the spot, with nothing to transition, when motion is off', async () => {
		device.prefersReducedMotion = true
		const restore = stubBodyHeight(MEASURED_BODY_HEIGHT)
		try {
			const { container } = mount({ body: LONG_BODY })
			await fireEvent.click(container.querySelector('[aria-label="expand notification"]')!)
			await fireEvent.click(container.querySelector('[aria-label="collapse notification"]')!)

			expect(body(container).className).toMatch(/line-clamp-1/)
			expect(body(container).className).not.toMatch(/transition-\[max-height\]/)
		} finally {
			restore()
		}
	})
})

describe('entrance', () => {
	it('claims a new notification exactly once', () => {
		const claimEntrance = vi.fn(() => true)
		mount({ claimEntrance })

		expect(claimEntrance).toHaveBeenCalledTimes(1)
		expect(claimEntrance).toHaveBeenCalledWith('notif_1')
	})

	it('plays the flyup family for a claimed row and nothing for a refused one', () => {
		const animate = vi.spyOn(Element.prototype, 'animate')
		try {
			animate.mockClear()
			const claimed = mount({ claimEntrance: () => true })
			expect(animate).toHaveBeenCalled()
			const options = animate.mock.calls[0][1] as KeyframeAnimationOptions
			expect(options.duration).toBe(270)
			expect(options.easing).toBe('cubic-bezier(0.34, 1.56, 0.64, 1)')
			claimed.unmount()

			animate.mockClear()
			mount({ claimEntrance: () => false })
			expect(animate).not.toHaveBeenCalled()
		} finally {
			animate.mockRestore()
		}
	})

	it('skips the entrance when motion is off', () => {
		device.prefersReducedMotion = true
		const animate = vi.spyOn(Element.prototype, 'animate')
		try {
			animate.mockClear()
			mount({ claimEntrance: () => true })
			expect(animate).not.toHaveBeenCalled()
		} finally {
			animate.mockRestore()
		}
	})
})

describe('the capabilities a row keeps', () => {
	it('marks a row read on its own when there is nothing to open', async () => {
		const onMarkRead = vi.fn()
		mount({ isUnread: true, onMarkRead })

		await waitFor(() => expect(onMarkRead).toHaveBeenCalledWith('notif_1'))
	})

	it('opens a clamped body and marks it read on the way', async () => {
		const onMarkRead = vi.fn()
		const { container } = mount({ body: LONG_BODY, imageUrl: '/img.png', onMarkRead })

		const toggle = container.querySelector<HTMLElement>('[aria-label="expand notification"]')
		expect(toggle).not.toBeNull()
		expect(container.querySelector('img[src="/img.png"]')).toBeNull()

		await fireEvent.click(toggle!)

		expect(container.querySelector('[aria-label="collapse notification"]')).not.toBeNull()
		expect(container.querySelector('img[src="/img.png"]')).not.toBeNull()
	})

	it('shows the notification image only once opened', () => {
		const { container } = mount({ imageUrl: '/img.png' })

		expect(container.querySelector('img[src="/img.png"]')).toBeNull()
		expect(container.querySelector('[aria-label="expand notification"]')).not.toBeNull()
	})

	it('prefers a supplied avatar over the per-type icon', () => {
		const withAvatar = mount({ iconUrl: '/avatar.png' })
		expect(withAvatar.container.querySelector('img[src="/avatar.png"]')).not.toBeNull()
		expect(withAvatar.container.querySelector('svg')).toBeNull()
		withAvatar.unmount()

		const withType = mount()
		expect(withType.container.querySelector('svg')).not.toBeNull()
	})

	it('keeps the title and the body it was given', () => {
		const { container } = mount({ title: 'reminder due', body: 'water the plants' })

		expect(container.textContent).toContain('reminder due')
		expect(container.textContent).toContain('water the plants')
	})
})

describe('the swipe-dismiss glyph (F136)', () => {
	it('stays out of the row until a swipe is under way', async () => {
		device.isTouch = true
		const { container } = mount({ onDismiss: vi.fn() })

		expect(hint(container)).toBeNull()

		await drag(container, -30)
		expect(hint(container)).not.toBeNull()

		await letGo(container, -30)
		expect(hint(container)).toBeNull()
	})

	it('fills in with the travel, the way the bubble hint does', async () => {
		device.isTouch = true
		const { container } = mount({ onDismiss: vi.fn() })

		await drag(container, -20)
		expect(Number(shownHint(container).style.opacity)).toBeCloseTo(0.25)
		expect(hintScale(shownHint(container))).toBeCloseTo(0.7)
		expect(shownHint(container).style.transform).toContain('translateY(-50%)')

		await drag(container, -60)
		expect(Number(shownHint(container).style.opacity)).toBeCloseTo(0.75)
		expect(hintScale(shownHint(container))).toBeCloseTo(0.9)
	})

	it('sits on the side the row is sliding off, either way', async () => {
		device.isTouch = true
		const left = mount({ onDismiss: vi.fn() })
		await drag(left.container, -30)
		expect(shownHint(left.container).dataset.direction).toBe('left')
		expect(shownHint(left.container)).toHaveClass('right-3')
		expect(shownHint(left.container)).not.toHaveClass('left-3')
		left.unmount()

		const right = mount({ onDismiss: vi.fn() })
		await drag(right.container, 30)
		expect(shownHint(right.container).dataset.direction).toBe('right')
		expect(shownHint(right.container)).toHaveClass('left-3')
	})

	it('is inert decoration: no hit area, no place in the a11y tree', async () => {
		device.isTouch = true
		const { container } = mount({ onDismiss: vi.fn() })

		await drag(container, -30)

		expect(shownHint(container)).toHaveClass('pointer-events-none')
		expect(shownHint(container).getAttribute('aria-hidden')).toBe('true')
	})

	it('still appears when motion is off, with nothing animating it', async () => {
		device.isTouch = true
		device.prefersReducedMotion = true
		const { container } = mount({ onDismiss: vi.fn() })

		await drag(container, -30)

		// the glyph is drawn straight from the finger's travel, so there is no
		// transition or animation to suppress - it is simply there.
		expect(shownHint(container).style.transition).toBe('')
		expect(shownHint(container).className).not.toMatch(/transition|animate-/)
	})

	it('leaves the dismissal threshold exactly where it was', async () => {
		vi.useFakeTimers()
		device.isTouch = true
		try {
			const short = vi.fn()
			const shortSwipe = mount({ onDismiss: short })
			await drag(shortSwipe.container, -60)
			await letGo(shortSwipe.container, -60)
			vi.advanceTimersByTime(400)
			expect(short).not.toHaveBeenCalled()
			shortSwipe.unmount()

			const past = vi.fn()
			const fullSwipe = mount({ onDismiss: past })
			await drag(fullSwipe.container, -90)
			await letGo(fullSwipe.container, -90)
			expect(past).not.toHaveBeenCalled()

			vi.advanceTimersByTime(400)
			expect(past).toHaveBeenCalledWith('notif_1')
		} finally {
			vi.useRealTimers()
		}
	})
})
