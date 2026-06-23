export const REMINDER_TITLE_MAX_LENGTH = 200
export const REMINDER_LIST_NAME_MAX_LENGTH = 100
export const REMINDER_LIST_DESCRIPTION_MAX_LENGTH = 500
export const REMINDER_LIST_ICON_MAX_LENGTH = 50
export const REMINDER_LIST_COLOR_MAX_LENGTH = 7

export function maxLengthError(label: string, value: string, maxLength: number): string | null {
	return value.length > maxLength ? `${label} must be ${maxLength} characters or less` : null
}

export function requiredNameError(value: string): string | null {
	return value.trim() ? null : 'name is required'
}
