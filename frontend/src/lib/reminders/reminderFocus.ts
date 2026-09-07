/**
 * reveal a reminder in its list: scroll it into view and flash it.
 *
 * the reminders instance of the shared anchor focus (`utils/anchorFocus`), used
 * by search results that anchor a matched reminder inside its list.
 */

import { createAnchorFocus } from '$lib/utils/anchorFocus'

// reminder rows are rounded-4xl, so the flash follows the row's own corner
const focus = createAnchorFocus({ radius: '2rem' })

/** mark an element as the scroll target for a reminder id. */
export const reminderAnchor = focus.anchor
export const revealReminder = focus.reveal
export const cancelReminderReveal = focus.cancel
