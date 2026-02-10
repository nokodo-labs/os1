import { onDestroy, untrack } from 'svelte'
import { SvelteSet } from 'svelte/reactivity'

/**
 * @typedef {Object} PanzoomOptions
 * @property {number} [initialX=0]
 * @property {number} [initialY=0]
 * @property {number} [initialScale=1]
 * @property {number} [minZoom=0.1]
 * @property {number} [maxZoom=Infinity]
 * @property {number} [zoomSpeed=1]
 * @property {number} [doubleClickScale=1.75]
 * @property {string|null} [modifierKey=null] Key required to hold for zooming (e.g. 'Control', 'Alt', 'Shift', 'Meta')
 * @property {boolean} [activateMouseWheel=true]
 */

/**
 * @param {PanzoomOptions} opts
 */
export const usePanzoom = (opts = {}) => {
	// state
	let x = opts.initialX ?? 0
	let y = opts.initialY ?? 0
	let scale = opts.initialScale ?? 1
	// options
	const minZoom = opts.minZoom ?? 0.1
	const maxZoom = opts.maxZoom ?? Number.POSITIVE_INFINITY
	const zoomSpeed = opts.zoomSpeed ?? 1
	const doubleClickScale = opts.doubleClickScale ?? 1.75
	const modifierKey = opts.modifierKey ?? null

	/** @type {HTMLElement | SVGSVGElement | null} */
	let node = null // element we transform
	/** @type {HTMLElement | SVGSVGElement | null} */
	let eventTarget = null // element we listen on (parent container if available)
	/** @type {HTMLElement | null} */
	let createdWrapper = null // wrapper we created if no parent existed
	const listeners = new SvelteSet()

	// restore context for expansion
	/** @type {HTMLElement | null} */
	let restoreParent = null
	/** @type {ChildNode | null} */
	let restoreNextSibling = null

	// drag state
	let dragging = false
	let lastClientX = 0
	let lastClientY = 0
	/** @type {(() => void) | null} */
	let dragOffMove = null
	/** @type {(() => void) | null} */
	let dragOffUp = null

	// touch state
	let touchMode = 'none'
	let pinchDistance = 0

	// expand/collapse state
	let isExpanded = $state(false)
	let animating = false

	const destroy = () => {
		listeners.forEach((off) => {
			if (typeof off === 'function') off()
		})
		listeners.clear()

		// Ensure restored if destroyed while expanded
		if (isExpanded && eventTarget && restoreParent) {
			if (restoreNextSibling) {
				restoreParent.insertBefore(eventTarget, restoreNextSibling)
			} else {
				restoreParent.appendChild(eventTarget)
			}
		}

		if (createdWrapper) {
			// Move node back out of wrapper before removing wrapper
			if (node && createdWrapper.parentElement) {
				createdWrapper.parentElement.insertBefore(node, createdWrapper)
			}
			createdWrapper.remove()
			createdWrapper = null
		}
	}
	onDestroy(() => {
		destroy()
	})
	function normalize() {
		// clamp and round to reduce subpixel jitter
		scale = clampScale(scale)
		/** @param {number} v */
		const r = (v) => Math.round(v * 1000) / 1000
		x = r(x)
		y = r(y)
		scale = r(scale)
	}
	function apply() {
		if (!node) return
		normalize()
		// Use CSS transform regardless of DOM/SVG root; modern browsers support this.
		const el = node
		el.style.transformOrigin = '0 0'
		el.style.willChange = 'transform'
		// transform order is right-to-left. We want screen = translate + scale * local
		// so use translate() first, then scale().
		el.style.transform = `translate3d(${x}px, ${y}px, 0) scale(${scale})`
	}
	/** @param {number} s */
	function clampScale(s) {
		if (s < minZoom) return minZoom
		if (s > maxZoom) return maxZoom
		return s
	}
	/**
	 * @param {number} clientX
	 * @param {number} clientY
	 * @param {number} factor
	 */
	function zoomAt(clientX, clientY, factor) {
		if (!node) return
		if (!Number.isFinite(factor) || factor === 1) return
		const nextScale = clampScale(scale * factor)
		const ratio = nextScale / scale
		if (ratio === 1) return
		const owner = eventTarget ?? node.parentElement ?? node
		const ownerRect = owner.getBoundingClientRect()
		const ox = clientX - ownerRect.left
		const oy = clientY - ownerRect.top
		// Keep (ox, oy) stationary in owner's coordinate space
		x = ratio * x + (1 - ratio) * ox
		y = ratio * y + (1 - ratio) * oy
		scale = nextScale
		apply()
	}
	/** @param {number} deltaY */
	function kineticWheel(deltaY) {
		// deltaY > 0 => zoom out; use smooth exponential scaling
		const sign = Math.sign(deltaY)
		const step = Math.min(0.25, Math.abs((zoomSpeed * deltaY) / 128))
		return 1 - sign * step
	}
	/** @param {WheelEvent} e */
	function onWheel(e) {
		if (!opts.activateMouseWheel) return

		// CUSTOMIZATION: Modifier Key Check
		if (modifierKey && !e.getModifierState(modifierKey)) {
			// When modifier is required but not pressed, ignore the event
			return
		}

		if (!node) return
		if (animating) {
			e.preventDefault()
			e.stopPropagation()
			return
		}
		// Always prevent default to stop page scroll
		e.preventDefault()
		e.stopPropagation()
		const factor = kineticWheel(e.deltaY * (e.deltaMode ? 100 : 1))
		zoomAt(e.clientX, e.clientY, factor)
		// re-apply using latest rect
		apply()
	}
	/** @param {MouseEvent} e */
	function onDblClick(e) {
		if (!node) return
		// Ignore dblclicks that originate outside of the pan/zoom content (the node)
		const t = e.target
		if (t instanceof Node && !(t === node || node.contains(t))) {
			return // likely UI control inside container; don't zoom
		}
		// Ignore dblclicks on interactive elements or those explicitly marked to ignore
		/** @param {HTMLElement} el */
		const isInteractive = (el) => {
			const tag = el.tagName.toLowerCase()
			return (
				el.closest('[data-panzoom-ignore]') !== null ||
				[
					'button',
					'a',
					'input',
					'textarea',
					'select',
					'label',
					'summary',
					'details',
				].includes(tag) ||
				el.isContentEditable
			)
		}
		if (t instanceof HTMLElement && isInteractive(t)) return
		e.preventDefault()
		// Anchor double-click zoom at parent center to avoid shifts on rapid clicks
		const baseEl = eventTarget ?? node?.parentElement ?? node
		if (!baseEl) return
		const base = baseEl.getBoundingClientRect()
		const cx = base.left + base.width / 2
		const cy = base.top + base.height / 2
		zoomAt(cx, cy, doubleClickScale)
	}
	/** @param {MouseEvent} e */
	function startDrag(e) {
		if (animating) {
			e.preventDefault()
			return
		}
		if (e.button !== 0) return // left only
		dragging = true
		lastClientX = e.clientX
		lastClientY = e.clientY
		e.preventDefault()
		if (node) node.style.cursor = 'grabbing'

		// Use window listeners for dragging outside
		const offMove = () => window.removeEventListener('mousemove', onDragMove)
		const offUp = () => window.removeEventListener('mouseup', endDrag)

		window.addEventListener('mousemove', onDragMove, { passive: false })
		window.addEventListener('mouseup', endDrag, { passive: true })

		listeners.add(offMove)
		listeners.add(offUp)
		dragOffMove = offMove
		dragOffUp = offUp
	}
	/** @param {MouseEvent} e */
	function onDragMove(e) {
		if (!dragging) return
		const dx = e.clientX - lastClientX
		const dy = e.clientY - lastClientY
		lastClientX = e.clientX
		lastClientY = e.clientY
		x += dx
		y += dy
		apply()
	}
	function endDrag() {
		dragging = false
		if (node) node.style.cursor = 'grab'
		if (dragOffMove) {
			dragOffMove()
			listeners.delete(dragOffMove)
		}
		if (dragOffUp) {
			dragOffUp()
			listeners.delete(dragOffUp)
		}
		dragOffMove = dragOffUp = null
	}

	/** @param {KeyboardEvent} e */
	function onKeyDown(e) {
		if (e.key === 'Escape' || e.keyCode === 27) {
			if (isExpanded && !animating) {
				// fire and forget
				void expand(false)
			}
		}
	}

	/** @param {TouchEvent} e */
	function onTouchStart(e) {
		// on mobile (touch devices), only allow pan/zoom when expanded (fullscreen).
		// this prevents mermaid charts from blocking chat scroll.
		if (!isExpanded && 'ontouchstart' in window) {
			return // let touch events bubble up for normal scrolling
		}

		const hasButton = e
			.composedPath()
			.some((el) => el instanceof HTMLElement && el.tagName.toLowerCase() === 'button')
		if (hasButton) return
		if (!node) return
		if (animating) {
			e.preventDefault()
			return
		}
		if (e.touches.length === 1) {
			touchMode = 'pan'
			lastClientX = e.touches[0].clientX
			lastClientY = e.touches[0].clientY
		} else if (e.touches.length >= 2) {
			touchMode = 'pinch'
			const [t1, t2] = [e.touches[0], e.touches[1]]
			pinchDistance = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY)
		}
		// prevent default scrolling/zooming
		e.preventDefault()
		const offMove = () => window.removeEventListener('touchmove', onTouchMove)
		const offEnd = () => window.removeEventListener('touchend', onTouchEnd)
		const offCancel = () => window.removeEventListener('touchcancel', onTouchEnd)
		window.addEventListener('touchmove', onTouchMove, { passive: false })
		window.addEventListener('touchend', onTouchEnd, { passive: true })
		window.addEventListener('touchcancel', onTouchEnd, { passive: true })
		listeners.add(offMove)
		listeners.add(offEnd)
		listeners.add(offCancel)
	}
	/** @param {TouchEvent} e */
	function onTouchMove(e) {
		if (!node) return
		if (touchMode === 'pan' && e.touches.length === 1) {
			const t = e.touches[0]
			const dx = t.clientX - lastClientX
			const dy = t.clientY - lastClientY
			lastClientX = t.clientX
			lastClientY = t.clientY
			x += dx
			y += dy
			apply()
			e.preventDefault()
		} else if (touchMode === 'pinch' && e.touches.length >= 2) {
			const [t1, t2] = [e.touches[0], e.touches[1]]
			const dist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY)
			const factor = dist / (pinchDistance || dist)
			const center = {
				x: (t1.clientX + t2.clientX) / 2,
				y: (t1.clientY + t2.clientY) / 2,
			}
			zoomAt(center.x, center.y, factor)
			pinchDistance = dist
			e.preventDefault()
		}
	}
	function onTouchEnd() {
		if (!node) return
		if (touchMode === 'pinch') {
			// reset pinch state, keep resulting transform
			touchMode = 'none'
			pinchDistance = 0
		} else if (touchMode === 'pan') {
			touchMode = 'none'
		}
	}

	/** @param {HTMLElement | SVGSVGElement} target */
	function internalAttach(target) {
		return untrack(() => {
			node = target
			// Ensure eventTarget and node are different elements to avoid FLIP conflicts
			const isSVG = typeof SVGSVGElement !== 'undefined' && target instanceof SVGSVGElement
			if (isSVG) {
				// For SVG, prefer parent element
				eventTarget = target.parentElement
			} else {
				// For non-SVG, try to use parent element when available
				const parent = target.parentElement
				if (parent && parent instanceof HTMLElement) {
					eventTarget = parent
				} else {
					// No suitable parent - create wrapper to ensure separation
					const wrapper = document.createElement('div')
					wrapper.style.cssText = `
						display: contents;
						contain: layout style;
					`
						.replace(/\s+/g, ' ')
						.trim()
					// Insert wrapper and move target into it
					if (target.parentElement) {
						target.parentElement.insertBefore(wrapper, target)
					}
					wrapper.appendChild(target)
					eventTarget = wrapper
					createdWrapper = wrapper
				}
			}
			// Final fallback if no eventTarget was established
			if (!eventTarget) {
				eventTarget = target
			}
			apply()
			// helper to add and track listeners with options
			/**
			 * @param {string} type
			 * @param {EventListenerOrEventListenerObject} handler
			 * @param {boolean | AddEventListenerOptions | undefined} options
			 */
			const add = (type, handler, options) => {
				const n = eventTarget ?? node
				if (!n) return () => {}
				n.addEventListener(type, handler, options)
				const off = () => n.removeEventListener(type, handler, options)
				listeners.add(off)
				return off
			}
			/**
			 * @param {string} type
			 * @param {EventListenerOrEventListenerObject} handler
			 * @param {boolean | AddEventListenerOptions | undefined} options
			 */
			const addWindow = (type, handler, options) => {
				window.addEventListener(type, handler, options)
				const off = () => window.removeEventListener(type, handler, options)
				listeners.add(off)
				return off
			}
			// core events with passive: false where needed
			add('mousedown', (/** @type {Event} */ e) => startDrag(/** @type {MouseEvent} */ (e)), {
				passive: false,
			})
			add('wheel', (/** @type {Event} */ e) => onWheel(/** @type {WheelEvent} */ (e)), {
				passive: false,
				capture: true,
			})
			add('dblclick', (/** @type {Event} */ e) => onDblClick(/** @type {MouseEvent} */ (e)), {
				passive: false,
			})
			add(
				'touchstart',
				(/** @type {Event} */ e) => onTouchStart(/** @type {TouchEvent} */ (e)),
				{ passive: false }
			)
			addWindow(
				'keydown',
				(/** @type {Event} */ e) => onKeyDown(/** @type {KeyboardEvent} */ (e)),
				{
					passive: true,
				}
			)
			// prevent text selection/scrolling while interacting
			const t = eventTarget ?? node
			if (!t) return () => destroy()
			t.style.userSelect = 'none'
			// on touch devices, allow normal scrolling when not expanded.
			// only block touch-action when expanded (fullscreen) or on desktop.
			const isTouchDevice = 'ontouchstart' in window
			t.style.touchAction = isTouchDevice ? 'pan-y' : 'none'
			t.style.cursor = 'grab'
			t.style.overscrollBehavior = isTouchDevice ? 'auto' : 'contain'
			// For SVG root, use fill-box so translation math stays in CSS px space
			const n = node
			if (typeof SVGSVGElement !== 'undefined' && target instanceof SVGSVGElement) {
				n.style.transformBox = 'fill-box'
			}
			return () => {
				destroy()
			}
		})
	}

	/** @param {boolean} expandStatus */
	const expand = (expandStatus) => {
		if (!eventTarget) return
		const target = eventTarget

		if (expandStatus) {
			// First: capture state
			const first = target.getBoundingClientRect()

			// Prepare placeholder in current parent
			if (target.parentElement) {
				// Save context
				restoreParent = target.parentElement
				restoreNextSibling = target.nextSibling

				// Lock parent height to prevent collapse
				const styleAttributes = ['margin-block', 'height']
				styleAttributes.forEach((attribute) => {
					if (restoreParent) {
						restoreParent.style.setProperty(
							attribute,
							getComputedStyle(target).getPropertyValue(attribute)
						)
					}
				})
			}

			// Move to body to escape Z-Index traps
			document.body.appendChild(target)

			target.dataset.expanded = 'true'
			isExpanded = true
			// enable touch interaction now that we're fullscreen
			target.style.touchAction = 'none'
			zoomToFit()

			// Last: capture new state (now fixed on body)
			const last = target.getBoundingClientRect()

			const deltaX = first.left - last.left
			const deltaY = first.top - last.top
			const deltaW = first.width / last.width
			const deltaH = first.height / last.height

			const animation = eventTarget.animate(
				[
					{
						transformOrigin: '0 0',
						transform: `translate(${deltaX}px, ${deltaY}px) scale(${deltaW}, ${deltaH})`,
					},
					{
						transformOrigin: '0 0',
						transform: 'translate(0px, 0px) scale(1, 1)',
					},
				],
				{
					duration: 350,
					easing: 'cubic-bezier(0.4, 0.0, 0.2, 1)',
					fill: 'both',
				}
			)
			animation.finished.then(() => {
				animation.cancel()
			})
		} else {
			// Collapse
			const first = eventTarget.getBoundingClientRect()

			// We want to calculate where it *will* be.
			// But we can't move it back yet, or the animation will happen inside the small box (clipping).

			// Strategy:
			// 1. Calculate target rect by measuring the placeholder?
			//    Currently restoreParent has fixed height matching the element.
			//    So we can calculate where the placeholder is.
			let targetRect
			if (restoreParent) {
				const rect = restoreParent.getBoundingClientRect()
				// The element takes up full space of parent usually in this context?
				// Or we can just trust that putting it back yields the correct position.
				// But we want to animate TO that position while still attached to body (to avoid clipping/overflow:hidden of parent during transition).
				targetRect = rect
			} else {
				targetRect = { left: 0, top: 0, width: 0, height: 0 }
			}

			eventTarget.dataset.expanded = 'false' // To remove fixed styles if needed for measurement, but we are animating manually?
			// actually dataset.expanded=false removes position:fixed from CSS.
			// If we remove it now, it jumps to body flow.
			// We want to keep it fixed during animation.

			// Wait, the CSS uses [data-expanded='true'] { position: fixed ... }
			// So if we set it to false, it loses fixed positioning.

			// Let's manually animate from current fixed rect to target rect.

			const deltaX = targetRect.left - first.left
			const deltaY = targetRect.top - first.top
			const deltaW = targetRect.width / first.width
			const deltaH = targetRect.height / first.height

			const animation = eventTarget.animate(
				[
					{
						transformOrigin: '0 0',
						transform: 'translate(0px, 0px) scale(1, 1)',
					},
					{
						transformOrigin: '0 0',
						transform: `translate(${deltaX}px, ${deltaY}px) scale(${deltaW}, ${deltaH})`,
					},
				],
				{
					duration: 350,
					easing: 'cubic-bezier(0.4, 0.0, 0.2, 1)',
					fill: 'both',
				}
			)

			animation.finished.then(() => {
				animation.cancel()
				if (!eventTarget) return // destroyed

				// Move back to original context
				eventTarget.dataset.expanded = 'false'
				isExpanded = false
				// restore touch-action for mobile scrolling
				const isTouchDevice = 'ontouchstart' in window
				eventTarget.style.touchAction = isTouchDevice ? 'auto' : 'none'

				if (restoreParent) {
					if (restoreNextSibling) {
						try {
							restoreParent.insertBefore(eventTarget, restoreNextSibling)
						} catch {
							// Fallback if sibling is gone
							restoreParent.appendChild(eventTarget)
						}
					} else {
						restoreParent.appendChild(eventTarget)
					}
					// Reset parent style
					restoreParent.style.height = 'fit-content'
					// restoreParent.style.marginBlock = ''; // If we want
				}

				zoomToFit()

				// Cleanup refs
				restoreParent = null
				restoreNextSibling = null
			})
		}
	}
	async function toggleExpand() {
		if (isExpanded) return expand(false)
		return expand(true)
	}
	function zoomToFit(padding = 0.05) {
		if (!node) return
		const parent = node.parentElement
		if (!parent) return
		const parentRect = parent.getBoundingClientRect()
		const rect = node.getBoundingClientRect()

		const naturalWidth = rect.width / scale || 0
		const naturalHeight = rect.height / scale || 0
		const targetWidth = parentRect.width * (1 - 2 * padding)
		const targetHeight = parentRect.height * (1 - 2 * padding)
		if (naturalWidth <= 0 || naturalHeight <= 0 || targetWidth <= 0 || targetHeight <= 0) return
		const s = clampScale(Math.min(targetWidth / naturalWidth, targetHeight / naturalHeight))
		scale = s
		x = 0
		y = 0
		apply()
		const newRect = node.getBoundingClientRect()
		const targetLeft = parentRect.left + (parentRect.width - newRect.width) / 2
		const targetTop = parentRect.top + (parentRect.height - newRect.height) / 2
		x = targetLeft - newRect.left
		y = targetTop - newRect.top
		apply()
	}
	/** @param {number} factor */
	function zoomBy(factor) {
		if (!node) return
		const owner = eventTarget ?? node.parentElement ?? node
		const ownerRect = owner.getBoundingClientRect()
		const cx = ownerRect.left + ownerRect.width / 2
		const cy = ownerRect.top + ownerRect.height / 2
		zoomAt(cx, cy, factor)
	}
	/**
	 * @param {number} dx
	 * @param {number} dy
	 */
	function moveBy(dx, dy) {
		x += dx
		y += dy
		apply()
	}
	function zoomIn(factor = 1.25) {
		zoomBy(factor)
	}
	function zoomOut(factor = 1.25) {
		if (factor <= 0) return
		zoomBy(1 / factor)
	}
	/**
	 * @param {number} nx
	 * @param {number} ny
	 * @param {number} ns
	 */
	function setTransform(nx, ny, ns) {
		scale = clampScale(ns)
		x = nx
		y = ny
		apply()
	}

	return {
		attach: internalAttach,
		zoomToFit,
		zoomBy,
		zoomIn,
		zoomOut,
		moveBy,
		setTransform,
		expand,
		toggleExpand,
		get transform() {
			return { x, y, scale }
		},
		get expanded() {
			return isExpanded
		},
	}
}
