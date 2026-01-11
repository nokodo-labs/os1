<script lang="ts">
	type TimestampLike = Date | { getTime: () => number }

	interface Props {
		timestamp: TimestampLike
		mode?: 'calendar' | 'relative'
		minUnit?: 'minute' | 'hour'
		className?: string
	}

	let { timestamp, mode = 'calendar', minUnit = 'minute', className = '' }: Props = $props()

	function toDate(value: TimestampLike): Date {
		return value instanceof Date ? value : new Date(value.getTime())
	}

	function startOfDay(d: Date): Date {
		return new Date(d.getFullYear(), d.getMonth(), d.getDate())
	}

	let date = $derived.by(() => toDate(timestamp))

	let label = $derived.by((): string => {
		if (Number.isNaN(date.getTime())) return ''

		if (mode === 'relative') {
			const nowMs = Date.now()
			const diffMs = nowMs - date.getTime()
			if (diffMs < 0) return ''

			const minutes = Math.floor(diffMs / 60_000)
			const hours = Math.floor(diffMs / 3_600_000)

			if (minUnit === 'hour') {
				if (hours < 1) return 'just now'
				if (hours < 24) return `${hours}h ago`
				return date.toLocaleDateString()
			}

			if (minutes < 1) return 'just now'
			if (minutes < 60) return `${minutes}m ago`
			if (hours < 24) return `${hours}h ago`
			return date.toLocaleDateString()
		}

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
