/**
 * the receipts style choice (F127): local until the synced field ships (B28),
 * so the whole contract is "it survives a reload, and never throws when storage
 * will not have it".
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('$app/environment', () => ({ browser: true, dev: false }))

const { DEFAULT_READ_RECEIPT_STYLE, readReceiptStyle } =
	await import('$lib/stores/readReceiptStyle.svelte')

const STORAGE_KEY = 'read-receipt-style'

beforeEach(() => {
	window.localStorage.clear()
	readReceiptStyle.set(DEFAULT_READ_RECEIPT_STYLE)
})

afterEach(() => {
	vi.restoreAllMocks()
	window.localStorage.clear()
	readReceiptStyle.set(DEFAULT_READ_RECEIPT_STYLE)
})

describe('readReceiptStyle', () => {
	it('starts on text, the owner-chosen default', () => {
		expect(DEFAULT_READ_RECEIPT_STYLE).toBe('text')
		expect(readReceiptStyle.style).toBe('text')
	})

	it('remembers a pick, and stores nothing for the default', () => {
		readReceiptStyle.set('ticks')

		expect(readReceiptStyle.style).toBe('ticks')
		expect(window.localStorage.getItem(STORAGE_KEY)).toBe('ticks')

		readReceiptStyle.set('text')

		expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
	})

	it('still switches when storage refuses to write', () => {
		vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
			throw new Error('quota exceeded')
		})

		expect(() => readReceiptStyle.set('ticks')).not.toThrow()
		expect(readReceiptStyle.style).toBe('ticks')
	})
})
