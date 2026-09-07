/**
 * reveal a message in the transcript: scroll it into view and flash it.
 *
 * the chat instance of the shared anchor focus (`utils/anchorFocus`). rendered
 * messages register themselves through `messageAnchor`, so callers address a
 * message by id and never touch the DOM. a request for a message that has not
 * mounted yet is held until it registers, which is what lets a reply jump and a
 * search anchor share one call even though the search anchor arrives before the
 * branch has finished loading.
 */

import { createAnchorFocus } from '$lib/utils/anchorFocus'

/**
 * a jump lands mid-transcript, so the flash has to survive the smooth scroll and
 * still be burning when the reader's eye arrives: ~0.3s rise, ~0.9s at full
 * tint, then a 1.8s fade out.
 */
export const MESSAGE_FLASH_MS = 3400

const focus = createAnchorFocus({
	flashMs: MESSAGE_FLASH_MS,
	mark: (node, id) => {
		node.dataset.messageId = id
	},
})

/** mark an element as the scroll target for a message id. */
export const messageAnchor = focus.anchor
export const revealMessage = focus.reveal
export const cancelMessageReveal = focus.cancel
