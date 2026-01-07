type Unsubscribe = () => void

interface ReadinessBlocker {
	done: () => void
}

export interface AppReadiness {
	readonly shellReady: boolean
	readonly blockerCount: number
	readonly ready: boolean
	markShellReady: () => void
	subscribe: (listener: () => void) => Unsubscribe
	waitForReady: () => Promise<void>
	createBlocker: () => ReadinessBlocker
}

let shellReady = $state(false)
let blockerCount = $state(0)
let listenerHead: { callback: () => void; next: typeof listenerHead } | null = null

function notify() {
	let node = listenerHead
	while (node) {
		node.callback()
		node = node.next
	}
}

function decrementBlocker() {
	blockerCount = Math.max(0, blockerCount - 1)
	notify()
}

export const appReadiness: AppReadiness = {
	get shellReady() {
		return shellReady
	},
	get blockerCount() {
		return blockerCount
	},
	get ready() {
		return shellReady && blockerCount === 0
	},
	markShellReady() {
		shellReady = true
		notify()
	},
	subscribe(listener) {
		const node = { callback: listener, next: listenerHead }
		listenerHead = node
		return () => {
			if (listenerHead === node) {
				listenerHead = node.next
				return
			}
			let prev = listenerHead
			while (prev?.next) {
				if (prev.next === node) {
					prev.next = node.next
					return
				}
				prev = prev.next
			}
		}
	},
	waitForReady() {
		if (shellReady && blockerCount === 0) return Promise.resolve()
		return new Promise<void>((resolve) => {
			const unsubscribe = appReadiness.subscribe(() => {
				if (!appReadiness.ready) return
				unsubscribe()
				resolve()
			})
		})
	},
	createBlocker() {
		blockerCount += 1
		notify()
		let isDone = false
		return {
			done: () => {
				if (isDone) return
				isDone = true
				decrementBlocker()
			},
		}
	},
}
