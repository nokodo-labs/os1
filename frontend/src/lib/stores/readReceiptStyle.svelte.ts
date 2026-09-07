/**
 * how read receipts are drawn: ticks beside the bubble, or imessage's word
 * under the newest one.
 *
 * a LOCAL choice for now - the whole read/write pair lives here, so when the
 * synced preference field ships (B28) this file is the only one that changes:
 * everything else reads `readReceiptStyle.style`.
 */

import { browser } from '$app/environment'

export type ReadReceiptStyle = 'ticks' | 'text'

/** the imessage word is the owner-chosen default (2026-09-03). */
export const DEFAULT_READ_RECEIPT_STYLE: ReadReceiptStyle = 'text'

const STORAGE_KEY = 'read-receipt-style'

function resolve(raw: string | null): ReadReceiptStyle {
	return raw === 'ticks' || raw === 'text' ? raw : DEFAULT_READ_RECEIPT_STYLE
}

function readStored(): ReadReceiptStyle {
	if (!browser) return DEFAULT_READ_RECEIPT_STYLE
	try {
		return resolve(window.localStorage.getItem(STORAGE_KEY))
	} catch {
		return DEFAULT_READ_RECEIPT_STYLE
	}
}

class ReadReceiptStyleStore {
	style = $state<ReadReceiptStyle>(readStored())

	set = (next: ReadReceiptStyle): void => {
		this.style = next
		if (!browser) return
		try {
			if (next === DEFAULT_READ_RECEIPT_STYLE) window.localStorage.removeItem(STORAGE_KEY)
			else window.localStorage.setItem(STORAGE_KEY, next)
		} catch {
			// storage unavailable: the choice simply does not survive a reload
		}
	}
}

export const readReceiptStyle = new ReadReceiptStyleStore()
