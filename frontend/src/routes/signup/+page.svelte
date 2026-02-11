<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { apiClient } from '$lib/api/client'
	import { getSystemStatus } from '$lib/api/system'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import { background } from '$lib/stores/background.svelte'
	import { pageTitleStore } from '$lib/stores/pageTitle.svelte'
	import { settingsState } from '$lib/stores/settings.svelte'
	import { onMount } from 'svelte'

	let email = $state('')
	let displayName = $state('')
	let password = $state('')
	let passwordConfirm = $state('')
	let isSubmitting = $state(false)
	let isInitialized = $state<boolean | null>(null)
	let errorMessage = $state<string | null>(null)
	let consoleOriginOverride = $state<string | null>(null)

	pageTitleStore.pageTitle = 'sign up'

	const allowSignups = $derived(settingsState.data?.security?.allow_signups ?? true)

	// auth pages use the admin-configured auth background
	$effect(() => {
		background.setPage(background.auth)
		return background.clearPage
	})

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

	const canSubmit = $derived(
		email.trim().length > 0 &&
			password.length >= 1 &&
			passwordConfirm.length >= 1 &&
			password === passwordConfirm &&
			isInitialized !== false &&
			allowSignups
	)

	async function onSubmit(event: SubmitEvent) {
		event.preventDefault()
		if (isSubmitting) return
		if (isInitialized === false) return
		if (!allowSignups) return

		errorMessage = null

		if (password !== passwordConfirm) {
			errorMessage = 'passwords do not match'
			return
		}

		isSubmitting = true
		try {
			const { data, error, response } = await apiClient().POST('/v1/users', {
				body: {
					email: email.trim(),
					password,
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
							<h1 class="text-2xl font-medium text-white">create your account</h1>
							<p class="text-sm text-white/55">sign up to get started</p>
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
												class="mt-2 inline-flex h-10 w-full cursor-pointer items-center justify-center rounded-full bg-white font-medium text-black hover:bg-white/90"
											>
												go to console
											</a>
										{:else}
											<a
												href={`https://${consoleOrigin.replace(/^https?:\/\//, '')}`}
												target="_blank"
												rel="noreferrer"
												class="mt-2 inline-flex h-10 w-full cursor-pointer items-center justify-center rounded-full bg-white font-medium text-black hover:bg-white/90"
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
								<label class="text-sm font-medium text-white/75" for="displayName"
									>name</label
								>
								<input
									id="displayName"
									type="text"
									autocomplete="name"
									bind:value={displayName}
									placeholder="optional"
									class="w-full rounded-full border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							<div class="space-y-2">
								<label class="text-sm font-medium text-white/75" for="email"
									>email</label
								>
								<input
									id="email"
									type="email"
									autocomplete="email"
									required
									bind:value={email}
									placeholder="you@nokodo.net"
									class="w-full rounded-full border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							<div class="space-y-2">
								<label class="text-sm font-medium text-white/75" for="password"
									>password</label
								>
								<input
									id="password"
									type="password"
									autocomplete="new-password"
									required
									bind:value={password}
									placeholder="••••••••"
									class="w-full rounded-full border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							<div class="space-y-2">
								<label
									class="text-sm font-medium text-white/75"
									for="passwordConfirm">confirm password</label
								>
								<input
									id="passwordConfirm"
									type="password"
									autocomplete="new-password"
									required
									bind:value={passwordConfirm}
									placeholder="••••••••"
									class="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/90 transition-colors outline-none placeholder:text-white/35 focus:border-white/20"
								/>
							</div>

							{#if passwordConfirm.length > 0 && password !== passwordConfirm}
								<div class="text-sm text-amber-300/80">passwords must match</div>
							{/if}

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
								class="interactive inline-flex h-11 w-full items-center justify-center rounded-full bg-white font-medium text-black transition-all hover:bg-white/90 focus-visible:ring-2 focus-visible:ring-black/20 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100"
							>
								{#if isSubmitting}
									<ShimmerText
										className="inline-block"
										textColor="rgb(0 0 0 / 1)"
										waveColor="rgb(0 0 0 / 0.35)"
									>
										creating account
									</ShimmerText>
								{:else}
									sign up
								{/if}
							</button>
						</form>

						<div class="mt-6 text-center text-sm text-white/55">
							already have an account?
							<a
								href={resolve('/login')}
								class="ml-1 font-medium text-white/80 hover:text-white"
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
