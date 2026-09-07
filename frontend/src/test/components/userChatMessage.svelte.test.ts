/**
 * the user bubble's action surface (F95, restaged by F110): individually
 * floating glass buttons for a precise cursor, and a lifted bubble over a
 * dimmed, blurred transcript for everything else. the same actions either way.
 *
 * plus the status slot beside the bubble (F48 + F104): clock, tick, both ticks.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { clockTime, formatTimeHeader } from '$lib/chat/chatTimestamps'
import type { ReadCursor } from '$lib/chat/readReceipts'
import type { Thread } from '$lib/stores/chat.svelte'
import { device } from '$lib/stores/device.svelte'
import { fireEvent, render, screen } from '@testing-library/svelte'
import { tick } from 'svelte'
import { SvelteMap } from 'svelte/reactivity'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeThread } from '../chat/fixtures'

vi.mock('$app/environment', () => ({ browser: true, dev: false }))
vi.mock('$lib/api/client', () => ({
	getApiBaseUrl: () => 'http://localhost:1383',
	api: {
		GET: vi.fn().mockResolvedValue({ data: null, error: null }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))
vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => null),
	onAccessTokenChanged: vi.fn(),
}))
vi.mock('$lib/stores/session.svelte', () => ({ session: { currentUserId: 'user_me' } }))

const UserChatMessage = (await import('$lib/components/chat/UserChatMessage.svelte')).default
const { chat } = await import('$lib/stores/chat.svelte')
const { readReceiptStyle } = await import('$lib/stores/readReceiptStyle.svelte')

interface Handlers {
	onReply?: () => void
	onDelete?: () => void
	onEditSave?: (content: string) => Promise<void>
}

function mount(handlers: Handlers = {}, extra: Record<string, unknown> = {}) {
	return render(UserChatMessage, {
		props: { content: 'hello there', ...handlers, ...extra },
	})
}

function bubbleRow(container: HTMLElement): HTMLElement {
	const row = container.querySelector('[role="article"]')
	if (!(row instanceof HTMLElement)) throw new Error('message row not rendered')
	return row
}

/** the gutter cluster the hover buttons live in. */
function cluster(container: HTMLElement): HTMLElement {
	const el = container.querySelector('[data-corner-actions]')
	if (!(el instanceof HTMLElement)) throw new Error('corner cluster not rendered')
	return el
}

/** each action carries its own glass surface rather than sharing a toolbar. */
function glassBubble(button: HTMLElement): HTMLElement {
	const el = button.closest('.action-bubble')
	if (!(el instanceof HTMLElement)) throw new Error('action is not a floating bubble')
	return el
}

function focusLayer(): HTMLElement | null {
	const el = document.querySelector('[data-message-focus]')
	return el instanceof HTMLElement ? el : null
}

/** the dim/blur layer; it goes inert while the surface settles back. */
function backdrop(): HTMLElement {
	const el = document.querySelector('[data-message-focus-backdrop]')
	if (!(el instanceof HTMLElement)) throw new Error('focus backdrop not rendered')
	return el
}

/** the inert copy of the bubble that stands in for it while it is lifted. */
function ghost(): HTMLElement {
	const el = focusLayer()?.querySelector('.bubble-wrapper')
	if (!(el instanceof HTMLElement)) throw new Error('lifted ghost not rendered')
	return el
}

function bubbleWrapper(container: HTMLElement): HTMLElement {
	const el = container.querySelector('.bubble-wrapper')
	if (!(el instanceof HTMLElement)) throw new Error('bubble not rendered')
	return el
}

/** the lifted layer's selection gate: inert while it comes in, armed after. */
function liftSelection(): string | undefined {
	const el = focusLayer()?.querySelector('.lift-layer')
	return el instanceof HTMLElement ? el.dataset.select : undefined
}

function swipeHint(container: HTMLElement): HTMLElement {
	const el = container.querySelector('[data-swipe-hint]')
	if (!(el instanceof HTMLElement)) throw new Error('swipe hint not rendered')
	return el
}

function senderAvatar(container: HTMLElement): HTMLElement {
	const el = container.querySelector('[data-sender-avatar]')
	if (!(el instanceof HTMLElement)) throw new Error('avatar gutter not rendered')
	return el
}

function replyQuote(container: HTMLElement): HTMLElement {
	const el = container.querySelector('[data-reply-quote]')
	if (!(el instanceof HTMLElement)) throw new Error('reply quote not rendered')
	return el
}

/** the props a bubble carries in a group thread: named sender, avatar, tail. */
const inGroup = {
	align: 'left',
	senderName: 'ada',
	showSenderAvatar: true,
	showTail: true,
	tailStyle: 'imessage',
} as const

/** drag the row far enough for the swipe attachment to claim the gesture. */
async function dragRow(container: HTMLElement, distance = 30): Promise<void> {
	const row = bubbleRow(container)
	const base = {
		bubbles: true,
		cancelable: true,
		pointerId: 2,
		isPrimary: true,
		button: 0,
		clientY: 10,
		pointerType: 'touch',
	}
	row.dispatchEvent(new PointerEvent('pointerdown', { ...base, clientX: 10 }))
	row.dispatchEvent(new PointerEvent('pointermove', { ...base, clientX: 10 + distance }))
	await tick()
}

/**
 * which elements a svelte transition actually reached. a transition is LOCAL by
 * default and stays silent when it is an ancestor block that mounted, so every
 * button in its own `{#if}` needs `|global` - this is what catches that.
 */
function watchAnimations() {
	const spy = vi.spyOn(Element.prototype, 'animate')
	return {
		targets: (): Element[] =>
			spy.mock.contexts.filter((ctx): ctx is Element => ctx instanceof Element),
		stop: (): void => spy.mockRestore(),
	}
}

function pointerDown(node: HTMLElement): void {
	node.dispatchEvent(
		new PointerEvent('pointerdown', {
			bubbles: true,
			cancelable: true,
			pointerId: 1,
			isPrimary: true,
			button: 0,
			clientX: 10,
			clientY: 10,
			pointerType: 'touch',
		})
	)
}

/** hold the bubble until the gesture fires, then let the surface settle in. */
async function hold(container: HTMLElement): Promise<void> {
	vi.useFakeTimers()
	pointerDown(bubbleRow(container))
	vi.advanceTimersByTime(500)
	await tick()
	await tick()
}

function usePreciseCursor(): void {
	device.hasHover = true
	device.isCoarsePointer = false
}

function useTouch(): void {
	device.hasHover = false
	device.isCoarsePointer = true
}

beforeEach(() => {
	usePreciseCursor()
	device.prefersReducedMotion = false
})

afterEach(() => {
	usePreciseCursor()
	device.prefersReducedMotion = false
	vi.useRealTimers()
})

describe('hover cluster', () => {
	it('springs individually floating glass bubbles into the gutter', async () => {
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })

		expect(cluster(container).dataset.visible).toBe('false')
		expect(screen.queryByLabelText('reply to message')).not.toBeInTheDocument()

		await fireEvent.mouseEnter(bubbleRow(container))
		expect(cluster(container).dataset.visible).toBe('true')

		// reply, copy and the ellipsis: three separate bubbles, no docked row
		const bubbles = container.querySelectorAll('.action-bubble')
		expect(bubbles).toHaveLength(3)
		for (const bubble of bubbles) {
			expect(bubble).toHaveClass('liquid-glass')
			expect(bubble).toHaveClass('rounded-pill')
		}
		expect(glassBubble(screen.getByLabelText('reply to message'))).not.toBe(
			glassBubble(screen.getByLabelText('copy message'))
		)
	})

	it('springs EVERY bubble, not just the one outside a nested block', async () => {
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })
		const animations = watchAnimations()

		await fireEvent.mouseEnter(bubbleRow(container))

		const sprung = animations.targets().filter((el) => el.classList.contains('action-bubble'))
		expect(sprung).toHaveLength(3)
		animations.stop()
	})

	it('keeps the cluster anchored in the gutter, shifted by the status glyph', async () => {
		const { container } = mount({ onReply: () => {} }, { sending: true })

		expect(cluster(container).className).toContain('right-full')
		expect(cluster(container).style.marginRight).toBe('2.25rem')
	})

	it('promotes reply and copy, and parks the rest behind the ellipsis', async () => {
		const { container } = mount({
			onReply: () => {},
			onDelete: () => {},
			onEditSave: async () => {},
		})
		await fireEvent.mouseEnter(bubbleRow(container))

		expect(screen.getByLabelText('reply to message')).toBeInTheDocument()
		expect(screen.getByLabelText('copy message')).toBeInTheDocument()
		expect(screen.getByLabelText('more actions')).toBeInTheDocument()
		// edit and delete are menu-only, never a bare corner button
		expect(screen.queryByLabelText('edit message')).not.toBeInTheDocument()
		expect(screen.queryByLabelText('delete message')).not.toBeInTheDocument()
	})

	it('the ellipsis menu lists every action the bubble offers', async () => {
		const onReply = vi.fn()
		const onDelete = vi.fn()
		const { container } = mount({ onReply, onDelete, onEditSave: async () => {} })
		await fireEvent.mouseEnter(bubbleRow(container))

		await fireEvent.click(screen.getByLabelText('more actions'))

		const labels = screen.getAllByRole('menuitem').map((item) => item.textContent?.trim())
		expect(labels).toEqual(['reply', 'copy', 'edit', 'delete'])

		await fireEvent.click(screen.getByRole('menuitem', { name: 'delete' }))
		expect(onDelete).toHaveBeenCalledTimes(1)
		expect(onReply).not.toHaveBeenCalled()
		// the menu is on its way out, so it is inert rather than already gone
		expect(screen.getByRole('menu')).toHaveAttribute('inert')
	})
})

describe('lifted focus', () => {
	it('a hold lifts the bubble, dims behind it, and floats the frequent actions', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })

		// no cursor, so nothing is offered until the bubble is held
		expect(screen.queryByLabelText('reply to message')).not.toBeInTheDocument()
		expect(focusLayer()).toBeNull()

		await hold(container)

		const layer = focusLayer()
		expect(layer).not.toBeNull()
		expect(layer?.querySelector('[data-message-focus-backdrop]')).not.toBeNull()
		expect(layer?.dataset.motion).toBe('spring')

		// the actions float as their own bubbles beside the lifted one
		expect(glassBubble(screen.getByLabelText('reply to message'))).toHaveClass('liquid-glass')
		expect(glassBubble(screen.getByLabelText('copy message'))).toHaveClass('liquid-glass')
		expect(glassBubble(screen.getByLabelText('more actions'))).toHaveClass('liquid-glass')

		// ...and nothing else: the fuller menu waits to be asked for
		expect(screen.queryByRole('menu')).not.toBeInTheDocument()
	})

	it('the ellipsis bubble opens the fuller menu below the lifted bubble', async () => {
		useTouch()
		const onDelete = vi.fn()
		const { container } = mount({ onReply: () => {}, onDelete, onEditSave: async () => {} })
		await hold(container)

		const ellipsis = screen.getByLabelText('more actions')
		expect(ellipsis).toHaveAttribute('aria-expanded', 'false')

		await fireEvent.click(ellipsis)

		expect(ellipsis).toHaveAttribute('aria-expanded', 'true')
		// only what the floating bubbles do not already offer
		const labels = screen.getAllByRole('menuitem').map((item) => item.textContent?.trim())
		expect(labels).toEqual(['edit', 'delete'])
	})

	it('closing the menu steps back to the lifted bubble, not out of focus', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })
		await hold(container)
		await fireEvent.click(screen.getByLabelText('more actions'))
		expect(screen.getByRole('menu')).toBeInTheDocument()

		await fireEvent.keyDown(window, { key: 'Escape' })

		// the menu is going, the lift stays
		expect(screen.getByRole('menu')).toHaveAttribute('inert')
		expect(backdrop()).not.toHaveAttribute('inert')
		expect(screen.getByLabelText('more actions')).toHaveAttribute('aria-expanded', 'false')

		// a second escape now takes the whole surface down
		await fireEvent.keyDown(window, { key: 'Escape' })
		expect(backdrop()).toHaveAttribute('inert')
	})

	it('animates the lift, the backdrop and each floating button', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })
		const animations = watchAnimations()

		await hold(container)

		const sprung = animations.targets()
		expect(sprung.filter((el) => el.classList.contains('action-bubble'))).toHaveLength(3)
		expect(sprung).toContain(backdrop())
		expect(sprung.some((el) => el.contains(ghost()))).toBe(true)
		animations.stop()
	})

	it('lets the platform select the lifted text instead of dismissing', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })
		await hold(container)

		// the copy is live, not a picture: a hold inside it reaches native selection
		const layer = ghost().closest('.lift-layer')
		expect(layer).toBeInstanceOf(HTMLElement)
		expect(layer).not.toHaveClass('pointer-events-none')

		// a press that starts on the bubble and drags out onto the dim must not close
		await fireEvent.pointerDown(ghost(), { pointerId: 1, isPrimary: true, button: 0 })
		await fireEvent.click(backdrop())

		expect(backdrop()).not.toHaveAttribute('inert')
		expect(bubbleWrapper(container).style.visibility).toBe('hidden')

		// ...while a press that starts on the dim still does
		await fireEvent.pointerDown(backdrop(), { pointerId: 1, isPrimary: true, button: 0 })
		await fireEvent.click(backdrop())
		expect(backdrop()).toHaveAttribute('inert')
	})

	it('the lifted bubble is an inert copy, and the original hides behind it', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {} })
		await hold(container)

		expect(bubbleWrapper(container).style.visibility).toBe('hidden')

		// the copy keeps the text but none of the live action chrome
		expect(ghost().textContent).toContain('hello there')
		expect(ghost().querySelector('[data-corner-actions]')).toBeNull()
	})

	it('gives the original bubble back on dismiss, even if no outro ever lands', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })
		await hold(container)
		expect(bubbleWrapper(container).style.visibility).toBe('hidden')

		await fireEvent.click(backdrop())
		// nothing here ever finishes a web animation, so no outro completes: the
		// bubble has to come back on the settle timer alone or it is lost for good
		vi.advanceTimersByTime(400)
		await tick()

		expect(bubbleWrapper(container).style.visibility).toBe('')
	})

	it('gives it back at once when motion is reduced', async () => {
		useTouch()
		device.prefersReducedMotion = true
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })
		await hold(container)
		expect(bubbleWrapper(container).style.visibility).toBe('hidden')

		// there is no settle to wait out, so nothing may be pending on a timer
		await fireEvent.click(backdrop())
		await tick()

		expect(bubbleWrapper(container).style.visibility).toBe('')
	})

	it('escape settles everything back', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })
		await hold(container)
		expect(backdrop()).not.toHaveAttribute('inert')

		await fireEvent.keyDown(window, { key: 'Escape' })
		expect(backdrop()).toHaveAttribute('inert')
	})

	it('a tap outside settles everything back', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })
		await hold(container)
		expect(backdrop()).not.toHaveAttribute('inert')

		await fireEvent.click(backdrop())

		expect(backdrop()).toHaveAttribute('inert')
	})

	it('drops edit and delete on a message the viewer does not own (F1)', async () => {
		const { container } = mount({ onReply: () => {} })
		await fireEvent.mouseEnter(bubbleRow(container))

		// nothing left to overflow, so the ellipsis does not appear either
		expect(screen.queryByLabelText('more actions')).not.toBeInTheDocument()

		await fireEvent.mouseLeave(bubbleRow(container))
		await hold(container)

		// the lift still happens, it just has nothing to hang a menu off
		expect(focusLayer()).not.toBeNull()
		expect(screen.queryByLabelText('more actions')).not.toBeInTheDocument()
		expect(screen.queryByRole('menu')).not.toBeInTheDocument()
	})

	it('drops the motion when the viewer asked for less of it', async () => {
		useTouch()
		device.prefersReducedMotion = true
		const { container } = mount({ onReply: () => {}, onDelete: () => {} })
		await hold(container)

		expect(focusLayer()?.dataset.motion).toBe('reduced')
	})

	it('keeps branch navigation on the bubble, not behind a gesture', () => {
		mount({}, { siblingCount: 2, currentSiblingIndex: 0 })

		expect(screen.getByTitle('previous version')).toBeInTheDocument()
		expect(screen.getByTitle('next version')).toBeInTheDocument()
		expect(screen.getByText('1/2')).toBeInTheDocument()
	})
})

describe('selection is the SECOND hold (F126)', () => {
	it('leaves the lifted text unselectable while the lifting hold is still down', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {} })
		await hold(container)

		// the press that opened this is still on the glass: nothing may select yet
		expect(liftSelection()).toBe('idle')

		vi.advanceTimersByTime(200)
		await tick()
		expect(liftSelection()).toBe('idle')
	})

	it('arms native selection once the entrance has settled', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {} })
		await hold(container)

		vi.advanceTimersByTime(340)
		await tick()

		expect(liftSelection()).toBe('armed')
		// still live text rather than a picture, so the second hold reaches it
		expect(ghost().closest('.lift-layer')).not.toHaveClass('pointer-events-none')
	})

	it('a fresh lift starts unarmed again', async () => {
		useTouch()
		const { container } = mount({ onReply: () => {} })
		await hold(container)
		vi.advanceTimersByTime(340)
		await tick()
		expect(liftSelection()).toBe('armed')

		await fireEvent.click(backdrop())
		vi.advanceTimersByTime(400)
		await tick()

		await hold(container)
		expect(liftSelection()).toBe('idle')
	})
})

describe('group thread alignment (F128, F129)', () => {
	it('keeps the swipe hint in the bubble gutter in a DM', async () => {
		const { container } = mount({ onReply: () => {} }, { align: 'left' })

		await dragRow(container)

		expect(swipeHint(container).dataset.pastAvatar).toBe('false')
		expect(swipeHint(container)).toHaveClass('-left-9')
	})

	it('pushes the swipe hint past the avatar column in a group', async () => {
		const { container } = mount({ onReply: () => {} }, inGroup)

		await dragRow(container)

		// the glyph is anchored to the bubble, so it has to clear the whole
		// avatar gutter as well or it lands on the sender's face
		expect(swipeHint(container).dataset.pastAvatar).toBe('true')
		expect(swipeHint(container)).toHaveClass('-left-19')
		expect(swipeHint(container)).not.toHaveClass('-left-9')
	})

	it('drops the avatar to the tail, not the bubble body', () => {
		const { container } = mount({}, inGroup)

		expect(senderAvatar(container).style.transform).toBe('translateY(7.6px)')
	})

	it('leaves the avatar flush when there is no tail to line up with', () => {
		const { container } = mount({}, { ...inGroup, tailStyle: 'none', showTail: false })

		expect(senderAvatar(container).style.transform).toBe('')
	})

	it('starts the reply quote above the bubble, not above the avatar', () => {
		const { container } = mount({}, { ...inGroup, replyTo: makeApiMessage() })

		expect(replyQuote(container).style.paddingLeft).toBe('2.5rem')
	})

	it('leaves the reply quote at the message edge in a DM', () => {
		const { container } = mount({}, { align: 'left', replyTo: makeApiMessage() })

		expect(replyQuote(container).style.paddingLeft).toBe('')
	})
})

/** three ids in the real `msg_` + base32(uuid7) shape, ascending. */
const OLD = 'msg_0197h2m8k0f7z9s5q3x1c4b6d8'
const MSG = 'msg_0197h2m8k9f7z9s5q3x1c4b6d8'
const THREAD = 'thread_receipts'
const ME = 'user_me'

type Participant = NonNullable<Thread['participants']>[number]

function writer(id: string, is_owner = false): Participant {
	return {
		id: `p_${id}`,
		thread_id: THREAD,
		access_level: is_owner ? 'admin' : 'editor',
		is_owner,
		kind: 'user',
		user: { id },
	}
}

function agentWriter(id: string): Participant {
	return {
		id: `p_${id}`,
		thread_id: THREAD,
		access_level: 'editor',
		is_owner: false,
		kind: 'agent',
		agent: { id, name: id },
	}
}

/** the thread the bubble is being read in, the way the page opens one. */
function openThread(participants: Participant[]): void {
	chat.activeThread = makeThread({ id: THREAD, owner_id: ME, participants })
}

/** move someone's read cursor, the way the participants fanout does. */
function setCursor(userId: string, messageId: string, at: Date | null = null): void {
	const cursors = chat.readCursors.get(THREAD) ?? new SvelteMap<string, ReadCursor>()
	cursors.set(userId, { messageId, at })
	chat.readCursors.set(THREAD, cursors)
}

function receipt(container: HTMLElement): HTMLElement | null {
	const el = container.querySelector('[data-read-receipt]')
	return el instanceof HTMLElement ? el : null
}

describe('read receipts', () => {
	// this suite exercises the TICK glyphs specifically; the app default is 'text'
	beforeEach(() => {
		readReceiptStyle.set('ticks')
	})
	afterEach(() => {
		readReceiptStyle.set('text')
		chat.readCursors.clear()
		chat.activeThread = null
	})

	it('turns the sending clock into a tick once the message is persisted', async () => {
		openThread([writer(ME, true), writer('user_them')])
		setCursor('user_them', OLD)
		const { container, rerender } = mount({}, { sending: true, messageId: null })

		expect(screen.getByLabelText('sending')).toBeInTheDocument()
		expect(receipt(container)).toBeNull()

		await rerender({ content: 'hello there', sending: false, messageId: MSG })

		expect(screen.queryByLabelText('sending')).not.toBeInTheDocument()
		expect(receipt(container)?.dataset.readReceipt).toBe('sent')
		expect(screen.getByLabelText('sent')).toBeInTheDocument()
	})

	it('goes blue when the cursor advances onto the message, live', async () => {
		openThread([writer(ME, true), writer('user_them')])
		setCursor('user_them', OLD)
		const { container } = mount({}, { messageId: MSG })

		expect(receipt(container)?.dataset.readReceipt).toBe('sent')
		expect(receipt(container)?.className).toContain('text-foreground/55')

		setCursor('user_them', MSG)
		await tick()

		expect(receipt(container)?.dataset.readReceipt).toBe('read')
		// the app's own accent, never a borrowed whatsapp teal
		expect(receipt(container)?.className).toContain('text-(--accent-primary)')
		expect(screen.getByLabelText('read')).toBeInTheDocument()
	})

	it('shows the sent tick while no cursor has been heard: sent is always knowable (B16 gates only the read upgrade)', () => {
		openThread([writer(ME, true), writer('user_them')])
		const { container } = mount({}, { messageId: MSG })

		expect(receipt(container)?.getAttribute('data-read-receipt')).toBe('sent')
		expect(screen.getByLabelText('sent')).toBeInTheDocument()
	})

	it('holds the group at one tick until every member has read it', async () => {
		openThread([writer(ME, true), writer('user_a'), writer('user_b')])
		setCursor('user_a', MSG)
		setCursor('user_b', OLD)
		const { container } = mount({}, { messageId: MSG })

		expect(receipt(container)?.dataset.readReceipt).toBe('sent')

		setCursor('user_b', MSG)
		await tick()

		expect(receipt(container)?.dataset.readReceipt).toBe('read')
	})

	it('never ticks in a solo thread: an agent is not an audience', () => {
		openThread([writer(ME, true), agentWriter('agent_1')])
		setCursor(ME, MSG)
		const { container } = mount({}, { messageId: MSG })

		expect(receipt(container)).toBeNull()
	})

	it('never ticks an incoming bubble: receipts are for your own', () => {
		openThread([writer(ME, true), writer('user_them')])
		setCursor('user_them', MSG)
		const { container } = mount({}, { messageId: MSG, align: 'left' })

		expect(receipt(container)).toBeNull()
	})

	it('leaves a failed send showing the warning, never a tick', () => {
		openThread([writer(ME, true), writer('user_them')])
		setCursor('user_them', MSG)
		const { container } = mount({}, { messageId: MSG, notDelivered: true })

		expect(screen.getByLabelText('not delivered')).toBeInTheDocument()
		expect(receipt(container)).toBeNull()
	})
})

/** the time revealed in the outer gutter on a precise cursor (F120). */
function hoverTime(container: HTMLElement): HTMLElement | null {
	const el = container.querySelector('[data-hover-time]')
	return el instanceof HTMLElement ? el : null
}

describe('bubble dates', () => {
	const SENT_AT = (() => {
		// anchored to the run date so day-graded formats stay in their buckets
		const d = new Date()
		d.setHours(14, 22, 0, 0)
		return d
	})()

	it('reserves no row above the bubble any more', () => {
		const { container } = mount({}, { timestamp: SENT_AT })

		// the old row was always in the DOM, merely transparent
		expect(container.querySelector('time')).toBeNull()
		expect(hoverTime(container)?.textContent?.trim()).toBe(clockTime(SENT_AT))
	})

	it('reveals the time in the gutter, on the cluster own timing', async () => {
		const { container } = mount({ onReply: () => {} }, { timestamp: SENT_AT })
		const time = hoverTime(container)

		expect(time?.className).toContain('opacity-0')
		expect(time?.className).toContain('right-full')

		await fireEvent.mouseEnter(bubbleRow(container))

		expect(hoverTime(container)?.className).not.toContain('opacity-0')
	})

	it('sits past the floating actions rather than underneath them', () => {
		const { container } = mount(
			{ onReply: () => {}, onDelete: () => {} },
			{ timestamp: SENT_AT }
		)

		// three action bubbles (32px) + their gaps + the cluster own margins
		expect(hoverTime(container)?.style.marginRight).toBe('120px')
	})

	it('leaves the group sender line alone, and never doubles up with it', () => {
		const { container } = mount({}, { ...inGroup, showSenderName: true, timestamp: SENT_AT })

		expect(container.querySelector('time')).toBeInTheDocument()
		expect(hoverTime(container)).toBeNull()
	})

	it('offers no gutter time on touch, where there is no hover to reveal it', () => {
		useTouch()
		const { container } = mount({}, { timestamp: SENT_AT })

		expect(hoverTime(container)).toBeNull()
	})

	it('names the day over the lifted bubble instead, where touch asks for it', async () => {
		useTouch()
		const { container } = mount({}, { timestamp: SENT_AT })
		await hold(container)

		const stamp = focusLayer()?.querySelector('[data-focus-time]')
		expect(stamp?.textContent?.trim()).toBe(formatTimeHeader(SENT_AT))
	})
})

describe('receipt text variant', () => {
	const SENT_AT = (() => {
		// anchored to the run date so day-graded formats stay in their buckets
		const d = new Date()
		d.setHours(14, 22, 0, 0)
		return d
	})()

	function receiptText(container: HTMLElement): HTMLElement | null {
		const el = container.querySelector('[data-read-receipt-text]')
		return el instanceof HTMLElement ? el : null
	}

	beforeEach(() => {
		openThread([writer(ME, true), writer('user_them')])
	})

	afterEach(() => {
		readReceiptStyle.set('ticks')
		chat.readCursors.clear()
		chat.activeThread = null
	})

	it('draws the text word by default, the owner-chosen style', () => {
		const { container } = mount({}, { messageId: MSG, isLatestOwn: true })

		expect(receipt(container)).toBeNull()
		expect(receiptText(container)).not.toBeNull()
	})

	it('swaps the tick for the word once the style says text', async () => {
		const { container } = mount({}, { messageId: MSG, isLatestOwn: true })
		readReceiptStyle.set('text')
		await tick()

		expect(receipt(container)).toBeNull()
		expect(receiptText(container)?.textContent?.trim()).toBe('delivered')
	})

	it('becomes read when the cursor reaches the message, live', async () => {
		readReceiptStyle.set('text')
		setCursor('user_them', OLD)
		const { container } = mount({}, { messageId: MSG, isLatestOwn: true })

		expect(receiptText(container)?.textContent?.trim()).toBe('delivered')

		setCursor('user_them', MSG)
		await tick()

		expect(receiptText(container)?.textContent?.trim()).toBe('read')
	})

	it('names the moment when the read came long after the message', async () => {
		readReceiptStyle.set('text')
		const readAt = new Date(SENT_AT.getTime() + 5 * 60 * 60 * 1000)
		setCursor('user_them', MSG, readAt)
		const { container } = mount({}, { messageId: MSG, isLatestOwn: true, timestamp: SENT_AT })
		await tick()

		expect(receiptText(container)?.textContent?.trim()).toBe(`read ${clockTime(readAt)}`)
	})

	it('says nothing under an older message: only the newest own one carries it', async () => {
		readReceiptStyle.set('text')
		setCursor('user_them', MSG)
		const { container } = mount({}, { messageId: MSG, isLatestOwn: false })
		await tick()

		expect(receiptText(container)).toBeNull()
		expect(receipt(container)).toBeNull()
	})

	it('leaves an incoming bubble alone, like the ticks do', async () => {
		readReceiptStyle.set('text')
		setCursor('user_them', MSG)
		const { container } = mount({}, { messageId: MSG, isLatestOwn: true, align: 'left' })
		await tick()

		expect(receiptText(container)).toBeNull()
	})
})

describe('agent blocks', () => {
	it('keep their own hover toolbar, untouched by the user-bubble redesign', () => {
		const source = readFileSync(
			resolve(process.cwd(), 'src/lib/components/chat/AssistantChatMessage.svelte'),
			'utf8'
		)

		// the agent side still owns its hover-revealed action row...
		expect(source).toContain('let showActions = $state(false)')
		expect(source).toContain('let actionsVisible = $derived(')
		expect(source).toContain(
			"{actionsVisible ? 'opacity-100' : 'pointer-events-none opacity-0'}"
		)
		// ...and none of the user bubble's new surface leaked into it
		expect(source).not.toContain('PopupMenu')
		expect(source).not.toContain('contextmenu')
		expect(source).not.toContain('more actions')
		expect(source).not.toContain('data-message-focus')
	})
})

/**
 * the lift's geometry (F137): happy-dom measures nothing on its own, so the
 * bubble is handed a rect and the surface is read back off the styles it writes.
 */
function fakeRect(left: number, top: number, width: number, height: number): DOMRect {
	return {
		left,
		top,
		width,
		height,
		right: left + width,
		bottom: top + height,
		x: left,
		y: top,
		toJSON: () => ({}),
	} as DOMRect
}

/** hand a rect to the bubble (and to the time, once it mounts); zero to the rest. */
function stageRects(bubble: DOMRect, stamp = fakeRect(0, 0, 90, 16)): () => void {
	const original = Element.prototype.getBoundingClientRect
	const spy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
		this: Element
	) {
		if (this.matches('[data-focus-time]')) return stamp
		if (this.classList.contains('bubble-wrapper')) return bubble
		return original.call(this)
	})
	return () => spy.mockRestore()
}

function focusStamp(): HTMLElement {
	const el = document.querySelector('[data-focus-time]')
	if (!(el instanceof HTMLElement)) throw new Error('focus time not rendered')
	return el
}

function liftLayer(): HTMLElement {
	const el = document.querySelector('.lift-layer')
	if (!(el instanceof HTMLElement)) throw new Error('lift layer not rendered')
	return el
}

function px(value: string): number {
	return Number.parseFloat(value)
}

/** anchored to the run date so the day-graded formats stay in their buckets. */
function sentAt(): Date {
	const date = new Date()
	date.setHours(14, 22, 0, 0)
	return date
}

describe('the time over a lifted bubble (F137)', () => {
	const SENT_AT = sentAt()
	let restore: (() => void) | null = null

	afterEach(() => {
		restore?.()
		restore = null
	})

	/** lift the bubble, then let the stamp measure itself. */
	async function lift(container: HTMLElement): Promise<void> {
		await hold(container)
		await tick()
		await tick()
	}

	it('keeps the stamp on ONE line, however narrow the bubble is', async () => {
		useTouch()
		restore = stageRects(fakeRect(300, 400, 50, 42))
		const { container } = mount({}, { timestamp: SENT_AT })
		await lift(container)

		expect(focusStamp().className).toContain('whitespace-nowrap')
		// never pinned to the bubble's width: that is what used to wrap it
		expect(focusStamp().style.width).toBe('')
	})

	it('never lets the stamp reach the bubble it names', async () => {
		useTouch()
		restore = stageRects(fakeRect(300, 400, 50, 42))
		const { container } = mount({}, { timestamp: SENT_AT })
		await lift(container)

		// its own measured height sits ABOVE the lifted bubble's top edge
		const liftedTop = px(liftLayer().style.top) - (42 * 0.07) / 2
		expect(px(focusStamp().style.top) + 16).toBeLessThanOrEqual(liftedTop)
	})

	it('lets the stamp be wider than the bubble, centred on the lift', async () => {
		useTouch()
		restore = stageRects(fakeRect(300, 400, 50, 42))
		const { container } = mount({}, { timestamp: SENT_AT })
		await lift(container)

		// 90 wide over a 50 wide bubble: centred, so it overhangs both sides
		expect(px(focusStamp().style.left)).toBeCloseTo(300 + 25 - 45, 5)
	})

	it('clamps the stamp into the viewport rather than off its edge', async () => {
		useTouch()
		restore = stageRects(fakeRect(window.innerWidth - 56, 400, 50, 42))
		const { container } = mount({}, { timestamp: SENT_AT })
		await lift(container)

		expect(px(focusStamp().style.left)).toBe(window.innerWidth - 12 - 90)
	})
})

describe('a lift that would not fit (F137)', () => {
	const SENT_AT = sentAt()
	let restore: (() => void) | null = null

	afterEach(() => {
		restore?.()
		restore = null
	})

	it('leaves a bubble with room to itself exactly where it sits', async () => {
		useTouch()
		restore = stageRects(fakeRect(100, 300, 200, 60))
		const { container } = mount({}, { timestamp: SENT_AT })
		await hold(container)

		expect(px(liftLayer().style.top)).toBe(300)
	})

	it('brings a bubble scrolled under the top back onto the screen', async () => {
		useTouch()
		restore = stageRects(fakeRect(100, -40, 200, 120))
		const { container } = mount({ onReply: () => {} }, { timestamp: SENT_AT })
		await hold(container)

		// the stamp above it and the grown edge both clear the top padding
		const top = px(liftLayer().style.top)
		expect(top).toBeGreaterThan(-40)
		expect(top - (120 * 0.07) / 2 - 22 - 16).toBeGreaterThanOrEqual(12)
	})

	it('lifts a bubble sitting on the bottom edge clear of it', async () => {
		useTouch()
		restore = stageRects(fakeRect(100, window.innerHeight - 40, 200, 120))
		const { container } = mount({ onReply: () => {} }, { timestamp: SENT_AT })
		await hold(container)

		const top = px(liftLayer().style.top)
		expect(top).toBeLessThan(window.innerHeight - 40)
		expect(top + 120 + (120 * 0.07) / 2).toBeLessThanOrEqual(window.innerHeight - 12)
	})

	it('pins the top of a bubble taller than the screen, and keeps the actions reachable', async () => {
		useTouch()
		const tall = window.innerHeight * 2
		restore = stageRects(fakeRect(100, -200, 200, tall))
		const { container } = mount(
			{ onReply: () => {}, onDelete: () => {} },
			{ timestamp: SENT_AT }
		)
		await hold(container)

		// the head of the message is what the reader is holding: it takes the top
		const top = px(liftLayer().style.top)
		expect(top - (tall * 0.07) / 2 - 22 - 16).toBeCloseTo(12, 5)

		// ...and the column does not ride the bubble off the bottom with it
		const column = focusLayer()?.querySelector('.flex-col')
		expect(column).toBeInstanceOf(HTMLElement)
		if (column instanceof HTMLElement) {
			expect(px(column.style.top)).toBeLessThanOrEqual(window.innerHeight - 12)
		}
	})
})

describe('normal mode reserves nothing for the time (F137)', () => {
	const SENT_AT = sentAt()

	it('leaves the row with no in-flow stamp above or around the bubble', () => {
		const { container } = mount({}, { timestamp: SENT_AT })
		const row = bubbleRow(container)

		// the gutter reveal is the only stamp in normal mode, and it is out of flow
		expect(hoverTime(container)?.className).toContain('absolute')

		// everything else in the row is the bubble itself
		const inFlow = [...row.children].filter((el) => !el.className.includes('absolute'))
		expect(inFlow).toHaveLength(1)
		expect(inFlow[0].querySelector('.bubble-content')).not.toBeNull()
	})

	it('adds no margin or floor of its own around the bubble', () => {
		const { container } = mount({}, { timestamp: SENT_AT })
		const row = bubbleRow(container)
		const style = getComputedStyle(row)

		expect(style.marginTop || '0px').toBe('0px')
		expect(style.marginBottom || '0px').toBe('0px')
		expect(style.minHeight || '0px').toBe('0px')
		// nothing sits between the top of the bubble row and the bubble
		expect(row.querySelector('.bubble-wrapper')?.previousElementSibling).toBeNull()
	})
})

describe('a tap tells you when (F137)', () => {
	const SENT_AT = sentAt()

	function detail(container: HTMLElement): HTMLElement | null {
		const el = container.querySelector('[data-message-detail]')
		return el instanceof HTMLElement ? el : null
	}

	function bubbleContent(container: HTMLElement): HTMLElement {
		const el = container.querySelector('.bubble-content')
		if (!(el instanceof HTMLElement)) throw new Error('bubble not rendered')
		return el
	}

	afterEach(() => {
		readReceiptStyle.set('ticks')
		chat.readCursors.clear()
		chat.activeThread = null
	})

	it('opens the line on a tap and closes it on the next one', async () => {
		useTouch()
		const { container } = mount({}, { timestamp: SENT_AT })

		expect(detail(container)).toBeNull()

		await fireEvent.click(bubbleContent(container))
		expect(detail(container)?.textContent?.trim()).toBe(formatTimeHeader(SENT_AT))

		// a second tap sends it back out: it is going the moment it is asked to
		await fireEvent.click(bubbleContent(container))
		expect(detail(container)).toHaveAttribute('inert')
	})

	it('moves the line to the bubble you just tapped', async () => {
		useTouch()
		const first = mount({}, { timestamp: SENT_AT })
		const second = mount({}, { timestamp: SENT_AT })

		await fireEvent.click(bubbleContent(first.container))
		expect(detail(first.container)).not.toBeNull()

		await fireEvent.click(bubbleContent(second.container))
		expect(detail(second.container)).not.toHaveAttribute('inert')
		expect(detail(first.container)).toHaveAttribute('inert')
	})

	it('is not what a press-and-hold releases into', async () => {
		useTouch()
		const { container } = mount({}, { timestamp: SENT_AT })
		await hold(container)

		// the hold swallows its own click, so the lift never doubles as a tap
		await fireEvent.click(bubbleContent(container))

		expect(detail(container)).toBeNull()
	})

	it('leaves a link inside the bubble to do its own job', async () => {
		useTouch()
		const { container } = mount({}, { timestamp: SENT_AT })
		const link = document.createElement('a')
		link.href = '#somewhere'
		link.textContent = 'a link'
		bubbleContent(container).appendChild(link)

		await fireEvent.click(link)

		expect(detail(container)).toBeNull()
	})

	it('names where your own message got to, whatever the receipt style is', async () => {
		useTouch()
		openThread([writer(ME, true), writer('user_them')])
		setCursor('user_them', MSG)
		const { container } = mount({}, { timestamp: SENT_AT, messageId: MSG })

		await fireEvent.click(bubbleContent(container))

		expect(detail(container)?.textContent).toContain(formatTimeHeader(SENT_AT))
		expect(detail(container)?.textContent).toContain('read')
	})

	it('gives an incoming bubble the time alone: a receipt is not yours to report', async () => {
		useTouch()
		openThread([writer(ME, true), writer('user_them')])
		setCursor('user_them', MSG)
		const { container } = mount({}, { timestamp: SENT_AT, messageId: MSG, align: 'left' })

		await fireEvent.click(bubbleContent(container))

		expect(detail(container)?.textContent?.trim()).toBe(formatTimeHeader(SENT_AT))
	})

	it('stands in for the standing receipt word rather than repeating it', async () => {
		useTouch()
		readReceiptStyle.set('text')
		openThread([writer(ME, true), writer('user_them')])
		setCursor('user_them', MSG)
		const { container } = mount({}, { timestamp: SENT_AT, messageId: MSG, isLatestOwn: true })

		expect(container.querySelector('[data-read-receipt-text]')).not.toBeNull()

		await fireEvent.click(bubbleContent(container))

		expect(container.querySelector('[data-read-receipt-text]')).toBeNull()
		expect(detail(container)).not.toBeNull()
	})

	it('reserves nothing while it is closed', () => {
		useTouch()
		mount({}, { timestamp: SENT_AT })

		expect(document.querySelector('[data-message-detail]')).toBeNull()
	})
})
