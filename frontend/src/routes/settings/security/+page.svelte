<script lang="ts">
	import { api } from '$lib/api/client'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import LockClosed from '$lib/components/icons/LockClosed.svelte'
	import ShieldCheck from '$lib/components/icons/ShieldCheck.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { session } from '$lib/stores/session.svelte'

	let currentPassword = $state('')
	let newPassword = $state('')
	let saving = $state(false)
	let error = $state<string | null>(null)
	let success = $state(false)

	// change email state
	let newEmail = $state('')
	let emailSaving = $state(false)
	let emailError = $state<string | null>(null)
	let emailSuccess = $state(false)

	const currentEmail = $derived(session.currentUser?.email ?? '')

	const canSubmit = $derived(currentPassword.length > 0 && newPassword.length >= 8)
	const canSubmitEmail = $derived(newEmail.trim().length > 0 && newEmail.trim() !== currentEmail)

	async function handleSubmit(e: Event): Promise<void> {
		e.preventDefault()
		if (!canSubmit || saving) return
		saving = true
		error = null
		success = false
		try {
			const { response, error: apiError } = await api.POST(
				'/v1/auth/change-password',
				{ body: { current_password: currentPassword, new_password: newPassword } }
			)
			if (!response.ok) {
				const detail = (apiError as Record<string, unknown>)?.detail
				error = typeof detail === 'string' ? detail : 'failed to change password'
				return
			}
			success = true
			currentPassword = ''
			newPassword = ''
		} catch {
			error = 'network error'
		} finally {
			saving = false
		}
	}

	async function handleEmailSubmit(e: Event): Promise<void> {
		e.preventDefault()
		if (!canSubmitEmail || emailSaving) return
		const uid = session.currentUser?.id
		if (!uid) return
		emailSaving = true
		emailError = null
		emailSuccess = false
		try {
			const {
				data,
				error: apiError,
				response,
			} = await api.PATCH('/v1/users/{user_id}', {
				params: { path: { user_id: uid } },
				body: { email: newEmail.trim() },
			})
			if (!response.ok) {
				const detail = (apiError as Record<string, unknown>)?.detail
				emailError = typeof detail === 'string' ? detail : 'failed to update email'
				return
			}
			if (data) session.currentUser = { ...data }
			emailSuccess = true
			newEmail = ''
		} catch {
			emailError = 'network error'
		} finally {
			emailSaving = false
		}
	}
</script>

<SettingsSectionLayout
	icon={ShieldCheck}
	label="security"
	description="authentication, passwords, and access control"
>
	<div class="space-y-4">
		<!-- JWT / session info -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="flex items-center gap-2">
				<LockClosed class="h-4.5 w-4.5 text-foreground/60" />
				<div class="text-sm font-semibold text-foreground">session</div>
			</div>
			<div class="mt-1 text-sm text-foreground/50">
				your current session is secured with a JWT token. tokens are automatically
				refreshed.
			</div>
			<div class="mt-4 flex items-center gap-3">
				<div
					class="rounded-pill flex items-center gap-2 border border-green-500/30 bg-green-500/10 px-3 py-1.5 text-xs text-green-400"
				>
					<span class="h-1.5 w-1.5 rounded-full bg-green-400"></span>
					active session
				</div>
			</div>
		</div>

		<!-- change password -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-foreground">change password</div>
			<div class="mt-1 text-sm text-foreground/50">
				update your account password. you'll need to enter your current password.
			</div>
			<form class="mt-4 space-y-3" onsubmit={handleSubmit} autocomplete="off">
				<div>
					<label
						class="mb-1.5 block text-xs font-medium text-foreground/50"
						for="current-password">current password</label
					>
					<input
						id="current-password"
						type="password"
						autocomplete="current-password"
						class="rounded-pill w-full border border-foreground/10 bg-foreground/5 px-4 py-2.5 text-sm text-foreground/90 placeholder:text-foreground/40 transition-colors outline-none focus:border-foreground/20 focus:bg-foreground/8"
						placeholder="enter current password"
						bind:value={currentPassword}
						disabled={saving}
					/>
				</div>
				<div>
					<label class="mb-1.5 block text-xs font-medium text-foreground/50" for="new-password"
						>new password</label
					>
					<input
						id="new-password"
						type="password"
						autocomplete="new-password"
						class="rounded-pill w-full border border-foreground/10 bg-foreground/5 px-4 py-2.5 text-sm text-foreground/90 placeholder:text-foreground/40 transition-colors outline-none focus:border-foreground/20 focus:bg-foreground/8"
						placeholder="enter new password (min 8 characters)"
						bind:value={newPassword}
						disabled={saving}
					/>
				</div>

				{#if error}
					<p class="text-xs text-red-400">{error}</p>
				{/if}
				{#if success}
					<p class="text-xs text-green-400">password updated successfully</p>
				{/if}

				<button
					type="submit"
					disabled={!canSubmit || saving}
					class="rounded-pill border border-foreground/10 bg-foreground/10 px-4 py-2 text-sm text-foreground/80 transition-colors hover:bg-foreground/15 disabled:text-foreground/40 disabled:hover:bg-foreground/10"
				>
					{#if saving}
						<ShimmerText className="inline-block">updating</ShimmerText>
					{:else}
						update password
					{/if}
				</button>
			</form>
		</div>

		<!-- OIDC -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-foreground">external authentication</div>
			<div class="mt-1 text-sm text-foreground/50">
				connect your account to an external identity provider via OpenID Connect (OIDC) for
				single sign-on.
			</div>
			<div class="mt-4">
				<button
					type="button"
					disabled
					class="rounded-pill border border-foreground/10 bg-foreground/5 px-4 py-2 text-sm text-foreground/50 transition-colors"
				>
					connect OIDC provider
				</button>
				<p class="mt-2 text-xs text-foreground/45">coming soon</p>
			</div>
		</div>

		<!-- change email -->
		<div class="rounded-container liquid-glass liquid-glass--frosted p-5">
			<div class="text-sm font-semibold text-foreground">email address</div>
			<div class="mt-1 text-sm text-foreground/50">
				your email address for notifications and account recovery.
			</div>
			<div
				class="rounded-pill mt-3 flex w-full items-center border border-foreground/14 bg-foreground/3 px-4 py-2.5 text-sm text-foreground/60"
			>
				{currentEmail}
			</div>
			<form class="mt-3 space-y-3" onsubmit={handleEmailSubmit} autocomplete="off">
				<div>
					<label class="mb-1.5 block text-xs font-medium text-foreground/50" for="new-email"
						>new email</label
					>
					<input
						id="new-email"
						type="email"
						autocomplete="email"
						class="rounded-pill w-full border border-foreground/10 bg-foreground/5 px-4 py-2.5 text-sm text-foreground/90 placeholder:text-foreground/40 transition-colors outline-none focus:border-foreground/20 focus:bg-foreground/8"
						placeholder="new email address"
						bind:value={newEmail}
						disabled={emailSaving}
					/>
				</div>

				{#if emailError}
					<p class="text-xs text-red-400">{emailError}</p>
				{/if}
				{#if emailSuccess}
					<p class="text-xs text-green-400">email updated successfully</p>
				{/if}

				<button
					type="submit"
					disabled={!canSubmitEmail || emailSaving}
					class="rounded-pill border border-foreground/10 bg-foreground/10 px-4 py-2 text-sm text-foreground/80 transition-colors hover:bg-foreground/15 disabled:text-foreground/40 disabled:hover:bg-foreground/10"
				>
					{#if emailSaving}
						<ShimmerText className="inline-block">updating</ShimmerText>
					{:else}
						update email
					{/if}
				</button>
			</form>
		</div>
	</div>
</SettingsSectionLayout>
