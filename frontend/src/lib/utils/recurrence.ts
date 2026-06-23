import type { components } from '$lib/api/types'

export type Recurrence = components['schemas']['Recurrence']
export type RecurrenceFrequency = 'HOURLY' | 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'YEARLY'
export type WeekdayCode = 'MO' | 'TU' | 'WE' | 'TH' | 'FR' | 'SA' | 'SU'
export type RecurrenceEndMode = 'never' | 'on' | 'after'
export type QuickRecurrencePresetId =
	| 'hourly'
	| 'daily'
	| 'weekdays'
	| 'weekly-current-day'
	| 'monthly-current-day'
	| 'yearly-current-date'
	| 'daily-current-time'

export type RecurrenceBuildOptions = {
	frequency: RecurrenceFrequency
	interval: number
	byDays: WeekdayCode[]
	byMonthDays: number[]
	byMonths: number[]
	byHours: number[]
	byMinutes: number[]
	endMode: RecurrenceEndMode
	untilDate: string
	count: number
	timezone: string | null | undefined
}

export type ParsedRRule = {
	frequency: RecurrenceFrequency
	interval: number
	byDays: WeekdayCode[]
	byMonthDays: number[]
	byMonths: number[]
	byHours: number[]
	byMinutes: number[]
	endMode: RecurrenceEndMode
	untilDate: string
	count: number
	unknownParts: string[]
}

export type NotificationOffsetUnit = 'minutes' | 'hours' | 'days' | 'weeks' | 'months'

export const WEEKDAY_OPTIONS: Array<{ value: WeekdayCode; label: string; shortLabel: string }> = [
	{ value: 'MO', label: 'monday', shortLabel: 'mon' },
	{ value: 'TU', label: 'tuesday', shortLabel: 'tue' },
	{ value: 'WE', label: 'wednesday', shortLabel: 'wed' },
	{ value: 'TH', label: 'thursday', shortLabel: 'thu' },
	{ value: 'FR', label: 'friday', shortLabel: 'fri' },
	{ value: 'SA', label: 'saturday', shortLabel: 'sat' },
	{ value: 'SU', label: 'sunday', shortLabel: 'sun' },
]

export const MONTH_OPTIONS: Array<{ value: number; label: string; shortLabel: string }> = [
	{ value: 1, label: 'january', shortLabel: 'jan' },
	{ value: 2, label: 'february', shortLabel: 'feb' },
	{ value: 3, label: 'march', shortLabel: 'mar' },
	{ value: 4, label: 'april', shortLabel: 'apr' },
	{ value: 5, label: 'may', shortLabel: 'may' },
	{ value: 6, label: 'june', shortLabel: 'jun' },
	{ value: 7, label: 'july', shortLabel: 'jul' },
	{ value: 8, label: 'august', shortLabel: 'aug' },
	{ value: 9, label: 'september', shortLabel: 'sep' },
	{ value: 10, label: 'october', shortLabel: 'oct' },
	{ value: 11, label: 'november', shortLabel: 'nov' },
	{ value: 12, label: 'december', shortLabel: 'dec' },
]

export const FREQUENCY_OPTIONS: Array<{ value: RecurrenceFrequency; label: string; unit: string }> =
	[
		{ value: 'HOURLY', label: 'hours', unit: 'hour' },
		{ value: 'DAILY', label: 'days', unit: 'day' },
		{ value: 'WEEKLY', label: 'weeks', unit: 'week' },
		{ value: 'MONTHLY', label: 'months', unit: 'month' },
		{ value: 'YEARLY', label: 'years', unit: 'year' },
	]

export const NOTIFICATION_OFFSET_PRESETS: Array<{ label: string; value: number }> = [
	{ label: 'start', value: 0 },
	{ label: '5 min', value: 5 },
	{ label: '10 min', value: 10 },
	{ label: '30 min', value: 30 },
	{ label: '1 hour', value: 60 },
	{ label: '2 hours', value: 120 },
	{ label: '1 day', value: 1440 },
	{ label: '1 week', value: 10080 },
]

const WEEKDAY_BY_JS_DAY: WeekdayCode[] = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA']
const VALID_WEEKDAYS = new Set<WeekdayCode>(WEEKDAY_OPTIONS.map((option) => option.value))
const MAX_NOTIFICATION_OFFSET_MINUTES = 525600
const MAX_NOTIFICATION_OFFSETS = 8

export function resolveAnchorDate(anchorDate: string | Date | null | undefined): Date {
	const fallback = new Date()
	if (anchorDate instanceof Date) {
		const date = new Date(anchorDate)
		return Number.isNaN(date.getTime()) ? fallback : date
	}
	if (!anchorDate) return fallback
	const date = new Date(anchorDate)
	return Number.isNaN(date.getTime()) ? fallback : date
}

export function getQuickRecurrencePresets(anchorDate: string | Date | null | undefined): Array<{
	id: QuickRecurrencePresetId
	label: string
	rrule: string
}> {
	const anchor = resolveAnchorDate(anchorDate)
	const weekday = WEEKDAY_BY_JS_DAY[anchor.getDay()]
	const weekdayLabel = weekdayName(weekday)
	const month = anchor.getMonth() + 1
	const monthDay = anchor.getDate()
	const hour = anchor.getHours()
	const minute = anchor.getMinutes()
	const monthLabel = monthDayLabel(month, monthDay)
	const timeLabel = formatTimeLabel(hour, minute)

	return [
		{ id: 'hourly', label: 'hourly', rrule: 'FREQ=HOURLY' },
		{ id: 'daily', label: 'daily', rrule: 'FREQ=DAILY' },
		{
			id: 'weekdays',
			label: 'every weekday',
			rrule: 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR',
		},
		{
			id: 'weekly-current-day',
			label: `weekly on ${weekdayLabel}`,
			rrule: `FREQ=WEEKLY;BYDAY=${weekday}`,
		},
		{
			id: 'monthly-current-day',
			label: `monthly on day ${monthDay}`,
			rrule: `FREQ=MONTHLY;BYMONTHDAY=${monthDay}`,
		},
		{
			id: 'yearly-current-date',
			label: `annually on ${monthLabel}`,
			rrule: `FREQ=YEARLY;BYMONTH=${month};BYMONTHDAY=${monthDay}`,
		},
		{
			id: 'daily-current-time',
			label: `every day at ${timeLabel}`,
			rrule: `FREQ=DAILY;BYHOUR=${hour};BYMINUTE=${minute}`,
		},
	]
}

export function recurrenceFromRule(
	rrule: string,
	timezone: string | null | undefined
): Recurrence | null {
	const rule = rrule.trim()
	if (!rule) return null
	return {
		rrule: [rule],
		rdate: [],
		exdate: [],
		timezone: normalizeTimezone(timezone),
	}
}

export function buildRecurrence(options: RecurrenceBuildOptions): Recurrence | null {
	const parts = [`FREQ=${options.frequency}`]
	const interval = clampInteger(options.interval, 1, 999)
	if (interval > 1) parts.push(`INTERVAL=${interval}`)

	const byDays = uniqueWeekdays(options.byDays)
	if (byDays.length > 0) parts.push(`BYDAY=${byDays.join(',')}`)

	const byMonthDays = normalizeNumberList(options.byMonthDays, 1, 31)
	if (byMonthDays.length > 0) parts.push(`BYMONTHDAY=${byMonthDays.join(',')}`)

	const byMonths = normalizeNumberList(options.byMonths, 1, 12)
	if (byMonths.length > 0) parts.push(`BYMONTH=${byMonths.join(',')}`)

	const byHours = normalizeNumberList(options.byHours, 0, 23)
	if (byHours.length > 0) parts.push(`BYHOUR=${byHours.join(',')}`)

	const byMinutes = normalizeNumberList(options.byMinutes, 0, 59)
	if (byMinutes.length > 0) parts.push(`BYMINUTE=${byMinutes.join(',')}`)

	if (options.endMode === 'after') {
		parts.push(`COUNT=${clampInteger(options.count, 1, 9999)}`)
	} else if (options.endMode === 'on') {
		const until = dateInputToRRuleUntil(options.untilDate)
		if (until) parts.push(`UNTIL=${until}`)
	}

	return recurrenceFromRule(parts.join(';'), options.timezone)
}

export function parseNumberList(value: string, min: number, max: number): number[] {
	const items = value
		.split(/[\s,]+/)
		.map((item) => item.trim())
		.filter(Boolean)
		.map((item) => Number(item))
	return normalizeNumberList(items, min, max)
}

export function formatNumberList(values: number[]): string {
	return values.join(', ')
}

export function parseRRule(ruleText: string | null | undefined): ParsedRRule {
	const parsed: ParsedRRule = {
		frequency: 'DAILY',
		interval: 1,
		byDays: [],
		byMonthDays: [],
		byMonths: [],
		byHours: [],
		byMinutes: [],
		endMode: 'never',
		untilDate: '',
		count: 10,
		unknownParts: [],
	}
	const body = stripRRulePrefix(ruleText ?? '')
	if (!body) return parsed

	for (const part of body.split(';')) {
		const [rawName, rawValue] = part.split('=', 2)
		const name = rawName?.trim().toUpperCase()
		const value = rawValue?.trim()
		if (!name || !value) {
			if (part.trim()) parsed.unknownParts.push(part.trim())
			continue
		}

		if (name === 'FREQ' && isRecurrenceFrequency(value)) {
			parsed.frequency = value
		} else if (name === 'INTERVAL') {
			parsed.interval = clampInteger(Number(value), 1, 999)
		} else if (name === 'BYDAY') {
			parsed.byDays = parseWeekdayList(value)
		} else if (name === 'BYMONTHDAY') {
			parsed.byMonthDays = parseNumberList(value, 1, 31)
		} else if (name === 'BYMONTH') {
			parsed.byMonths = parseNumberList(value, 1, 12)
		} else if (name === 'BYHOUR') {
			parsed.byHours = parseNumberList(value, 0, 23)
		} else if (name === 'BYMINUTE') {
			parsed.byMinutes = parseNumberList(value, 0, 59)
		} else if (name === 'COUNT') {
			parsed.endMode = 'after'
			parsed.count = clampInteger(Number(value), 1, 9999)
		} else if (name === 'UNTIL') {
			parsed.endMode = 'on'
			parsed.untilDate = rruleUntilToDateInput(value)
		} else {
			parsed.unknownParts.push(`${name}=${value}`)
		}
	}

	return parsed
}

export function describeRecurrence(
	recurrence: Recurrence | null | undefined,
	anchorDate?: string | Date | null
): string {
	const rule = recurrence?.rrule?.[0]?.trim()
	if (!rule) return 'does not repeat'
	const parsed = parseRRule(rule)
	const intervalPrefix = parsed.interval === 1 ? '' : `${parsed.interval} `
	const pluralUnit = frequencyPlural(parsed.frequency)
	const singularUnit = frequencySingular(parsed.frequency)
	let label =
		parsed.interval === 1
			? defaultFrequencyLabel(parsed.frequency)
			: `every ${intervalPrefix}${pluralUnit}`

	if (parsed.frequency === 'DAILY' && parsed.byHours.length === 1) {
		label = `${parsed.interval === 1 ? 'every day' : `every ${intervalPrefix}days`} at ${formatTimeLabel(
			parsed.byHours[0],
			parsed.byMinutes[0] ?? 0
		)}`
	} else if (parsed.frequency === 'WEEKLY' && isWeekdaySet(parsed.byDays)) {
		label = 'every weekday'
	} else if (parsed.frequency === 'WEEKLY' && parsed.byDays.length > 0) {
		label = `${parsed.interval === 1 ? 'weekly' : `every ${intervalPrefix}${pluralUnit}`} on ${formatWeekdayList(
			parsed.byDays
		)}`
	} else if (parsed.frequency === 'MONTHLY' && parsed.byMonthDays.length > 0) {
		label = `${parsed.interval === 1 ? 'monthly' : `every ${intervalPrefix}${pluralUnit}`} on day ${formatSimpleList(
			parsed.byMonthDays.map(String)
		)}`
	} else if (
		parsed.frequency === 'YEARLY' &&
		parsed.byMonths.length === 1 &&
		parsed.byMonthDays.length === 1
	) {
		label = `${parsed.interval === 1 ? 'annually' : `every ${intervalPrefix}${pluralUnit}`} on ${monthDayLabel(
			parsed.byMonths[0],
			parsed.byMonthDays[0]
		)}`
	} else if (parsed.frequency === 'YEARLY' && parsed.byMonths.length > 0) {
		label = `${parsed.interval === 1 ? 'annually' : `every ${intervalPrefix}${pluralUnit}`} in ${formatMonthList(
			parsed.byMonths
		)}`
	}

	if (parsed.unknownParts.length > 0) label = `custom ${singularUnit} repeat`
	if (parsed.endMode === 'after') label = `${label}, ${parsed.count} times`
	if (parsed.endMode === 'on' && parsed.untilDate)
		label = `${label}, until ${formatDateInput(parsed.untilDate)}`
	if (
		!rule.includes('BY') &&
		parsed.interval === 1 &&
		anchorDate &&
		parsed.frequency === 'WEEKLY'
	) {
		const anchor = resolveAnchorDate(anchorDate)
		label = `weekly from ${weekdayName(WEEKDAY_BY_JS_DAY[anchor.getDay()])}`
	}
	return label
}

export function normalizeNotificationOffsets(offsets: number[]): number[] {
	return normalizeNumberList(offsets, 0, MAX_NOTIFICATION_OFFSET_MINUTES).slice(
		0,
		MAX_NOTIFICATION_OFFSETS
	)
}

export function offsetToMinutes(amount: number, unit: NotificationOffsetUnit): number {
	const normalized = clampInteger(amount, 1, 9999)
	if (unit === 'hours') return normalized * 60
	if (unit === 'days') return normalized * 1440
	if (unit === 'weeks') return normalized * 10080
	if (unit === 'months') return normalized * 43200
	return normalized
}

export function describeNotificationOffset(offset: number): string {
	if (offset === 0) return 'at start'
	if (offset % 43200 === 0) return pluralize(offset / 43200, 'month')
	if (offset % 10080 === 0) return pluralize(offset / 10080, 'week')
	if (offset % 1440 === 0) return pluralize(offset / 1440, 'day')
	if (offset % 60 === 0) return pluralize(offset / 60, 'hour')
	return pluralize(offset, 'minute')
}

export function describeNotificationOffsets(offsets: number[]): string {
	const normalized = normalizeNotificationOffsets(offsets)
	if (normalized.length === 0) return 'no notifications'
	return normalized.map(describeNotificationOffset).join(', ')
}

function stripRRulePrefix(ruleText: string): string {
	const trimmed = ruleText.trim()
	return trimmed.toUpperCase().startsWith('RRULE:') ? trimmed.slice(6) : trimmed
}

function normalizeTimezone(timezone: string | null | undefined): string | null {
	const trimmed = timezone?.trim()
	return trimmed || null
}

function isRecurrenceFrequency(value: string): value is RecurrenceFrequency {
	return (
		value === 'HOURLY' ||
		value === 'DAILY' ||
		value === 'WEEKLY' ||
		value === 'MONTHLY' ||
		value === 'YEARLY'
	)
}

function parseWeekdayList(value: string): WeekdayCode[] {
	return value
		.split(',')
		.map((item) => item.trim().slice(-2).toUpperCase())
		.filter((item): item is WeekdayCode => VALID_WEEKDAYS.has(item as WeekdayCode))
		.filter((item, index, items) => items.indexOf(item) === index)
}

function uniqueWeekdays(values: WeekdayCode[]): WeekdayCode[] {
	return WEEKDAY_OPTIONS.map((option) => option.value).filter((value) => values.includes(value))
}

function normalizeNumberList(values: number[], min: number, max: number): number[] {
	return [
		...new Set(
			values.map((value) => Math.trunc(value)).filter((value) => value >= min && value <= max)
		),
	].sort((a, b) => a - b)
}

function clampInteger(value: number, min: number, max: number): number {
	if (!Number.isFinite(value)) return min
	return Math.min(max, Math.max(min, Math.trunc(value)))
}

function dateInputToRRuleUntil(value: string): string | null {
	if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
	const date = new Date(`${value}T23:59:59`)
	if (Number.isNaN(date.getTime())) return null
	return date
		.toISOString()
		.replace(/[-:]/g, '')
		.replace(/\.\d{3}Z$/, 'Z')
}

function rruleUntilToDateInput(value: string): string {
	const normalized = value.trim()
	const dateOnly = normalized.match(/^(\d{4})(\d{2})(\d{2})$/)
	if (dateOnly) return `${dateOnly[1]}-${dateOnly[2]}-${dateOnly[3]}`
	const dateTime = normalized.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?$/)
	if (!dateTime) return ''
	const date = new Date(
		`${dateTime[1]}-${dateTime[2]}-${dateTime[3]}T${dateTime[4]}:${dateTime[5]}:${dateTime[6]}Z`
	)
	if (Number.isNaN(date.getTime())) return ''
	return date.toISOString().slice(0, 10)
}

function frequencySingular(frequency: RecurrenceFrequency): string {
	if (frequency === 'HOURLY') return 'hourly'
	if (frequency === 'DAILY') return 'daily'
	if (frequency === 'WEEKLY') return 'weekly'
	if (frequency === 'MONTHLY') return 'monthly'
	return 'annual'
}

function frequencyPlural(frequency: RecurrenceFrequency): string {
	return FREQUENCY_OPTIONS.find((option) => option.value === frequency)?.label ?? 'days'
}

function defaultFrequencyLabel(frequency: RecurrenceFrequency): string {
	if (frequency === 'HOURLY') return 'hourly'
	if (frequency === 'DAILY') return 'daily'
	if (frequency === 'WEEKLY') return 'weekly'
	if (frequency === 'MONTHLY') return 'monthly'
	return 'annually'
}

function weekdayName(code: WeekdayCode): string {
	return WEEKDAY_OPTIONS.find((option) => option.value === code)?.label ?? 'day'
}

function monthDayLabel(month: number, day: number): string {
	const monthName = MONTH_OPTIONS.find((option) => option.value === month)?.shortLabel ?? 'month'
	return `${monthName} ${day}`
}

function formatTimeLabel(hour: number, minute: number): string {
	const date = new Date()
	date.setHours(hour, minute, 0, 0)
	return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
		.format(date)
		.toLowerCase()
}

function isWeekdaySet(values: WeekdayCode[]): boolean {
	return (
		values.length === 5 &&
		values.every((value) => ['MO', 'TU', 'WE', 'TH', 'FR'].includes(value))
	)
}

function formatWeekdayList(values: WeekdayCode[]): string {
	return formatSimpleList(
		values.map(
			(value) => WEEKDAY_OPTIONS.find((option) => option.value === value)?.label ?? value
		)
	)
}

function formatMonthList(values: number[]): string {
	return formatSimpleList(
		values.map(
			(value) =>
				MONTH_OPTIONS.find((option) => option.value === value)?.label ?? String(value)
		)
	)
}

function formatSimpleList(values: string[]): string {
	if (values.length <= 1) return values[0] ?? ''
	if (values.length === 2) return `${values[0]} and ${values[1]}`
	return `${values.slice(0, -1).join(', ')}, and ${values[values.length - 1]}`
}

function formatDateInput(value: string): string {
	const date = new Date(`${value}T00:00`)
	if (Number.isNaN(date.getTime())) return value
	return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
		.format(date)
		.toLowerCase()
}

function pluralize(value: number, unit: string): string {
	return `${value} ${unit}${value === 1 ? '' : 's'}`
}
