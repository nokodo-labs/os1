<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { api } from '$lib/api/client'
	import { getSystemStatus } from '$lib/api/system'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { settingsState } from '$lib/stores/settings.svelte'
	import { onMount } from 'svelte'

	let email = $state('')
	let username = $state('')
	let displayName = $state('')
	let password = $state('')
	let passwordConfirm = $state('')
	let isSubmitting = $state(false)
	let isInitialized = $state<boolean | null>(null)
	let errorMessage = $state<string | null>(null)
	type SignupField = 'displayName' | 'username' | 'email' | 'password' | 'passwordConfirm'
	type FieldErrors = Partial<Record<SignupField, string>>

	let touched = $state<Record<SignupField, boolean>>({
		displayName: false,
		username: false,
		email: false,
		password: false,
		passwordConfirm: false,
	})
	let submitted = $state(false)
	let serverFieldErrors = $state<FieldErrors>({})
	let consoleOriginOverride = $state<string | null>(null)
	const USERNAME_RE = /^[a-zA-Z0-9][a-zA-Z0-9._]{1,28}[a-zA-Z0-9]$/
	const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

	pageTitleStore.pageTitle = 'sign up'

	const allowSignups = $derived(settingsState.data?.security?.allow_signups ?? true)

	const consoleOrigin = $derived(
		consoleOriginOverride ?? settingsState.data?.branding?.public_console_origin ?? null
	)

	onMount(async () => {
		if (!browser) return

		try {
			const status = await getSystemStatus()
			isInitialized = status.initialized
			if (status.initialized === false) {
				errorMessage = 'this instance needs an admin created in the console first'
			}
		} catch {
			// fallback: if the status check fails, allow signup to proceed
			isInitialized = true
		}
	})

	const clientFieldErrors = $derived(validateFields())
	const canSubmit = $derived(
		!hasErrors(clientFieldErrors) && isInitialized !== false && allowSignups
	)

	$effect(() => {
		const formValues = [username, email, displayName, password, passwordConfirm]
		if (formValues.length === 0) return
		serverFieldErrors = {}
	})

	function hasErrors(errors: FieldErrors): boolean {
		return Object.values(errors).some(Boolean)
	}

	function validateFields(): FieldErrors {
		const errors: FieldErrors = {}
		const cleanUsername = username.trim()
		const cleanEmail = email.trim()
		const cleanDisplayName = displayName.trim()

		if (cleanDisplayName.length > 80) {
			errors.displayName = 'name must be 80 characters or fewer'
		}

		if (!cleanUsername) {
			errors.username = 'username is required'
		} else if (cleanUsername.length < 3 || cleanUsername.length > 30) {
			errors.username = 'username must be 3 to 30 characters'
		} else if (!USERNAME_RE.test(cleanUsername)) {
			errors.username =
				'use letters, numbers, periods, or underscores; start and end with a letter or number'
		} else if (cleanUsername.includes('..')) {
			errors.username = 'username cannot contain consecutive periods'
		}

		if (!cleanEmail) {
			errors.email = 'email is required'
		} else if (!EMAIL_RE.test(cleanEmail)) {
			errors.email = 'enter a valid email address'
		}

		if (!password) {
			errors.password = 'password is required'
		} else if (password.length < 8) {
			errors.password = 'password must be at least 8 characters'
		}

		if (!passwordConfirm) {
			errors.passwordConfirm = 'confirm your password'
		} else if (password !== passwordConfirm) {
			errors.passwordConfirm = 'passwords do not match'
		}

		return errors
	}

	function markTouched(field: SignupField): void {
		touched[field] = true
	}

	function fieldError(field: SignupField): string | null {
		const serverError = serverFieldErrors[field]
		if (serverError) return serverError
		if (!submitted && !touched[field]) return null
		return clientFieldErrors[field] ?? null
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
		if (typeof value === 'string' && value.trim()) return value.trim()
		if (!value || typeof value !== 'object') return null
		const objectValue = value as { msg?: unknown; message?: unknown; detail?: unknown }
		return (
			messageFromUnknown(objectValue.msg) ??
			messageFromUnknown(objectValue.message) ??
			messageFromUnknown(objectValue.detail)
		)
	}

	function parseBackendErrors(detail: unknown): { message: string | null; fields: FieldErrors } {
		let fields: FieldErrors = {}
		let message: string | null = null

		if (Array.isArray(detail)) {
			for (const item of detail) {
				const itemMessage = messageFromUnknown(item) ?? 'invalid value'
				const field =
					item && typeof item === 'object'
						? fieldFromLocation((item as { loc?: unknown }).loc)
						: null
				if (field) {
					fields = setFieldError(fields, field, itemMessage)
				} else if (!message) {
					message = itemMessage
				}
			}
			return { message, fields }
		}

		if (detail && typeof detail === 'object') {
			const objectDetail = detail as Record<string, unknown>
			for (const key of ['display_name', 'displayName', 'username', 'email', 'password']) {
				const field = signupFieldFromValue(key)
				const value = objectDetail[key]
				const fieldMessage = messageFromUnknown(Array.isArray(value) ? value[0] : value)
				if (field && fieldMessage) fields = setFieldError(fields, field, fieldMessage)
			}
		}

		return { message: messageFromUnknown(detail), fields }
	}

	async function onSubmit(event: SubmitEvent) {
		event.preventDefault()
		if (isSubmitting) return
		if (isInitialized === false) return
		if (!allowSignups) return

		submitted = true
		errorMessage = null
		serverFieldErrors = {}

		const validationErrors = validateFields()
		if (hasErrors(validationErrors)) {
			errorMessage = 'fix the highlighted fields'
			return
		}

		isSubmitting = true
		try {
			const { data, error, response } = await api.POST('/v1/users', {
				body: {
					email: email.trim(),
					password,
					username: username.trim(),
					display_name: displayName.trim() ? displayName.trim() : null,
				},
			})
			if (error || !response.ok || !data) {
				const detail = (error as { detail?: unknown } | undefined)?.detail
				if (typeof detail === 'string' && detail) throw new Error(detail)
				if (
					detail &&
					typeof detail === 'object' &&
					'code' in detail &&
					(detail as { code?: unknown }).code === 'bootstrap_required'
				) {
					const message = (detail as { message?: unknown }).message
					const origin = (detail as { console_origin?: unknown }).console_origin
					if (typeof origin === 'string' && origin) consoleOriginOverride = origin
					if (typeof message === 'string' && message) throw new Error(message)
				}
				const parsed = parseBackendErrors(detail)
				if (hasErrors(parsed.fields)) {
					serverFieldErrors = parsed.fields
					throw new Error(parsed.message ?? 'check the highlighted fields')
				}
				if (parsed.message) throw new Error(parsed.message)
				throw new Error(response.statusText || 'failed to create account')
			}
			await goto(resolve('/login'), { state: { email: email.trim() } })
		} catch (err) {
			errorMessage = err instanceof Error ? err.message : 'failed to create account'
		} finally {
			isSubmitting = false
		}
	}
</script>

<div class="flex-1 overflow-y-auto">
	<div class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-8 pt-8 pb-24">
		<div class="flex flex-1 items-center justify-center">
			<div class="w-full max-w-md">
				<div
					class="liquid-glass liquid-glass--frosted rounded-container overflow-hidden shadow-[0_28px_80px_rgba(0,0,0,0.45)]"
				>
					<div class="p-8">
						<div class="mb-8 space-y-2">
							<h1 class="text-foreground text-2xl font-medium">
								create your account
							</h1>
							<p class="text-foreground/55 text-sm">sign up to get started</p>
						</div>

						<form class="space-y-4" onsubmit={onSubmit}>
							{#if isInitialized === false}
								<div
									class="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
									role="alert"
								>
									setup is required before accounts can be created.
									{#if consoleOrigin}
										{#if consoleOrigin.startsWith('http:')}
											<a
												href={`http://${consoleOrigin.replace(/^https?:\/\//, '')}`}
												target="_blank"
												rel="noreferrer"
												class="bg-foreground text-background hover:bg-foreground/90 mt-2 inline-flex h-10 w-full cursor-pointer items-center justify-center rounded-full font-medium"
											>
												go to console
											</a>
										{:else}
											<a
												href={`https://${consoleOrigin.replace(/^https?:\/\//, '')}`}
												target="_blank"
												rel="noreferrer"
												class="bg-foreground text-background hover:bg-foreground/90 mt-2 inline-flex h-10 w-full cursor-pointer items-center justify-center rounded-full font-medium"
											>
												go to console
											</a>
										{/if}
									{/if}
								</div>
							{/if}
							{#if !allowSignups}
								<div
									class="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
									role="alert"
								>
									signups are currently disabled.
								</div>
							{/if}
							<div class="space-y-2">
								<label
									class="text-foreground/75 text-sm font-medium"
									for="displayName">name</label
								>
								<input
									id="displayName"
									type="text"
									autocomplete="name"
									bind:value={displayName}
									onblur={() => markTouched('displayName')}
									placeholder="optional"
									aria-invalid={Boolean(fieldError('displayName'))}
									aria-describedby="displayName-error"
									class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/35 focus:border-foreground/20 w-full rounded-full border px-4 py-3 text-sm transition-colors outline-none"
								/>
								{#if fieldError('displayName')}
									<p id="displayName-error" class="text-sm text-red-300/85">
										{fieldError('displayName')}
									</p>
								{/if}
							</div>

							<div class="space-y-2">
								<label class="text-foreground/75 text-sm font-medium" for="username"
									>username</label
								>
								<input
									id="username"
									type="text"
									autocomplete="username"
									required
									bind:value={username}
									onblur={() => markTouched('username')}
									placeholder="3 to 30 characters"
									aria-invalid={Boolean(fieldError('username'))}
									aria-describedby="username-error"
									class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/35 focus:border-foreground/20 w-full rounded-full border px-4 py-3 text-sm transition-colors outline-none"
								/>
								{#if fieldError('username')}
									<p id="username-error" class="text-sm text-red-300/85">
										{fieldError('username')}
									</p>
								{/if}
							</div>

							<div class="space-y-2">
								<label class="text-foreground/75 text-sm font-medium" for="email"
									>email</label
								>
								<input
									id="email"
									type="email"
									autocomplete="email"
									required
									bind:value={email}
									onblur={() => markTouched('email')}
									placeholder="you@nokodo.net"
									aria-invalid={Boolean(fieldError('email'))}
									aria-describedby="email-error"
									class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/35 focus:border-foreground/20 w-full rounded-full border px-4 py-3 text-sm transition-colors outline-none"
								/>
								{#if fieldError('email')}
									<p id="email-error" class="text-sm text-red-300/85">
										{fieldError('email')}
									</p>
								{/if}
							</div>

							<div class="space-y-2">
								<label class="text-foreground/75 text-sm font-medium" for="password"
									>password</label
								>
								<input
									id="password"
									type="password"
									autocomplete="new-password"
									required
									bind:value={password}
									onblur={() => markTouched('password')}
									placeholder="••••••••"
									aria-invalid={Boolean(fieldError('password'))}
									aria-describedby="password-error"
									class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/35 focus:border-foreground/20 w-full rounded-full border px-4 py-3 text-sm transition-colors outline-none"
								/>
								{#if fieldError('password')}
									<p id="password-error" class="text-sm text-red-300/85">
										{fieldError('password')}
									</p>
								{/if}
							</div>

							<div class="space-y-2">
								<label
									class="text-foreground/75 text-sm font-medium"
									for="passwordConfirm">confirm password</label
								>
								<input
									id="passwordConfirm"
									type="password"
									autocomplete="new-password"
									required
									bind:value={passwordConfirm}
									onblur={() => markTouched('passwordConfirm')}
									placeholder="••••••••"
									aria-invalid={Boolean(fieldError('passwordConfirm'))}
									aria-describedby="passwordConfirm-error"
									class="border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/35 focus:border-foreground/20 w-full rounded-full border px-4 py-3 text-sm transition-colors outline-none"
								/>
								{#if fieldError('passwordConfirm')}
									<p id="passwordConfirm-error" class="text-sm text-red-300/85">
										{fieldError('passwordConfirm')}
									</p>
								{/if}
							</div>

							{#if errorMessage}
								<div
									class="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200"
									role="alert"
								>
									{errorMessage}
								</div>
							{/if}

							<button
								type="submit"
								disabled={!canSubmit || isSubmitting}
								class="interactive bg-foreground text-background hover:bg-foreground/90 focus-visible:ring-foreground/20 inline-flex h-11 w-full items-center justify-center rounded-full font-medium transition-all focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100"
							>
								{#if isSubmitting}
									<ShimmerText
										className="inline-block"
										textColor="var(--background)"
										waveColor="color-mix(in oklch, var(--background) 35%, transparent)"
									>
										creating account
									</ShimmerText>
								{:else}
									sign up
								{/if}
							</button>
						</form>

						<div class="text-foreground/55 mt-6 text-center text-sm">
							already have an account?
							<a
								href={resolve('/login')}
								class="text-foreground/80 hover:text-foreground ml-1 font-medium"
							>
								sign in
							</a>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</div>
