export type SignupField = 'displayName' | 'username' | 'email' | 'password' | 'passwordConfirm'
export type FieldErrors = Partial<Record<SignupField, string>>

function hasMessageText(value: unknown): value is string {
	return typeof value === 'string' && value.trim().length > 0
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return Boolean(value) && typeof value === 'object'
}

function signupFieldFromValue(value: unknown): SignupField | null {
	if (typeof value !== 'string') return null
	switch (value) {
		case 'display_name':
		case 'displayName':
			return 'displayName'
		case 'username':
		case 'email':
		case 'password':
			return value
		case 'password_confirm':
		case 'passwordConfirm':
			return 'passwordConfirm'
		default:
			return null
	}
}

function fieldFromLocation(location: unknown): SignupField | null {
	if (!Array.isArray(location)) return signupFieldFromValue(location)
	for (let i = location.length - 1; i >= 0; i -= 1) {
		const field = signupFieldFromValue(location[i])
		if (field) return field
	}
	return null
}

function setFieldError(errors: FieldErrors, field: SignupField, message: string): FieldErrors {
	switch (field) {
		case 'displayName':
			return { ...errors, displayName: message }
		case 'username':
			return { ...errors, username: message }
		case 'email':
			return { ...errors, email: message }
		case 'password':
			return { ...errors, password: message }
		case 'passwordConfirm':
			return { ...errors, passwordConfirm: message }
	}
}

function messageFromUnknown(value: unknown): string | null {
	if (hasMessageText(value)) return value.trim()
	if (!isRecord(value)) return null
	return (
		messageFromUnknown(value.msg) ??
		messageFromUnknown(value.message) ??
		messageFromUnknown(value.detail)
	)
}

function duplicateFieldFromMessage(message: string): SignupField | null {
	const normalized = message.toLowerCase()
	const isConflict =
		normalized.includes('taken') ||
		normalized.includes('registered') ||
		normalized.includes('exists') ||
		normalized.includes('duplicate')
	if (!isConflict) return null
	if (normalized.includes('username')) return 'username'
	if (normalized.includes('email')) return 'email'
	return null
}

export function parseSignupBackendErrors(detail: unknown): {
	message: string | null
	fields: FieldErrors
} {
	let fields: FieldErrors = {}
	let message: string | null = null

	if (Array.isArray(detail)) {
		for (const item of detail) {
			const itemMessage = messageFromUnknown(item) ?? 'invalid value'
			const field = isRecord(item) ? fieldFromLocation(item.loc) : null
			if (field) {
				fields = setFieldError(fields, field, itemMessage)
			} else if (!message) {
				message = itemMessage
			}
		}
		return { message, fields }
	}

	const stringMessage = messageFromUnknown(detail)
	if (stringMessage) {
		const duplicateField = duplicateFieldFromMessage(stringMessage)
		if (duplicateField) fields = setFieldError(fields, duplicateField, stringMessage)
		return { message: duplicateField ? null : stringMessage, fields }
	}

	if (isRecord(detail)) {
		for (const key of ['display_name', 'displayName', 'username', 'email', 'password']) {
			const field = signupFieldFromValue(key)
			const value = detail[key]
			const fieldMessage = messageFromUnknown(Array.isArray(value) ? value[0] : value)
			if (field && fieldMessage) fields = setFieldError(fields, field, fieldMessage)
		}
	}

	return { message: null, fields }
}

export function signupSubmissionErrorMessage(error: unknown): string {
	if (error instanceof Error) {
		const message = error.message.trim()
		if (!message) return 'failed to create account'
		if (
			error instanceof TypeError ||
			/failed to fetch|networkerror|load failed/i.test(message)
		) {
			return 'could not reach the server. try again in a moment.'
		}
		return message
	}
	return 'failed to create account'
}
