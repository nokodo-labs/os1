import { autoPlacement, autoUpdate, computePosition, hide, offset, shift } from '@floating-ui/dom'
import { setContext } from 'svelte'

export class Popover {
	isOpen = $state(false)
	// Internal reference to the DOM element
	_referenceNode = null

	constructor() {
		setContext('POPOVER', true)
	}

	// Action to capture the reference element
	reference = (node) => {
		this._referenceNode = node
		return {
			destroy: () => {
				this._referenceNode = null
			},
		}
	}

	place = async (node) => {
		if (!this._referenceNode || !node) return

		const middleware = [
			hide(),
			offset(10),
			shift({
				mainAxis: true,
			}),
			autoPlacement({
				allowedPlacements: [
					'top',
					'top-end',
					'top-start',
					'bottom',
					'bottom-end',
					'bottom-start',
				],
			}),
		]

		const { x, y, strategy } = await computePosition(this._referenceNode, node, {
			strategy: 'fixed',
			middleware,
		})

		Object.assign(node.style, {
			position: strategy,
			left: `${x}px`,
			top: `${y}px`,
		})
	}

	popoverAttachment = (node) => {
		// Portal logic: Move to body to avoid clipping
		document.body.appendChild(node)

		void this.place(node)

		// Use _referenceNode instead of relying on the undefined 'reference' state
		if (this._referenceNode) {
			const off = autoUpdate(this._referenceNode, node, () => this.place(node))
			return {
				destroy: () => {
					off()
					if (node.parentNode) {
						node.parentNode.removeChild(node)
					}
				},
			}
		}

		return {
			destroy: () => {
				if (node.parentNode) {
					node.parentNode.removeChild(node)
				}
			},
		}
	}
}
