<script module lang="ts">
	/**
	 * which bubble is showing its tapped detail line. one at a time across the
	 * whole transcript, the way imessage moves the line to the message you just
	 * tapped instead of stacking a second one. transient: nothing persists it.
	 */
	let openDetailKey = $state<symbol | null>(null)
</script>

<script lang="ts">
	import { contextmenu } from '$lib/attachments/contextmenu'
	import { portal } from '$lib/attachments/portal'
	import { swipe } from '$lib/attachments/swipe'
	import { getApiBaseUrl } from '$lib/api/client'
	import {
		extractFileParts,
		extractMediaParts,
		type FileContentPart,
		type MediaContentPart,
	} from '$lib/chat/helpers'
	import { clockTime, formatTimeHeader, receiptStamp } from '$lib/chat/chatTimestamps'
	import {
		clampSpan,
		fitTranslation,
		liftEnsembleBox,
		type Offset,
		type SafeArea,
	} from '$lib/chat/liftGeometry'
	import { messageReceipt, receiptAudience } from '$lib/chat/readReceipts'
	import type { ApiMessage, ResourceAttachment } from '$lib/chat/types'
	import AttachmentRefs from '$lib/components/chat/AttachmentRefs.svelte'
	import MediaAttachments from '$lib/components/chat/MediaAttachments.svelte'
	import ReplyPreview from '$lib/components/chat/ReplyPreview.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowUpCircle from '$lib/components/icons/ArrowUpCircle.svelte'
	import ArrowUturnLeft from '$lib/components/icons/ArrowUturnLeft.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import CheckDouble from '$lib/components/icons/CheckDouble.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import Clipboard from '$lib/components/icons/Clipboard.svelte'
	import Clock from '$lib/components/icons/Clock.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import ExclamationTriangle from '$lib/components/icons/ExclamationTriangle.svelte'
	import FloppyDisk from '$lib/components/icons/FloppyDisk.svelte'
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { IconButton, MenuItem, MenuSeparator, PopupMenu } from '$lib/components/primitives'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { chat as chatStore } from '$lib/stores/chat.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { BubbleTailStyle } from '$lib/stores/preferences.svelte'
	import { readReceiptStyle } from '$lib/stores/readReceiptStyle.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { getUserInitials } from '$lib/utils'
	import { tick, type Snippet } from 'svelte'
	import type { Attachment } from 'svelte/attachments'
	import { backOut, cubicOut } from 'svelte/easing'
	import { fade, fly, scale, type TransitionConfig } from 'svelte/transition'

	interface Props {
		content: string
		contentParts?: ApiMessage['content']
		attachmentRefs?: ResourceAttachment[]
		optimisticMediaParts?: MediaContentPart[]
		optimisticFileParts?: FileContentPart[]
		timestamp?: Date
		align?: 'left' | 'right'
		siblingCount?: number
		currentSiblingIndex?: number
		onPrevious?: () => void
		onNext?: () => void
		tailStyle?: BubbleTailStyle
		showTail?: boolean
		viewTransitionName?: string
		sending?: boolean
		/** the send never reached the backend, so nothing was written. */
		notDelivered?: boolean
		/**
		 * the persisted message's id, once it has one. read receipts hang off it:
		 * an optimistic bubble has nothing to compare a cursor against.
		 */
		messageId?: string | null
		/**
		 * the newest of YOUR messages in the thread. imessage names the receipt
		 * under that one alone, so the word travels down the transcript instead of
		 * repeating beside every bubble.
		 */
		isLatestOwn?: boolean
		/** quoted message this one answers, already resolved by the caller. */
		replyTo?: ApiMessage | null
		replyToAuthor?: string | null
		/**
		 * who wrote this, for multi-writer threads. resolved from the thread
		 * roster, not carried on the message. omit in single-writer threads so
		 * they keep looking exactly as they do today.
		 */
		senderName?: string | null
		senderAvatarUrl?: string | null
		/** first bubble of a same-author run: the one that shows the name. */
		showSenderName?: boolean
		/** last bubble of a same-author run: the one that shows the avatar. */
		showSenderAvatar?: boolean
		/** quote this message. drives both the swipe gesture and the reply action. */
		onReply?: () => void
		/** omitted on messages the viewer may not delete (F1). */
		onDelete?: () => void
		onEditSave?: (newContent: string) => Promise<void>
		onEditSaveAsCopy?: (newContent: string) => Promise<void>
		/** attached to the root on mount, used by the page to play the entrance
		 *  animation for live (cross-session) messages. */
		entrance?: Attachment<HTMLElement>
	}

	let {
		content,
		contentParts,
		attachmentRefs,
		optimisticMediaParts,
		optimisticFileParts,
		timestamp,
		align = 'right',
		siblingCount = 1,
		currentSiblingIndex = 0,
		onPrevious,
		onNext,
		tailStyle = 'none',
		showTail = false,
		viewTransitionName,
		sending = false,
		notDelivered = false,
		messageId = null,
		isLatestOwn = false,
		replyTo = null,
		replyToAuthor = null,
		senderName = null,
		senderAvatarUrl = null,
		showSenderName = false,
		showSenderAvatar = false,
		onReply,
		onDelete,
		onEditSave,
		onEditSaveAsCopy,
		entrance = () => {},
	}: Props = $props()

	const apiBase = getApiBaseUrl()
	const mediaParts = $derived(
		contentParts ? extractMediaParts(contentParts, apiBase) : (optimisticMediaParts ?? [])
	)
	const fileParts = $derived(
		contentParts ? extractFileParts(contentParts, apiBase) : (optimisticFileParts ?? [])
	)
	const hasMedia = $derived(mediaParts.length > 0 || fileParts.length > 0)
	const refs = $derived(attachmentRefs ?? [])

	// edit state
	let isEditing = $state(false)
	let editContent = $state('')
	let editTextarea: HTMLTextAreaElement | undefined = $state()
	let isSaving = $state(false)

	let messageRef: HTMLElement | undefined = $state()
	let bubbleRef: HTMLElement | undefined = $state()
	let menuTriggerRef: HTMLElement | null = $state(null)
	let isPointerOver = $state(false)
	let copied = $state(false)
	let copiedTimer: ReturnType<typeof setTimeout> | undefined

	/**
	 * what the bubble is offering right now: nothing, the ellipsis menu on its own
	 * (precise cursor), or focus - the bubble lifted out of a dimmed, blurred
	 * transcript with its actions floating around it.
	 */
	type ActionSurface = 'none' | 'menu' | 'focus'
	let surface = $state<ActionSurface>('none')

	interface FocusGeometry {
		left: number
		right: number
		top: number
		width: number
		height: number
		viewportWidth: number
		/** how far the whole ensemble moves to sit inside the visible viewport. */
		fit: Offset
		/** what "inside" means here: past the island, off the composer, with padding. */
		safe: SafeArea
	}
	/** the lift source's rect, frozen at entrance: the ghost is placed against it. */
	let focusGeom = $state<FocusGeometry | null>(null)
	/** the time's own box, so it can never be positioned into the bubble it names. */
	let stampBox = $state({ width: 0, height: 0 })
	/**
	 * the original stays hidden while the ghost stands in for it. it is released
	 * on a timer, never on the ghost's outro: an outro that is dropped (offscreen
	 * tab, a cancelled animation, motion turned off) would strand the bubble
	 * invisible, and a message you cannot see is worse than one that settles early.
	 */
	let liftActive = $state(false)
	let settleTimer: ReturnType<typeof setTimeout> | undefined
	/**
	 * the hold that LIFTS the bubble must not also select its text: the lifted
	 * copy mounts inert and opts into selection once the entrance has settled, so
	 * a SECOND press-and-hold is what reaches the platform's own selection (F126).
	 */
	let selectionArmed = $state(false)
	let armTimer: ReturnType<typeof setTimeout> | undefined
	/** the fuller menu is a step INTO focus, opened from the ellipsis bubble. */
	let focusMenuOpen = $state(false)
	let liftLayer = $state<HTMLElement | null>(null)
	/** a press that began on the lifted bubble is the reader working with the
	 *  text, not a press outside it: it must never dismiss. */
	let pressStartedInLift = false
	/** ghost -> original delta, measured at dismissal in case the row has moved. */
	let settleOffset = $state({ x: 0, y: 0 })

	/** how far the bubble grows when it takes focus. */
	const LIFT_SCALE = 1.07
	const LIFT_MS = 260
	const BACKDROP_MS = 200
	/** gap between the settling of one floating button and the next. */
	const STAGGER_MS = 45
	/** distance between the lifted bubble and the buttons floating beside it. */
	const FLOAT_GAP_PX = 10
	/** gap between the lifted bubble and the menu below it. */
	const MENU_GAP_PX = 12
	/** gap between the lifted bubble and the time sitting above it. */
	const FOCUS_TIME_GAP_PX = 22
	/** one line of `text-xs`: what the time takes before it has been measured. */
	const FOCUS_TIME_LINE_PX = 16
	/** the column of floating actions stacks on `gap-2`. */
	const FLOAT_STACK_GAP_PX = 8
	/** breathing room between the lifted ensemble and every edge it must clear. */
	const VIEWPORT_PAD_PX = 12
	/** the tapped detail line: a quick slide, not a reveal you wait for. */
	const DETAIL_MS = 160
	/**
	 * android drops the virtual keyboard on a ~500ms hold and nothing can prevent
	 * it; the reflow that follows must not read as the user scrolling away.
	 */
	const SCROLL_GRACE_MS = 400
	/**
	 * how long the lifted copy stays unselectable. it is a timer and not the
	 * lifting press's own pointerup because that pointerup is not guaranteed to
	 * arrive: the same android hold that drops the keyboard reflows the page, and
	 * the press can end as a `pointercancel` on another element - which would
	 * strand the text permanently unselectable. it outlasts both the entrance and
	 * the ~500ms hold android recognises on its own, so the opening press is over
	 * well before the text can answer a new one.
	 */
	const SELECT_ARM_MS = 340

	const reduceMotion = $derived(device.prefersReducedMotion)
	const liftMs = $derived(reduceMotion ? 0 : LIFT_MS)
	const backdropMs = $derived(reduceMotion ? 0 : BACKDROP_MS)
	const staggerMs = $derived(reduceMotion ? 0 : STAGGER_MS)
	const liftScale = $derived(reduceMotion ? 1 : LIFT_SCALE)
	const detailMs = $derived(reduceMotion ? 0 : DETAIL_MS)

	/**
	 * a precise cursor gets the floating corner buttons; everything else reaches
	 * the same actions by holding the bubble. `(hover: hover) and (pointer: fine)`,
	 * read off the device store.
	 */
	const canHover = $derived(device.hasHover && !device.isCoarsePointer)

	/**
	 * the bubble grows into focus and settles back along the same curve.
	 *
	 * the layer is already positioned where the ensemble FITS, so the entrance is
	 * the walk from where the bubble really sits to there - one motion with the
	 * scale rather than a jump before it - and the dismissal is the same walk
	 * back, which is what hands the row its own position again.
	 */
	const lift: (node: Element) => TransitionConfig = () => ({
		duration: liftMs,
		easing: backOut,
		css: (t) => {
			const fit = focusGeom?.fit ?? { x: 0, y: 0 }
			const x = (settleOffset.x - fit.x) * (1 - t)
			const y = (settleOffset.y - fit.y) * (1 - t)
			return `transform: translate(${x}px, ${y}px) scale(${1 + (liftScale - 1) * t})`
		},
	})

	/** the text bubble is what lifts; a message made only of attachments has none. */
	function liftSource(): HTMLElement | undefined {
		return bubbleRef ?? messageRef
	}

	/**
	 * what the lift is allowed to cover: the VISIBLE viewport, minus the island it
	 * would otherwise slide under and the composer it would sit on top of. both
	 * are read rather than guessed - the island is themed and the composer grows
	 * with the draft - and both fall back to the viewport's own edge.
	 */
	function safeArea(): SafeArea {
		const top = device.viewportOffsetTop
		const height = device.viewportHeight || window.innerHeight
		const width = device.viewportWidth || window.innerWidth
		const island = document.querySelector('header')?.getBoundingClientRect().bottom ?? top
		const composer =
			document.querySelector('[data-chat-input]')?.getBoundingClientRect().top ?? top + height
		return {
			top: Math.max(top, island) + VIEWPORT_PAD_PX,
			bottom: Math.min(top + height, composer) - VIEWPORT_PAD_PX,
			left: VIEWPORT_PAD_PX,
			right: width - VIEWPORT_PAD_PX,
		}
	}

	/** a hold and a right-click share one entrance: the bubble lifts into focus. */
	function openFocus(): void {
		const source = liftSource()
		if (!source) return
		const rect = source.getBoundingClientRect()
		const safe = safeArea()
		const fit = fitTranslation(
			liftEnsembleBox({
				rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
				scale: liftScale,
				stampHeight: timestamp ? FOCUS_TIME_LINE_PX : 0,
				stampGap: FOCUS_TIME_GAP_PX,
				floatsWidth: CORNER_BUTTON_PX,
				floatsHeight: floatColumnHeight,
				floatGap: FLOAT_GAP_PX,
				align,
			}),
			safe
		)
		focusGeom = {
			left: rect.left,
			right: rect.right,
			top: rect.top,
			width: rect.width,
			height: rect.height,
			viewportWidth: window.innerWidth,
			fit,
			safe,
		}
		settleOffset = { x: 0, y: 0 }
		clearTimeout(settleTimer)
		clearTimeout(armTimer)
		selectionArmed = false
		armTimer = setTimeout(() => {
			selectionArmed = true
		}, SELECT_ARM_MS)
		focusMenuOpen = false
		pressStartedInLift = false
		liftActive = true
		surface = 'focus'
	}

	/** the menu is a layer above focus: closing it steps back to the lifted
	 *  bubble, and only a press outside everything takes the whole thing down. */
	function dismissMenu(): void {
		if (surface === 'focus' && focusMenuOpen) {
			focusMenuOpen = false
			return
		}
		closeSurface()
	}

	/** the reader is holding, dragging or has text selected inside the lift. */
	function isWorkingInLift(): boolean {
		if (pressStartedInLift) return true
		const selection = window.getSelection()
		if (!selection || selection.isCollapsed || selection.rangeCount === 0) return false
		return liftLayer?.contains(selection.anchorNode) ?? false
	}

	function closeSurface(): void {
		if (surface === 'focus') {
			const rect = liftSource()?.getBoundingClientRect()
			settleOffset =
				rect && focusGeom
					? { x: rect.left - focusGeom.left, y: rect.top - focusGeom.top }
					: { x: 0, y: 0 }
			releaseLift()
		}
		clearTimeout(armTimer)
		selectionArmed = false
		focusMenuOpen = false
		surface = 'none'
	}

	/** hand the bubble back once the ghost has had its settle, or at once if it
	 *  never had one to play. */
	function releaseLift(): void {
		clearTimeout(settleTimer)
		if (liftMs === 0) {
			liftActive = false
			return
		}
		settleTimer = setTimeout(() => {
			liftActive = false
		}, liftMs)
	}

	/**
	 * the lifted bubble is a clone of the real one: the transcript lives inside a
	 * scroll container, so raising the original above a page-level backdrop is not
	 * something z-index can be trusted with. the copy is inert - its interactive
	 * parts are stripped, and the tail goes with them, because the tail's cutout is
	 * painted in the page background, which is not what sits behind it out here.
	 */
	function liftGhost(): Attachment<HTMLElement> {
		return (node) => {
			const source = liftSource()
			if (!source) return
			const copy = source.cloneNode(true)
			if (!(copy instanceof HTMLElement)) return
			copy.style.visibility = ''
			// imessage tails are background-independent since F119 and may stay on
			// the lifted ghost; whatsapp's border-trick tail still assumes the page
			// background, so those classes keep coming off.
			copy.classList.remove('whatsapp-right', 'whatsapp-left')
			copy.querySelectorAll('[data-corner-actions], [data-swipe-hint]').forEach((el) => {
				el.remove()
			})
			// a view transition name may only belong to one element at a time
			copy.querySelectorAll('.bubble-content').forEach((el) => {
				if (el instanceof HTMLElement) el.style.viewTransitionName = ''
			})
			node.appendChild(copy)
			return () => copy.remove()
		}
	}

	$effect(() => {
		if (surface !== 'focus') return
		const openedAt = Date.now()
		const onScroll = (): void => {
			if (Date.now() - openedAt < SCROLL_GRACE_MS) return
			// a selection drag scrolls the page to reach more text, and the native
			// selection handles are not DOM: a live selection is the only signal.
			if (isWorkingInLift()) return
			closeSurface()
		}
		const onKeyDown = (event: KeyboardEvent): void => {
			if (event.key !== 'Escape') return
			// the menu owns this one; it steps back to the lifted bubble
			if (focusMenuOpen) return
			event.preventDefault()
			closeSurface()
		}
		window.addEventListener('scroll', onScroll, true)
		window.addEventListener('keydown', onKeyDown)
		return () => {
			window.removeEventListener('scroll', onScroll, true)
			window.removeEventListener('keydown', onKeyDown)
		}
	})

	$effect(() => () => {
		clearTimeout(copiedTimer)
		clearTimeout(settleTimer)
		clearTimeout(armTimer)
		// the open line belongs to a bubble that is going: nothing else can close it
		if (openDetailKey === detailKey) openDetailKey = null
	})

	async function copyMessage(): Promise<void> {
		try {
			if (navigator.clipboard && window.isSecureContext) {
				await navigator.clipboard.writeText(content)
			} else {
				const textArea = document.createElement('textarea')
				textArea.value = content
				textArea.style.position = 'fixed'
				textArea.style.top = '0'
				textArea.style.left = '0'
				document.body.appendChild(textArea)
				textArea.select()
				document.execCommand('copy')
				textArea.remove()
			}
			copied = true
			clearTimeout(copiedTimer)
			copiedTimer = setTimeout(() => {
				copied = false
			}, 1383)
		} catch (e) {
			console.error('failed to copy message', e)
		}
	}

	function startEditing() {
		isEditing = true
		editContent = content
	}

	function cancelEditing() {
		isEditing = false
		editContent = ''
	}

	async function saveEdit() {
		if (!onEditSave || isSaving || !editContent.trim()) return
		isSaving = true
		try {
			await onEditSave(editContent.trim())
			isEditing = false
			editContent = ''
		} finally {
			isSaving = false
		}
	}

	async function saveAsCopy() {
		if (!onEditSaveAsCopy || isSaving || !editContent.trim()) return
		isSaving = true
		try {
			await onEditSaveAsCopy(editContent.trim())
			isEditing = false
			editContent = ''
		} finally {
			isSaving = false
		}
	}

	// focus & size the textarea when entering edit mode
	$effect(() => {
		if (!isEditing || !editTextarea) return
		const el = editTextarea
		void tick().then(() => {
			el.style.height = ''
			el.style.height = `${el.scrollHeight}px`
			if (!device.isMobile) {
				el.focus()
				el.setSelectionRange(el.value.length, el.value.length)
			}
		})
	})

	const canEdit = $derived(!!(onEditSave || onEditSaveAsCopy))

	/** 0..1 travel of an in-flight swipe, drives the reply affordance. */
	let swipeProgress = $state(0)

	// only other people's messages get an avatar gutter; your own bubbles are
	// already identified by side, and a solo thread has nobody to disambiguate.
	const hasAvatarGutter = $derived(align === 'left' && senderName !== null && !isEditing)
	const senderInitials = $derived(getUserInitials(senderName ?? ''))

	/** avatar box, and the gutter the name lines up with. */
	const AVATAR_SIZE = 'size-8'
	/** avatar width + its gap, for aligning things under the bubble. */
	const AVATAR_GUTTER = '2.5rem'
	/** how far the imessage tail hangs below the bubble's bottom edge (F119 r4). */
	const TAIL_DESCENT_PX = 7.6
	/**
	 * the avatar's baseline is the TAIL's end, not the bubble body's, so it sits a
	 * touch lower than the bubble the way imessage draws it. a transform rather
	 * than a margin: the row's height must not move with it.
	 */
	const avatarDrop = $derived(
		showSenderAvatar && showTail && tailStyle === 'imessage'
			? `translateY(${TAIL_DESCENT_PX}px)`
			: undefined
	)
	/**
	 * where the sender line starts: past the avatar gutter (2rem avatar + 0.5rem
	 * gap), then far enough into the bubble's corner to clear the curve without
	 * looking detached from the text below it.
	 */
	const senderInset = $derived(hasAvatarGutter ? '3.25rem' : '0.75rem')

	/** an identified sender carries the time on its own line, not above it. */
	const showsSenderLine = $derived(showSenderName && senderName !== null && !isEditing)

	// an incoming bubble is a neutral surface: the accent identifies YOUR side of
	// the conversation, so painting everyone with it erases that distinction.
	const isIncoming = $derived(align === 'left')

	/** the time rides with the actions: hover on a cursor, focus on touch. */
	const isHovered = $derived(isPointerOver || surface !== 'none')

	/**
	 * receipts ride on your OWN bubbles: an incoming one is not yours to report on.
	 * the rule itself lives in `$lib/chat/readReceipts`; what belongs here is
	 * reading the store's cursor map, so a tick turns blue the moment a cursor
	 * moves rather than on the next thread load. SENT is always knowable (the
	 * message has a real id), so a persisted message in a people thread draws
	 * the single tick even while cursors are unheard (B16); only the READ
	 * upgrade waits for evidence - a guessed blue tick is worse than none.
	 */
	const receipt = $derived.by(() => {
		if (align !== 'right' || !messageId || isEditing) return null
		const thread = chatStore.activeThread
		if (!thread) return null
		if (receiptAudience(thread, session.currentUserId).length === 0) return null
		const cursors = chatStore.threadReadCursors(thread.id)
		const result = messageReceipt(messageId, thread, cursors, session.currentUserId)
		if (!result.sent) return null
		return result
	})

	const receiptGlyph = $derived(
		receipt === null ? null : receipt.state === 'read' ? 'read' : 'sent'
	)

	/**
	 * the two ways a receipt reads (F127): ticks in the slot beside the bubble,
	 * or imessage's quiet word under the newest message that has one. the
	 * derivation above is shared - only this branches.
	 */
	const receiptsAsText = $derived(readReceiptStyle.style === 'text')
	const showsReceiptGlyph = $derived(receiptGlyph !== null && !receiptsAsText)

	/**
	 * the word, graded by WHEN the read happened: right after the message it is
	 * bare, hours or days later it names the moment. "delivered" is always bare -
	 * delivery IS the message's own time, so there is nothing to grade.
	 */
	const receiptWord = $derived.by(() => {
		if (receipt === null) return ''
		if (receipt.state !== 'read') return 'delivered'
		const stamp = receiptStamp(receipt.readAt, timestamp ?? null)
		return stamp ? `read ${stamp}` : 'read'
	})

	/** the standing word: under the newest own message, when receipts read as text. */
	const receiptLabel = $derived(receiptsAsText && isLatestOwn ? receiptWord : '')

	/** the word stops short of the bubble's corner, leaving the tail its own. */
	const receiptTailClearance = $derived(
		showTail && tailStyle === 'imessage' ? '1.25rem' : '0.25rem'
	)

	/** the status glyph owns the slot just outside the bubble, so share it out. */
	const hasStatusGlyph = $derived((sending || notDelivered || showsReceiptGlyph) && !isEditing)

	const hasTextBubble = $derived(content.trim().length > 0 || isEditing)

	/** never on hover alone: the same set floats beside the lifted bubble (F95). */
	const cornerActionsVisible = $derived(
		canHover && !isEditing && surface !== 'focus' && (isPointerOver || surface === 'menu')
	)
	/** the ellipsis only earns its place when it holds something the corner does not. */
	const hasOverflowActions = $derived(canEdit || Boolean(onDelete))
	const showBranchNav = $derived(siblingCount > 1 && !isEditing)

	/* the corner cluster's own footprint, so the time can sit just past it
	   instead of underneath it: an `IconButton size="sm"` and the cluster's
	   `gap-1`, offset by the same margins the cluster gives itself. */
	const CORNER_BUTTON_PX = 32
	const CORNER_GAP_PX = 4
	const CLUSTER_INSET_PX = 8
	const CLUSTER_INSET_WITH_GLYPH_PX = 36
	const cornerActionCount = $derived(1 + (onReply ? 1 : 0) + (hasOverflowActions ? 1 : 0))
	const hoverTimeInset = $derived(
		`${
			(hasStatusGlyph ? CLUSTER_INSET_WITH_GLYPH_PX : CLUSTER_INSET_PX) +
			cornerActionCount * CORNER_BUTTON_PX +
			(cornerActionCount - 1) * CORNER_GAP_PX +
			CLUSTER_INSET_PX
		}px`
	)

	/**
	 * the time is REVEALED, never reserved (F120): a bubble no longer keeps an
	 * empty row above it, so a precise cursor gets it in the outer gutter beside
	 * the floating actions, and a hold gets it over the lifted bubble.
	 *
	 * hover shows the clock alone - the transcript's own headers already say
	 * which day you are looking at - while the lift, which you asked for, spells
	 * the day out too. a named sender already trails the time on its own line, so
	 * that bubble is not told twice.
	 */
	const showsHoverTime = $derived(
		canHover && timestamp !== undefined && !isEditing && !showsSenderLine
	)
	const hoverTime = $derived(timestamp ? clockTime(timestamp) : '')
	const focusTime = $derived(timestamp ? formatTimeHeader(timestamp) : '')

	/** focus already floats reply and copy, so its menu carries only the rest. */
	const inFocusMenu = $derived(surface === 'focus')
	const menuItemCount = $derived(
		(inFocusMenu ? 0 : 1 + (onReply ? 1 : 0)) + (canEdit ? 1 : 0) + (onDelete ? 1 : 0)
	)

	/** the column of floating actions, for the room the ensemble has to claim. */
	const floatColumnHeight = $derived(
		cornerActionCount * CORNER_BUTTON_PX + (cornerActionCount - 1) * FLOAT_STACK_GAP_PX
	)

	/* the ensemble draws against the frozen rect MOVED to where it fits, so one
	   offset carries the ghost, the time, the floating actions and the menu. */
	const liftLeft = $derived(focusGeom ? focusGeom.left + focusGeom.fit.x : 0)
	const liftTop = $derived(focusGeom ? focusGeom.top + focusGeom.fit.y : 0)

	/**
	 * the actions stay reachable even when the bubble is taller than the screen:
	 * the column is centred on the lifted bubble until that would put it off the
	 * end, and then it holds the nearest edge instead.
	 */
	const floatColumnCentre = $derived(
		focusGeom
			? clampSpan(
					liftTop + focusGeom.height / 2 - floatColumnHeight / 2,
					floatColumnHeight,
					focusGeom.safe.top,
					focusGeom.safe.bottom
				) +
					floatColumnHeight / 2
			: 0
	)

	/**
	 * the time is ONE line whatever the bubble's width (F137): a narrow bubble
	 * used to wrap it and the second line landed on the bubble itself. it may now
	 * be wider than what it names - centred on the lift, clamped into the
	 * viewport - and it is placed by its own measured box, so no width can grow
	 * it down into the bubble.
	 */
	const stampWidth = $derived(stampBox.width)
	const stampHeight = $derived(stampBox.height || FOCUS_TIME_LINE_PX)
	const focusTimeLeft = $derived(
		focusGeom
			? clampSpan(
					liftLeft + focusGeom.width / 2 - stampWidth / 2,
					stampWidth,
					focusGeom.safe.left,
					focusGeom.safe.right
				)
			: 0
	)
	const focusTimeTop = $derived.by(() => {
		if (!focusGeom) return 0
		const bubbleTop = liftTop - (focusGeom.height * (liftScale - 1)) / 2
		// a stamp wider than its bubble can reach into the action column beside
		// it, and then it clears that too rather than sitting on a button
		const reachesColumn =
			align === 'right'
				? focusTimeLeft < liftLeft - FLOAT_GAP_PX
				: focusTimeLeft + stampWidth > liftLeft + focusGeom.width + FLOAT_GAP_PX
		const anchor = reachesColumn
			? Math.min(bubbleTop, floatColumnCentre - floatColumnHeight / 2)
			: bubbleTop
		return anchor - FOCUS_TIME_GAP_PX - stampHeight
	})

	/** the time is one line, so its box is what the layer measures on mount. */
	function measureStamp(): Attachment<HTMLElement> {
		return (node) => {
			const rect = node.getBoundingClientRect()
			stampBox = { width: rect.width, height: rect.height }
		}
	}

	/** the fuller menu hangs below the lifted bubble, off its own outer edge - or
	 *  at the bottom of the room there is, when the bubble outgrows the screen. */
	const focusMenuAnchor = $derived(
		focusGeom
			? {
					x:
						focusGeom.left < focusGeom.viewportWidth / 2
							? liftLeft
							: liftLeft + focusGeom.width,
					y: Math.min(
						liftTop + (focusGeom.height * (1 + liftScale)) / 2 + MENU_GAP_PX,
						focusGeom.safe.bottom
					),
				}
			: null
	)

	/**
	 * the tapped detail line (F137): imessage answers a plain tap with when the
	 * message was sent and, on your own, where it got to. one line at a time in
	 * the transcript, so the identity is a key rather than a boolean.
	 */
	const detailKey = Symbol('message detail')
	const detailLabel = $derived([focusTime, receiptWord].filter(Boolean).join(' · '))
	const detailOpen = $derived(openDetailKey === detailKey && detailLabel !== '' && !isEditing)

	/**
	 * what reaches here is a TAP: the hold and the swipe each swallow the click
	 * they would otherwise release into. a press that selected text or landed on
	 * a link is not one either, so those hand the gesture back.
	 *
	 * it is a listener rather than an `onclick` because the bubble is prose, not
	 * a control: announcing it as one would be a lie, and the same information is
	 * on the hover gutter and in the lift for anyone not tapping.
	 */
	function tapDetail(): Attachment<HTMLElement> {
		return (node) => {
			const onClick = (event: MouseEvent): void => {
				if (isEditing) return
				if (event.target instanceof Element && event.target.closest('a')) return
				const selection = window.getSelection()
				if (selection && !selection.isCollapsed && node.contains(selection.anchorNode)) {
					return
				}
				openDetailKey = openDetailKey === detailKey ? null : detailKey
			}
			node.addEventListener('click', onClick)
			return () => node.removeEventListener('click', onClick)
		}
	}

	/** one derived class instead of eight directives: the ghost reuses it too. */
	const tailClass = $derived.by(() => {
		if (isEditing || !showTail) return ''
		if (tailStyle === 'imessage') return align === 'right' ? 'imessage-right' : 'imessage-left'
		if (tailStyle === 'whatsapp') return align === 'right' ? 'whatsapp-right' : 'whatsapp-left'
		return ''
	})
</script>

{#snippet replyIcon()}
	<ArrowUturnLeft strokeWidth="2" />
{/snippet}

{#snippet copyIcon()}
	{#if copied}
		<Check strokeWidth="2.5" />
	{:else}
		<Clipboard strokeWidth="2" />
	{/if}
{/snippet}

{#snippet ellipsisIcon()}
	<EllipsisHorizontal strokeWidth="2" />
{/snippet}

<!-- one action, one bubble: its own glass surface and shadow, springing in a
     beat after the one before it. never a docked row of icons.
     every transition here is |global: each button sits in its own `{#if}`, and a
     local transition stays silent when it is an ANCESTOR block that mounted. -->
{#snippet glassAction(
	order: number,
	label: string,
	tip: string,
	onclick: () => void,
	icon: Snippet,
	expanded?: boolean
)}
	<span
		class="action-bubble liquid-glass rounded-pill flex"
		transition:scale|global={{
			duration: liftMs,
			delay: order * staggerMs,
			start: 0.4,
			opacity: 0,
			easing: backOut,
		}}
	>
		<IconButton
			size="sm"
			aria-label={label}
			title={tip}
			aria-haspopup={expanded === undefined ? undefined : 'menu'}
			aria-expanded={expanded}
			{onclick}
		>
			{@render icon()}
		</IconButton>
	</span>
{/snippet}

{#snippet cornerActions()}
	<!-- floating actions, anchored to the OUTER edge of the message and centred on
	     it: never over the text, and the same place whatever the height. it steps
	     aside when a status glyph holds that slot, which is a per-message constant,
	     so nothing shifts under the cursor. -->
	<div
		data-corner-actions
		data-visible={cornerActionsVisible}
		class="absolute top-1/2 z-20 flex -translate-y-1/2 items-center gap-1"
		class:right-full={align === 'right'}
		class:left-full={align === 'left'}
		style:margin-right={align === 'right' ? (hasStatusGlyph ? '2.25rem' : '0.5rem') : undefined}
		style:margin-left={align === 'left' ? (hasStatusGlyph ? '2.25rem' : '0.5rem') : undefined}
	>
		{#if cornerActionsVisible}
			{#if onReply}
				{@render glassAction(0, 'reply to message', 'reply', () => onReply?.(), replyIcon)}
			{/if}
			{@render glassAction(
				onReply ? 1 : 0,
				copied ? 'copied' : 'copy message',
				'copy',
				() => void copyMessage(),
				copyIcon
			)}
			{#if hasOverflowActions}
				<span
					bind:this={menuTriggerRef}
					class="action-bubble liquid-glass rounded-pill flex"
					transition:scale|global={{
						duration: liftMs,
						delay: (onReply ? 2 : 1) * staggerMs,
						start: 0.4,
						opacity: 0,
						easing: backOut,
					}}
				>
					<IconButton
						size="sm"
						aria-label="more actions"
						aria-haspopup="menu"
						aria-expanded={surface === 'menu'}
						onclick={() => (surface === 'menu' ? closeSurface() : (surface = 'menu'))}
					>
						<EllipsisHorizontal strokeWidth="2" />
					</IconButton>
				</span>
			{/if}
		{/if}
	</div>
{/snippet}

{#snippet focusSurface()}
	<!-- portalled to the body like every other overlay here (BaseModal, PopupMenu):
	     the transcript scrolls inside its own container, so raising a bubble above
	     a page-level backdrop is not something z-index can be trusted with.
	     `data-popup-menu` is PopupMenu's own marker for chrome that belongs to the
	     open menu, so a press in here is not read as a press outside it. -->
	<div
		{@attach portal()}
		data-message-focus
		data-motion={reduceMotion ? 'reduced' : 'spring'}
		data-popup-menu
		class="fixed inset-0 z-9990"
		role="presentation"
		onpointerdown={(event) => {
			pressStartedInLift = liftLayer !== null && event.composedPath().includes(liftLayer)
		}}
	>
		<!-- everything behind the bubble dims and blurs; tapping it settles back -->
		<button
			type="button"
			data-message-focus-backdrop
			class="absolute inset-0 bg-black/20 backdrop-blur-md dark:bg-black/45"
			transition:fade|global={{ duration: backdropMs, easing: cubicOut }}
			aria-label="dismiss message actions"
			onclick={() => {
				// a selection drag that began on the bubble and ended out here is
				// still the reader working with the text
				if (pressStartedInLift) return
				closeSurface()
			}}
		></button>
		{#if focusGeom}
			<!-- the strip directly above the bubble is where iMessage keeps its
			     tapbacks. this product has none, so the time takes it: without a
			     reserved row and without hover, the lift is where touch asks a
			     message when it was sent (F120c). -->
			{#if focusTime}
				<div
					data-focus-time
					{@attach measureStamp()}
					class="text-foreground/70 fixed text-xs whitespace-nowrap"
					style:left="{focusTimeLeft}px"
					style:top="{focusTimeTop}px"
					transition:fade|global={{ duration: backdropMs, easing: cubicOut }}
				>
					{focusTime}
				</div>
			{/if}
			<!-- the lifted copy stays live so the platform's own press-and-hold can
			     select its text and offer the native copy; our copy bubble stays too.
			     that second hold is the only one that selects: the hold that lifted
			     the bubble is still down when this mounts, so it arms on a delay. -->
			<div
				bind:this={liftLayer}
				data-select={selectionArmed ? 'armed' : 'idle'}
				class="lift-layer fixed origin-center"
				style:left="{liftLeft}px"
				style:top="{liftTop}px"
				style:width="{focusGeom.width}px"
				transition:lift|global
			>
				<div {@attach liftGhost()}></div>
			</div>
			<!-- the frequent actions float in the same gutter the corner cluster
			     uses, so the two surfaces speak about position the same way. -->
			<div
				class="fixed flex flex-col items-center gap-2"
				style:top="{floatColumnCentre}px"
				style:transform="translateY(-50%)"
				style:left={align === 'left'
					? `${liftLeft + focusGeom.width + FLOAT_GAP_PX}px`
					: undefined}
				style:right={align === 'right'
					? `${focusGeom.viewportWidth - liftLeft + FLOAT_GAP_PX}px`
					: undefined}
			>
				{#if onReply}
					{@render glassAction(
						0,
						'reply to message',
						'reply',
						() => {
							closeSurface()
							onReply?.()
						},
						replyIcon
					)}
				{/if}
				{@render glassAction(
					onReply ? 1 : 0,
					copied ? 'copied' : 'copy message',
					'copy',
					() => {
						closeSurface()
						void copyMessage()
					},
					copyIcon
				)}
				{#if hasOverflowActions}
					{@render glassAction(
						onReply ? 2 : 1,
						'more actions',
						'more',
						() => (focusMenuOpen = !focusMenuOpen),
						ellipsisIcon,
						focusMenuOpen
					)}
				{/if}
			</div>
		{/if}
	</div>
{/snippet}

{#snippet actionMenu()}
	<PopupMenu
		open={surface === 'menu' || (inFocusMenu && focusMenuOpen)}
		anchorEl={inFocusMenu ? null : menuTriggerRef}
		anchorPoint={inFocusMenu ? focusMenuAnchor : null}
		onClose={dismissMenu}
		estimatedHeight={44 * menuItemCount + 16}
	>
		{#if !inFocusMenu}
			{#if onReply}
				<MenuItem
					icon={ArrowUturnLeft}
					onclick={() => {
						closeSurface()
						onReply?.()
					}}
				>
					reply
				</MenuItem>
			{/if}
			<MenuItem
				icon={Clipboard}
				onclick={() => {
					closeSurface()
					void copyMessage()
				}}
			>
				copy
			</MenuItem>
		{/if}
		{#if canEdit}
			<MenuItem
				icon={Pencil}
				onclick={() => {
					closeSurface()
					startEditing()
				}}
			>
				edit
			</MenuItem>
		{/if}
		{#if onDelete}
			{#if canEdit || !inFocusMenu}
				<MenuSeparator />
			{/if}
			<MenuItem
				icon={GarbageBin}
				destructive
				onclick={() => {
					closeSurface()
					onDelete?.()
				}}
			>
				delete
			</MenuItem>
		{/if}
	</PopupMenu>
{/snippet}

<div
	bind:this={messageRef}
	{@attach entrance}
	{@attach swipe({
		onTrigger: () => onReply?.(),
		enabled: Boolean(onReply) && !isEditing,
		onProgress: (p) => (swipeProgress = p),
	})}
	{@attach contextmenu({ onOpen: openFocus, disabled: isEditing })}
	style:visibility={liftActive && !hasTextBubble ? 'hidden' : undefined}
	class="relative flex flex-col gap-2"
	class:ml-auto={align === 'right' && !isEditing}
	class:items-end={align === 'right' && !isEditing}
	class:items-start={align === 'left' && !isEditing}
	class:items-stretch={isEditing}
	class:w-full={isEditing}
	style:max-width={!isEditing ? '80%' : undefined}
	onmouseenter={() => (isPointerOver = true)}
	onmouseleave={() => (isPointerOver = false)}
	role="article"
>
	{#if showsSenderLine}
		<!-- the sender line: name, with the time trailing it on hover. inset so
		     it starts over the bubble's straight edge, clear of the corner. -->
		<div class="-mb-1 flex items-baseline gap-2" style:padding-left={senderInset}>
			<span class="text-foreground/75 text-[0.8125rem]">{senderName}</span>
			{#if timestamp}
				<span
					class="text-foreground/50 text-xs transition-opacity duration-200"
					class:opacity-0={!isHovered}
				>
					<Timestamp {timestamp} className="text-xs text-foreground/50" />
				</span>
			{/if}
		</div>
	{/if}

	{#if showsHoverTime}
		<!-- the time in the outer gutter, past the floating actions: no row is
		     reserved above the bubble any more, so it appears with the cluster and
		     leaves with it. PROVISIONAL placement (F120c). -->
		<span
			data-hover-time
			class="text-foreground/45 pointer-events-none absolute top-1/2 z-10 -translate-y-1/2 text-xs whitespace-nowrap transition-opacity duration-200"
			class:right-full={align === 'right'}
			class:left-full={align === 'left'}
			class:opacity-0={!cornerActionsVisible}
			style:margin-right={align === 'right' ? hoverTimeInset : undefined}
			style:margin-left={align === 'left' ? hoverTimeInset : undefined}
		>
			{hoverTime}
		</span>
	{/if}

	<!-- media attachments rendered OUTSIDE the bubble -->
	{#if hasMedia && !isEditing}
		<div class="relative max-w-sm">
			<div class="space-y-1.5 overflow-hidden rounded-2xl">
				<MediaAttachments {mediaParts} {fileParts} />
			</div>
			<!-- a caption-less message has no bubble to hang the actions off -->
			{#if canHover && !hasTextBubble && refs.length === 0}
				{@render cornerActions()}
			{/if}
		</div>
	{/if}

	<!-- attachment resource refs (user-attached files/resources) -->
	{#if refs.length > 0 && !isEditing}
		<div class="relative max-w-sm space-y-1.5">
			<AttachmentRefs {refs} />
			{#if canHover && !hasTextBubble}
				{@render cornerActions()}
			{/if}
		</div>
	{/if}

	<!-- quoted message, above the bubble it answers - over the BUBBLE, so in a
	     group thread it clears the avatar gutter the same way the branch nav does -->
	{#if replyTo && !isEditing}
		<div
			data-reply-quote
			class="max-w-sm"
			style:padding-left={hasAvatarGutter ? AVATAR_GUTTER : undefined}
		>
			<ReplyPreview message={replyTo} authorName={replyToAuthor} jumpable />
		</div>
	{/if}

	<!-- text bubble (only shown when there is text content or editing) -->
	{#if hasTextBubble}
		<div class="relative flex items-end gap-2" class:w-full={isEditing}>
			{#if hasAvatarGutter}
				<!-- reserved even when empty so a same-author run stays aligned -->
				<div data-sender-avatar class="{AVATAR_SIZE} shrink-0" style:transform={avatarDrop}>
					{#if showSenderAvatar}
						{#if senderAvatarUrl}
							<img
								src={senderAvatarUrl}
								alt={senderName ?? 'participant'}
								class="{AVATAR_SIZE} rounded-full object-cover"
							/>
						{:else}
							<!-- opaque, like the agent's generated avatar: a translucent
							     disc lets the wallpaper through and stops reading as a face -->
							<div
								class="text-foreground/90 {AVATAR_SIZE} flex items-center justify-center rounded-full text-xs font-semibold"
								style="background-color: var(--accent-primary);"
							>
								{senderInitials}
							</div>
						{/if}
					{/if}
				</div>
			{/if}
			<!-- one slot, one state at a time, sat at the bubble's outer bottom corner
			     the way both iMessage and whatsapp read status: clock while the send is
			     in flight, then a tick once it is written, both ticks once it is read.
			     a failed send ends the sequence there. -->
			{#if notDelivered && !isEditing}
				<!-- the same slot the clock uses: the wait is over, it just ended badly -->
				<div
					class="text-destructive/80 pointer-events-none absolute bottom-2 flex size-4 items-center justify-center"
					class:-left-6={align === 'right'}
					class:-right-6={align === 'left'}
					aria-label="not delivered"
				>
					<ExclamationTriangle class="h-4 w-4" strokeWidth="2" />
				</div>
			{:else if sending && !isEditing}
				<div
					class="text-foreground/55 pointer-events-none absolute bottom-2 flex size-4 items-center justify-center"
					class:-left-6={align === 'right'}
					class:-right-6={align === 'left'}
					aria-label="sending"
				>
					<span class="sending-clock-tick flex size-4 items-center justify-center">
						<Clock class="h-4 w-4" strokeWidth="2" />
					</span>
				</div>
			{:else if showsReceiptGlyph}
				<div
					data-read-receipt={receiptGlyph}
					class="pointer-events-none absolute bottom-2 flex size-4 items-center justify-center {receiptGlyph ===
					'read'
						? 'text-(--accent-primary)'
						: 'text-foreground/55'}"
					class:-left-6={align === 'right'}
					class:-right-6={align === 'left'}
					aria-label={receiptGlyph === 'read' ? 'read' : 'sent'}
				>
					{#if receiptGlyph === 'read'}
						<CheckDouble class="h-4 w-4" strokeWidth="2" />
					{:else}
						<Check class="h-4 w-4" strokeWidth="2" />
					{/if}
				</div>
			{/if}
			<div
				bind:this={bubbleRef}
				class="bubble-wrapper {tailClass}"
				class:w-full={isEditing}
				style:visibility={liftActive && !isEditing ? 'hidden' : undefined}
			>
				{#if canHover && !isEditing}
					{@render cornerActions()}
				{/if}
				{#if onReply && swipeProgress > 0}
					<!-- trails the bubble as it slides, filling in as the action arms.
					     it is anchored to the bubble, so in a group thread it has to
					     clear the avatar column as well as the usual gutter or it
					     lands squarely on the sender's face (F128). -->
					<div
						data-swipe-hint
						data-past-avatar={hasAvatarGutter}
						class="text-foreground/60 pointer-events-none absolute top-1/2 flex size-7 items-center justify-center rounded-full"
						class:-left-9={!hasAvatarGutter}
						class:-left-19={hasAvatarGutter}
						style:opacity={swipeProgress}
						style:transform="translateY(-50%) scale({0.6 + swipeProgress * 0.4})"
						aria-hidden="true"
					>
						<ArrowUturnLeft class="h-4 w-4" strokeWidth="2.5" />
					</div>
				{/if}
				<div
					{@attach tapDetail()}
					class="bubble-content relative rounded-3xl px-3 py-2 backdrop-blur-[20px] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] [backdrop-saturate:180%]"
					class:liquid-glass={!isIncoming}
					class:incoming={isIncoming}
					class:px-5={isEditing}
					class:py-3={isEditing}
					class:w-full={isEditing}
					style:view-transition-name={viewTransitionName}
					style={isIncoming
						? undefined
						: 'background-color: var(--accent-primary); box-shadow: 0 4px 16px var(--accent-border);'}
				>
					{#if isEditing}
						<div class="max-h-96 overflow-auto">
							<textarea
								bind:this={editTextarea}
								bind:value={editContent}
								class="text-foreground placeholder:text-foreground/40 w-full resize-none bg-transparent leading-relaxed wrap-break-word outline-none disabled:opacity-60"
								placeholder="edit your message"
								disabled={isSaving}
								rows={1}
								oninput={(e) => {
									const t = e.currentTarget
									t.style.height = ''
									t.style.height = `${t.scrollHeight}px`
								}}
								onkeydown={(e) => {
									if (e.key === 'Escape') cancelEditing()
									if (
										(e.metaKey || e.ctrlKey) &&
										e.key === 'Enter' &&
										onEditSaveAsCopy
									)
										saveAsCopy()
									if ((e.metaKey || e.ctrlKey) && e.key === 's') {
										e.preventDefault()
										if (onEditSave) saveEdit()
									}
								}}
							></textarea>
						</div>
						<!-- button row: save (left), cancel + send (right) -->
						<div class="mt-2 mb-1 flex justify-between text-sm font-medium">
							<div>
								{#if onEditSave}
									<button
										onclick={saveEdit}
										disabled={isSaving || !editContent.trim()}
										class="border-foreground/20 bg-foreground/10 text-foreground/90 hover:bg-foreground/20 inline-flex cursor-pointer items-center gap-1.5 rounded-3xl border px-3.5 py-1.5 transition disabled:cursor-not-allowed disabled:opacity-40"
									>
										<FloppyDisk class="h-4 w-4" strokeWidth="2" />
										<span>save</span>
									</button>
								{/if}
							</div>
							<div class="flex space-x-1.5">
								<button
									onclick={cancelEditing}
									disabled={isSaving}
									class="text-foreground/70 hover:bg-foreground/10 hover:text-foreground inline-flex cursor-pointer items-center gap-1.5 rounded-3xl px-3.5 py-1.5 transition disabled:cursor-not-allowed disabled:opacity-50"
								>
									<XMark class="h-4 w-4" />
									<span>cancel</span>
								</button>
								{#if onEditSaveAsCopy}
									<button
										onclick={saveAsCopy}
										disabled={isSaving || !editContent.trim()}
										class="bg-foreground text-background hover:bg-foreground/90 inline-flex cursor-pointer items-center gap-1.5 rounded-3xl px-3.5 py-1.5 font-semibold transition disabled:cursor-not-allowed disabled:opacity-40"
									>
										<ArrowUpCircle class="h-4 w-4" strokeWidth="2" />
										{#if isSaving}
											<ShimmerText className="inline-block"
												>saving</ShimmerText
											>
										{:else}
											<span>send</span>
										{/if}
									</button>
								{/if}
							</div>
						</div>
					{:else}
						<div
							class="text-foreground leading-relaxed wrap-break-word whitespace-pre-wrap select-text"
						>
							{content}
						</div>
					{/if}
				</div>
			</div>
		</div>
	{/if}

	<!-- the tapped line: when it was sent, and where it got to. it is asked for,
	     so it reserves nothing until it is - and it stands in for the receipt
	     word while it is open rather than repeating it underneath. -->
	{#if detailOpen}
		<div
			data-message-detail
			class="text-foreground/45 -mt-1 text-[0.6875rem] leading-none"
			style:padding-right={align === 'right' ? receiptTailClearance : undefined}
			style:padding-left={align === 'left' ? receiptTailClearance : undefined}
			transition:fly|global={{ y: -4, duration: detailMs, opacity: 0, easing: cubicOut }}
		>
			{detailLabel}
		</div>
	{/if}

	<!-- imessage's receipt: one quiet word under the newest message that has one,
	     sat clear of the tail rather than over it. -->
	{#if receiptLabel && !detailOpen}
		<div
			data-read-receipt-text={receiptGlyph}
			class="text-foreground/45 -mt-1 text-[0.6875rem] leading-none"
			style:padding-right={align === 'right' ? receiptTailClearance : undefined}
			style:padding-left={align === 'left' ? receiptTailClearance : undefined}
		>
			{receiptLabel}
		</div>
	{/if}

	<!-- branch nav is state, not an action: it says which alternative you are on,
	     so it stays put rather than hiding behind a gesture. -->
	{#if showBranchNav}
		<div
			class="text-foreground/50 flex items-center text-xs font-medium"
			style:padding-left={hasAvatarGutter ? AVATAR_GUTTER : '0.25rem'}
			style:padding-right={align === 'right' ? '0.25rem' : undefined}
			role="none"
		>
			<button
				onclick={onPrevious}
				disabled={currentSiblingIndex === 0}
				class="text-foreground/50 hover:text-foreground flex h-6 w-6 cursor-pointer items-center justify-center transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
				title="previous version"
			>
				<ChevronLeft class="size-4" strokeWidth="2" />
			</button>
			<span class="mx-0.5 font-mono tabular-nums">
				{currentSiblingIndex + 1}/{siblingCount}
			</span>
			<button
				onclick={onNext}
				disabled={currentSiblingIndex === siblingCount - 1}
				class="text-foreground/50 hover:text-foreground flex h-6 w-6 cursor-pointer items-center justify-center transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
				title="next version"
			>
				<ChevronRight class="size-4" strokeWidth="2" />
			</button>
		</div>
	{/if}
</div>

{#if surface === 'focus'}
	{@render focusSurface()}
{/if}

{@render actionMenu()}

<style>
	.bubble-wrapper {
		position: relative;
		max-width: 100%;
	}

	/*
	 * the lifted copy is live text, not a picture of the bubble: a hold inside it
	 * has to reach the platform's own selection, handles and copy item, so it
	 * keeps its pointer events and opts back into the ios callout - but only once
	 * armed. the lifting hold is still down when the layer mounts, so until then
	 * nothing in here is selectable, and the bubble's own `select-text` sits
	 * INSIDE the clone: the lock has to reach past it, not sit on the layer alone.
	 */
	.lift-layer:not([data-select='armed']),
	.lift-layer:not([data-select='armed']) :global(*) {
		-webkit-user-select: none;
		user-select: none;
		-webkit-touch-callout: none;
	}

	.lift-layer[data-select='armed'] {
		-webkit-user-select: text;
		user-select: text;
		-webkit-touch-callout: default;
	}

	@keyframes sendingClockTick {
		to {
			transform: rotate(360deg);
		}
	}

	.sending-clock-tick {
		animation: sendingClockTick 1.4s steps(12) infinite;
		transform-origin: center;
	}

	/*
	 * an incoming bubble is tinted glass, not a panel: no border of its own, the
	 * backdrop blur does the separating. the tint is a thin veil - heavy blur
	 * carries the shape, so the wallpaper keeps its own colour instead of being
	 * greyed out by a thick neutral wash.
	 */
	.bubble-content.incoming {
		--bubble-tint: var(--color-foreground);
		background-color: color-mix(in oklab, var(--bubble-tint) 10%, transparent);
		backdrop-filter: blur(40px) saturate(180%);
	}

	/* ════════════════════════════════════════════════════════════
       iMESSAGE TAIL - a horn hanging off the bottom corner
       the classic recipe paints its cutout in the page background,
       which can never work over live wallpapers. here one bubble-
       coloured ::before is masked to the tail alone and unions with
       the bubble, so only the bubble's own paint touches the screen.
       geometry contour-traced from a hi-res ios 26 shot (both sent
       bubbles, averaged, each normalised on its own corner radius:
       47.1 reference px against our 21, so 1px here = 2.24 there).
       the mask's inner edge is an arc 0.4px inside the bubble's own
       24px corner, so the two shapes tile rather than stack - a
       translucent incoming bubble would otherwise double its tint -
       and that hair of overlap keeps antialiasing from opening a seam.
       ════════════════════════════════════════════════════════════ */

	.imessage-right .bubble-content,
	.imessage-left .bubble-content {
		position: relative;
		/* real imessage keeps ONE corner radius at every height; the utility's
		   24px only matched the tail's 21px registration on one-line bubbles
		   (where the browser clamps it) - pin it so the tail joins at any height */
		border-radius: 21px;
	}

	.imessage-right .bubble-content::before,
	.imessage-left .bubble-content::before {
		content: '';
		position: absolute;
		/* a global sheen layer also styles this pseudo with inset 0; left/top
		   must be released or they win over right/bottom + width */
		inset: auto;
		bottom: -10px;
		width: 34px;
		height: 36px;
		background-color: var(--accent-primary);
		/* the sheen layer also sets a gradient image and a full border-radius
		   on this pseudo; both must be neutralised or they deform the tail */
		background-image: none;
		border-radius: 0;
		/* the box's (30,13) is the bubble's true bottom corner. the outline
		   surfaces from the corner arc ~2px above the bottom edge, turns
		   vertical at a waist 12.5px inboard, then bends OUTWARD as it falls
		   to a tip 11.3px inboard and 8px below: the tail leans toward the
		   speaker's own side. the under edge returns to the bottom edge 27.5px
		   inboard and arrives TANGENT to it - that tangency is the whole
		   trick, since an edge that meets the bubble at an angle reads as a
		   cone. it carries the taper too: a 15px shoulder narrowing to a point
		   the trace alone drew ~0.8px too thick. the closing curve is the
		   inset corner arc, hidden inside */
		mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 34 36'%3E%3Cpath d='M9.2 25.98L10.16 26.15L11.1 26.31L11.28 26.38L11.45 26.46L11.85 26.66L12.25 26.87L12.53 27.01L12.81 27.15L13.52 27.58L14.22 28.01L14.87 28.48L15.51 28.95L15.69 29.06L15.88 29.18L16.63 29.64L17.37 30.1L17.54 30.18L17.7 30.27L17.93 30.4L18.16 30.53L18.39 30.66L18.61 30.8L19.31 31.16L20.01 31.52L20.75 31.87L21.49 32.23L21.61 32.3L21.73 32.36L22.71 32.8L23.68 33.23L24.09 33.42L24.51 33.61L25.06 33.6L25.06 33.6L25.61 33.6L25.85 33.32L26.08 33.03L26.1 32.82L26.12 32.62L26 32.32L25.89 32.03L25.44 31.49L24.99 30.95L24.69 30.56L24.38 30.18L24.08 29.72L23.78 29.26L23.56 28.88L23.33 28.5L23.05 27.69L22.75 26.87L22.63 26.36L22.48 25.86L22.63 25.21L22.77 24.56L22.95 24.21L23.12 23.87L23.36 23.48L23.59 23.1L23.94 22.67L22.48 20.3A18 18 0 0 1 13 23L9.2 23Z'/%3E%3C/svg%3E");
		mask-size: 34px 36px;
		mask-position: 0 0;
		mask-repeat: no-repeat;
		/* behind the bubble's own paint: overlap can never double-draw */
		z-index: -1;
		/* the sheen layer's mask shorthand also carries content-box and an
		   exclude composite; against its 1px padding that shifts the tail off
		   the corner by a pixel and clips its edge, so both are re-stated */
		mask-origin: border-box;
		mask-clip: border-box;
		mask-composite: add;
		backdrop-filter: none;
	}

	/* outgoing: opaque accent, flush with the bubble's own right edge */
	.imessage-right .bubble-content::before {
		right: 0;
	}

	/* incoming mirrors via transform so one geometry serves both sides */
	.imessage-left .bubble-content::before {
		left: 0;
		transform: scaleX(-1);
	}

	.imessage-left .bubble-content.incoming::before {
		background-color: color-mix(in oklab, var(--bubble-tint) 10%, transparent);
		backdrop-filter: blur(40px) saturate(180%);
		/* translucent glass: a deep overlap would double the tint, so the glass
		   variant closes shallow instead */
		mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 34 36'%3E%3Cpath d='M9.2 25.98L10.16 26.15L11.1 26.31L11.28 26.38L11.45 26.46L11.85 26.66L12.25 26.87L12.53 27.01L12.81 27.15L13.52 27.58L14.22 28.01L14.87 28.48L15.51 28.95L15.69 29.06L15.88 29.18L16.63 29.64L17.37 30.1L17.54 30.18L17.7 30.27L17.93 30.4L18.16 30.53L18.39 30.66L18.61 30.8L19.31 31.16L20.01 31.52L20.75 31.87L21.49 32.23L21.61 32.3L21.73 32.36L22.71 32.8L23.68 33.23L24.09 33.42L24.51 33.61L25.06 33.6L25.06 33.6L25.61 33.6L25.85 33.32L26.08 33.03L26.1 32.82L26.12 32.62L26 32.32L25.89 32.03L25.44 31.49L24.99 30.95L24.69 30.56L24.38 30.18L24.08 29.72L23.78 29.26L23.56 28.88L23.33 28.5L23.05 27.69L22.75 26.87L22.63 26.36L22.48 25.86L22.63 25.21L22.77 24.56L22.95 24.21L23.12 23.87L23.36 23.48L23.59 23.1L23.94 22.67L23.74 22.34A20.4 20.4 0 0 1 13 25.4L9.2 25.4Z'/%3E%3C/svg%3E");
	}

	/*
	 * glass cannot blur through a nested pseudo: a backdrop-filter on the bubble
	 * makes it a backdrop root, so the tail's own filter is left with nothing to
	 * sample and paints a bare tint over the unblurred wallpaper - a differently
	 * coloured object hanging off the bubble. the body's glass moves to an
	 * ::after that is the tail's SIBLING instead: both then filter the same
	 * backdrop and land on the same colour. (::after is free here - the sheen and
	 * ring layers ride .liquid-glass, which incoming bubbles never carry.)
	 */
	.imessage-left .bubble-content.incoming {
		background-color: transparent;
		backdrop-filter: none;
		/* without its filter the bubble is no longer a stacking context, and both
		   pseudos sit at -1: restore one or they escape the bubble entirely */
		z-index: 0;
	}

	.imessage-left .bubble-content.incoming::after {
		content: '';
		position: absolute;
		inset: 0;
		border-radius: inherit;
		background-color: color-mix(in oklab, var(--bubble-tint) 10%, transparent);
		backdrop-filter: blur(40px) saturate(180%);
		/* below the text, above the tail - the shallow closing keeps that hair of
		   overlap from reading as doubled tint */
		z-index: -1;
	}

	/* ════════════════════════════════════════════════════════════
       WHATSAPP TAIL - Single rotated pseudo-element with border trick
       ════════════════════════════════════════════════════════════ */

	/* WhatsApp uses sharper corners than iMessage */
	.whatsapp-right .bubble-content {
		border-radius: 8px !important;
		border-bottom-right-radius: 2px !important;
	}

	.whatsapp-left .bubble-content {
		border-radius: 8px !important;
		border-bottom-left-radius: 2px !important;
	}

	/* RIGHT TAIL (sent messages) */
	.whatsapp-right .bubble-content::after {
		content: '';
		position: absolute;
		bottom: 0;
		right: -8px;
		width: 0;
		height: 0;
		border: 0 solid transparent;
		border-top: 13px solid var(--accent-primary);
		border-radius: 0 20px 0;
		transform: rotate(145deg);
	}

	/* LEFT TAIL (received messages) */
	.whatsapp-left .bubble-content::after {
		content: '';
		position: absolute;
		bottom: 0;
		left: -8px;
		width: 0;
		height: 0;
		border: 0 solid transparent;
		border-top: 13px solid var(--accent-primary);
		border-radius: 0 20px 0;
		transform: rotate(45deg) scaleY(-1);
	}

	/* the tail is part of the bubble, so it takes the bubble's own colour */
	.whatsapp-left .bubble-content.incoming::after {
		border-top-color: color-mix(in oklab, var(--bubble-tint) 10%, transparent);
	}
</style>
