<script lang="ts">
	import { setBackgroundContext } from '$lib/contexts/backgroundContext'

	interface Props {
		color?: string
		image?: string
		imagePosition?: string
		imageSize?: string
	}

	let {
		color = '#000000',
		image,
		imagePosition = 'center',
		imageSize = 'cover',
	}: Props = $props()

	let subscribers: Array<() => void> = []

	// Provide a dummy context for compatibility
	setBackgroundContext({
		getCanvas: () => null,
		getCanvasDimensions: () => ({ width: 0, height: 0 }),
		subscribe: (callback) => {
			subscribers.push(callback)
			return () => {
				subscribers = subscribers.filter((cb) => cb !== callback)
			}
		},
	})

	const backgroundStyle = $derived(() => {
		if (image) {
			return `background-color: ${color}; background-image: url(${image}); background-position: ${imagePosition}; background-size: ${imageSize};`
		}
		return `background-color: ${color};`
	})
</script>

<div class="absolute inset-0 overflow-hidden" style={backgroundStyle()}></div>
