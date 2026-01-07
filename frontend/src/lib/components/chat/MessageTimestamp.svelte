<script lang="ts">
	type TimestampLike = Date | { getTime: () => number }

	interface Props {
		timestamp: TimestampLike
		className?: string
	}

	let { timestamp, className = '' }: Props = $props()

	function toDate(value: TimestampLike): Date {
		return value instanceof Date ? value : new Date(value.getTime())
	}

	function startOfDay(d: Date): Date {
		return new Date(d.getFullYear(), d.getMonth(), d.getDate())
	}

	let date = $derived.by(() => toDate(timestamp))

	let label = $derived.by((): string => {
		if (Number.isNaN(date.getTime())) return ''

		const now = new Date()
		const dayDiff = Math.floor(
			(startOfDay(now).getTime() - startOfDay(date).getTime()) / 86_400_000
		)

		const time = date
			.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
			.toLowerCase()

		if (dayDiff === 0) return `today at ${time}`
		if (dayDiff === 1) return `yesterday at ${time}`
		if (dayDiff > 1 && dayDiff < 7) {
			const weekday = date.toLocaleDateString([], { weekday: 'long' }).toLowerCase()
			return `${weekday} at ${time}`
		}

		const fullDate = date.toLocaleDateString([], {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
		})
		return `${fullDate} at ${time}`
	})

	let iso = $derived.by(() => {
		if (Number.isNaN(date.getTime())) return ''
		return date.toISOString()
	})

	let title = $derived.by((): string => {
		if (Number.isNaN(date.getTime())) return ''
		return date.toLocaleString()
	})
</script>

<time datetime={iso} class={className} {title}>{label}</time>
