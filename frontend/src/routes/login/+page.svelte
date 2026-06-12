<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { page } from '$app/state'
	import { api } from '$lib/api/client'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ExclamationTriangle from '$lib/components/icons/ExclamationTriangle.svelte'
	import { initAuthenticatedSession } from '$lib/init'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { settingsState } from '$lib/stores/settings.svelte'

	let identifier = $state('')
	let password = $state('')
	let isSubmitting = $state(false)
	let errorMessage = $state<string | null>(null)
	type LoginField = 'identifier' | 'password'
	type LoginFieldErrors = Partial<Record<LoginField, string>>
	let touched = $state<Record<LoginField, boolean>>({ identifier: false, password: false })
	let submitted = $state(false)
	let serverFieldErrors = $state<LoginFieldErrors>({})

	// NOTE: searchParams access must be guarded for SSG/prerender compatibility
	const next = $derived(
		browser
			? typeof page.state.next === 'string'
				? page.state.next
				: (page.url.searchParams.get('next') ?? '/')
			: '/'
	)

	pageTitleStore.pageTitle = 'login'

	const allowSignups = $derived(settingsState.data?.security?.allow_signups ?? true)
	const oidcOnly = $derived(settingsState.data?.security?.oidc?.only ?? false)

	$effect(() => {
		if (!browser) return
		const fromState = page.state.email
		if (fromState && !identifier) identifier = fromState
		const fromQuery = page.url.searchParams.get('email')
		if (fromQuery && !identifier) identifier = fromQuery
	})

	function nextTargetFromNextValue(
		nextValue: string
	): { type: 'home' } | { type: 'chat'; id: string } {
		if (nextValue.startsWith('/c/')) {
			const id = nextValue.slice(3).split(/[/?#]/)[0]
			if (id) return { type: 'chat', id }
		}
		return { type: 'home' }
	}

	function markTouched(field: LoginField): void {
		touched[field] = true
	}

	function validateFields(): LoginFieldErrors {
		const errors: LoginFieldErrors = {}
		if (!identifier.trim()) errors.identifier = 'email or username is required'
		if (!password) errors.password = 'password is required'
		return errors
	}

	function hasErrors(errors: LoginFieldErrors): boolean {
		return Object.values(errors).some(Boolean)
	}

	function fieldError(field: LoginField): string | null {
		const serverError = serverFieldErrors[field]
		if (serverError) return serverError
		if (!submitted && !touched[field]) return null
		return validateFields()[field] ?? null
	}

	function inputClass(field: LoginField): string {
		const hasError = Boolean(fieldError(field))
		const stateClass = hasError
			? 'border-red-400/70 bg-red-500/10 text-red-50 placeholder:text-red-300/45 focus:border-red-300/80'
			: 'border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/35 focus:border-foreground/20'
		return `${stateClass} w-full rounded-full border px-4 py-3 text-sm transition-colors outline-none`
	}

	function fieldFromLocation(location: unknown): LoginField | null {
		if (!Array.isArray(location)) return null
		for (let i = location.length - 1; i >= 0; i -= 1) {
			const value = location[i]
			if (value === 'username') return 'identifier'
			if (value === 'password') return 'password'
		}
		return null
	}

	function parseBackendErrors(detail: unknown): {
		message: string | null
		fields: LoginFieldErrors
	} {
		let fields: LoginFieldErrors = {}
		let message: string | null = null

		if (!Array.isArray(detail)) return { message, fields }
		for (const item of detail) {
			const itemMessage =
				item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string'
					? item.msg
					: 'invalid value'
			const field = item && typeof item === 'object' ? fieldFromLocation(item.loc) : null
			if (field) fields = { ...fields, [field]: itemMessage }
			else if (!message) message = itemMessage
		}
		return { message, fields }
	}

	function submitErrorMessage(error: unknown): string {
		if (error instanceof Error) {
			const message = error.message.trim()
			if (!message) return 'failed to sign in'
			if (
				error instanceof TypeError ||
				/failed to fetch|networkerror|load failed/i.test(message)
			) {
				return 'could not reach the server. try again in a moment.'
			}
			return message
		}
		return 'failed to sign in'
	}

	async function onSubmit(event: SubmitEvent) {
		event.preventDefault()
		if (isSubmitting) return
		if (oidcOnly) return

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
			const { data, error, response } = await api.POST('/v1/auth/login/access-token', {
				headers: {
					'Content-Type': 'application/x-www-form-urlencoded',
				},
				body: {
					username: identifier.trim(),
					password,
					scope: '',
				},
			})

			if (error || !data) {
				const detail = (error as { detail?: unknown } | undefined)?.detail
				if (typeof detail === 'string' && detail) throw new Error(detail)
				const parsed = parseBackendErrors(detail)
				if (hasErrors(parsed.fields)) {
					serverFieldErrors = parsed.fields
					throw new Error(parsed.message ?? 'check the highlighted fields')
				}
				if (parsed.message) throw new Error(parsed.message)
				throw new Error(response.statusText || 'failed to sign in')
			}

			session.setToken(data.access_token)
			// start the authenticated session (user data, event stream, preference
			// sync, etc.) before navigating. initApp only ran the unauthenticated
			// branch at startup, so without this the preference sync never starts
			// and settings toggles no-op until a manual reload.
			await initAuthenticatedSession()
			const target = nextTargetFromNextValue(next)
			if (target.type === 'chat') {
				await goto(resolve('/c/[id]', { id: target.id }))
			} else {
				await goto(resolve('/'))
			}
		} catch (err) {
			errorMessage = submitErrorMessage(err)
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
							<h1 class="text-foreground text-2xl font-medium">welcome back</h1>
							<p class="text-foreground/55 text-sm">sign in to continue</p>
						</div>

						<form class="space-y-4" onsubmit={onSubmit}>
							<div class="space-y-2">
								<label
									class="text-foreground/75 text-sm font-medium"
									for="identifier">email or username</label
								>
								<input
									id="identifier"
									type="text"
									autocomplete="username"
									required
									bind:value={identifier}
									onblur={() => markTouched('identifier')}
									placeholder="email or username"
									aria-invalid={Boolean(fieldError('identifier'))}
									aria-describedby="identifier-error"
									class={inputClass('identifier')}
								/>
								{#if fieldError('identifier')}
									<p
										id="identifier-error"
										class="flex min-h-8 w-full items-center justify-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-center text-xs text-red-200"
									>
										<ExclamationTriangle class="size-3.5 shrink-0" />
										<span>{fieldError('identifier')}</span>
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
									autocomplete="current-password"
									required
									bind:value={password}
									onblur={() => markTouched('password')}
									placeholder="••••••••"
									aria-invalid={Boolean(fieldError('password'))}
									aria-describedby="password-error"
									class={inputClass('password')}
								/>
								{#if fieldError('password')}
									<p
										id="password-error"
										class="flex min-h-8 w-full items-center justify-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-center text-xs text-red-200"
									>
										<ExclamationTriangle class="size-3.5 shrink-0" />
										<span>{fieldError('password')}</span>
									</p>
								{/if}
							</div>

							{#if oidcOnly}
								<div
									class="flex min-h-10 items-center justify-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-center text-sm text-amber-200"
									role="alert"
								>
									<ExclamationTriangle class="size-4 shrink-0" />
									<span>password login is disabled. sign in with oidc.</span>
								</div>
							{:else if errorMessage}
								<div
									class="flex min-h-10 items-center justify-center gap-2 rounded-full border border-red-500/30 bg-red-500/10 px-4 py-2 text-center text-sm text-red-200"
									role="alert"
								>
									<ExclamationTriangle class="size-4 shrink-0" />
									<span>{errorMessage}</span>
								</div>
							{/if}

							<button
								type="submit"
								disabled={isSubmitting || oidcOnly}
								class="interactive bg-foreground text-background hover:bg-foreground/90 focus-visible:ring-foreground/20 inline-flex h-11 w-full items-center justify-center rounded-full font-medium transition-all focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100"
							>
								{#if isSubmitting}
									<ShimmerText
										className="inline-block"
										textColor="var(--background)"
										waveColor="color-mix(in oklch, var(--background) 35%, transparent)"
									>
										signing in
									</ShimmerText>
								{:else}
									sign in
								{/if}
							</button>
						</form>

						{#if allowSignups}
							<div class="text-foreground/55 mt-6 text-center text-sm">
								don't have an account?
								<a
									href={resolve('/signup')}
									class="text-foreground/80 hover:text-foreground ml-1 font-medium"
								>
									sign up
								</a>
							</div>
						{/if}
					</div>
				</div>
			</div>
		</div>
	</div>
</div>
