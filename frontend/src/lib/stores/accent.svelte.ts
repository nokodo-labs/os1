/**
 * accent color store
 *
 * a simple reactive store for setting the current accent color.
 * pages/components are responsible for importing and setting the accent as needed.
 */

// accent color names (matching the accentColors map in themeContext)
export type AccentColorKey =
	| 'purple'
	| 'blue'
	| 'green'
	| 'orange'
	| 'pink'
	| 'red'
	| 'yellow'
	| 'gray'
	| 'notes'
	| 'reminders'
	| 'calendar'
	| 'lilac'
	| 'petrol'

// reactive state for current accent
let currentAccent = $state<AccentColorKey>('lilac')

/**
 * accent store object for reactive access
 */
export const accentStore = {
	get current() {
		return currentAccent
	},
	set(color: AccentColorKey) {
		currentAccent = color
	},
}
