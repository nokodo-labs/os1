<script lang="ts">
	import { api } from '$lib/api/client'
	import { logoutAndRedirect } from '$lib/auth/logout'
	import { cancelRevocationLogoutDefer, deferRevocationLogout } from '$lib/auth/sessionRevocation'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte'
	import DevicePhone from '$lib/components/icons/DevicePhone.svelte'
	import ExclamationTriangle from '$lib/components/icons/ExclamationTriangle.svelte'
	import FloppyDisk from '$lib/components/icons/FloppyDisk.svelte'
	import Link from '$lib/components/icons/Link.svelte'
	import LockClosed from '$lib/components/icons/LockClosed.svelte'
	import Mail from '$lib/components/icons/Mail.svelte'
	import ShieldCheck from '$lib/components/icons/ShieldCheck.svelte'
	import SignOut from '$lib/components/icons/SignOut.svelte'
	import { ModalFormDirty } from '$lib/components/modals/formDirty.svelte'
	import { ActionButton } from '$lib/components/primitives'
	import { securityFields } from '$lib/components/settings/fields/security'
	import SettingsField from '$lib/components/settings/SettingsField.svelte'
	import SettingsSectionLayout from '$lib/components/settings/SettingsSectionLayout.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { session } from '$lib/stores/session.svelte'

	/** mirrors `UserPasswordChange.new_password` (`min_length=8`) on the backend. */
	const MIN_PASSWORD_LENGTH = 8

	let currentPassword = $state('')
	let newPassword = $state('')
	let confirmPassword = $state('')
	let touchedCurrent = $state(false)
	let touchedNew = $state(false)
	let touchedConfirm = $state(false)
	let submitted = $state(false)
	let saving = $state(false)
	let formError = $state<string | null>(null)
	let serverCurrentError = $state<string | null>(null)
	let success = $state(false)

	const passwordDirty = new ModalFormDirty(() => ({
		currentPassword,
		newPassword,
		confirmPassword,
	}))

	$effect(() => {
		passwordDirty.reset()
	})

	const currentRule = $derived(currentPassword ? null : 'current password is required')
	const newRule = $derived(
		!newPassword
			? 'new password is required'
			: newPassword.length < MIN_PASSWORD_LENGTH
				? `new password must be at least ${MIN_PASSWORD_LENGTH} characters`
				: null
	)
	const confirmRule = $derived(
		!confirmPassword
			? 'confirm your new password'
			: confirmPassword !== newPassword
				? 'passwords do not match'
				: null
	)

	// a rule only shows once the field has been visited or the form was submitted
	const currentError = $derived(
		serverCurrentError ?? (submitted || touchedCurrent ? currentRule : null)
	)
	const newError = $derived(submitted || touchedNew ? newRule : null)
	const confirmError = $derived(submitted || touchedConfirm ? confirmRule : null)

	const passwordValid = $derived(!currentRule && !newRule && !confirmRule)
	const canSubmitPassword = $derived(passwordValid && passwordDirty.dirty)

	function fieldClass(hasError: boolean): string {
		const state = hasError
			? 'border-red-500/45 bg-red-500/8 focus:border-red-400/70'
			: 'border-foreground/10 bg-foreground/5 focus:border-foreground/20 focus:bg-foreground/8'
		return `${state} rounded-pill text-foreground/90 placeholder:text-foreground/40 w-full border px-4 py-2.5 text-sm transition-colors outline-none disabled:opacity-50`
	}

	async function submitPassword(): Promise<void> {
		submitted = true
		serverCurrentError = null
		if (!canSubmitPassword || saving) return
		const uid = session.currentUser?.id
		if (!uid) return
		saving = true
		formError = null
		success = false
		// this tab handles its own logout below; hold the global revocation
		// watcher back so the confirmation stays readable.
		deferRevocationLogout(2000)
		try {
			const { response, error: apiError } = await api.POST(
				'/v1/users/{user_id}/change-password',
				{
					params: { path: { user_id: uid } },
					body: { current_password: currentPassword, new_password: newPassword },
				}
			)
			if (!response.ok) {
				const detail = (apiError as Record<string, unknown>)?.detail
				const message = typeof detail === 'string' ? detail : 'could not change password'
				// the backend names the offending field, so keep it next to that input
				if (message.includes('current password')) {
					serverCurrentError = message
				} else {
					formError = message
				}
				cancelRevocationLogoutDefer()
				return
			}
			success = true
			currentPassword = ''
			newPassword = ''
			confirmPassword = ''
			submitted = false
			touchedCurrent = false
			touchedNew = false
			touchedConfirm = false
			// the change revokes every session, this one included. give the user a
			// beat to read the confirmation, then send them back to sign in.
			setTimeout(() => {
				void logoutAndRedirect()
			}, 1500)
		} catch {
			formError = 'network error'
			cancelRevocationLogoutDefer()
		} finally {
			saving = false
		}
	}

	let revoking = $state(false)
	let revokeError = $state<string | null>(null)

	async function revokeSessions(): Promise<void> {
		if (revoking) return
		const uid = session.currentUser?.id
		if (!uid) return
		revoking = true
		revokeError = null
		try {
			const { response, error: apiError } = await api.POST(
				'/v1/users/{user_id}/sessions/revoke',
				{ params: { path: { user_id: uid } } }
			)
			if (!response.ok) {
				const detail = (apiError as Record<string, unknown>)?.detail
				revokeError = typeof detail === 'string' ? detail : 'could not log out sessions'
				return
			}
			await logoutAndRedirect()
		} catch {
			revokeError = 'network error'
		} finally {
			revoking = false
		}
	}

	function confirmRevokeSessions(): void {
		// there is no undo and every device pays for it, so it asks first
		modals.open('confirm-delete', {
			title: 'log out all sessions?',
			description:
				'every signed-in device is signed out, this one included. you will need to sign in again.',
			confirmLabel: 'log out everywhere',
			pendingLabel: 'logging out',
			confirmIcon: SignOut,
			onDelete: () => revokeSessions(),
		})
	}

	// self-service email change is gated server-side until a verification flow exists
	const emailChangeDisabled = true
	let newEmail = $state('')
	let emailCurrentPassword = $state('')
	let emailSaving = $state(false)
	let emailError = $state<string | null>(null)
	let emailSuccess = $state(false)

	const currentEmail = $derived(session.currentUser?.email ?? '')

	const canSubmitEmail = $derived(
		!emailChangeDisabled &&
			newEmail.trim().length > 0 &&
			newEmail.trim() !== currentEmail &&
			emailCurrentPassword.length > 0
	)

	async function submitEmail(): Promise<void> {
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
			} = await api.POST('/v1/users/{user_id}/change-email', {
				params: { path: { user_id: uid } },
				body: { current_password: emailCurrentPassword, new_email: newEmail.trim() },
			})
			if (!response.ok) {
				const detail = (apiError as Record<string, unknown>)?.detail
				emailError = typeof detail === 'string' ? detail : 'could not update email'
				return
			}
			if (data) session.currentUser = { ...data }
			emailSuccess = true
			newEmail = ''
			emailCurrentPassword = ''
		} catch {
			emailError = 'network error'
		} finally {
			emailSaving = false
		}
	}
</script>

{#snippet parkedBadge(label: string)}
	<span class="rounded-pill bg-foreground/5 text-foreground/45 px-2 py-0.5 text-[0.65rem]">
		{label}
	</span>
{/snippet}

{#snippet fieldMessage(id: string, message: string)}
	<p {id} class="mt-1.5 flex items-center gap-1.5 pl-4 text-xs text-red-300">
		<ExclamationTriangle class="h-3.5 w-3.5 shrink-0" />
		<span>{message}</span>
	</p>
{/snippet}

<SettingsSectionLayout
	icon={ShieldCheck}
	label="security"
	description="authentication, passwords, and access control"
>
	<div class="space-y-4">
		<SettingsField field={securityFields.session}>
			{#snippet leading()}
				<DevicePhone class="text-foreground/60 h-5 w-5" />
			{/snippet}

			<div class="mt-4">
				<div
					class="rounded-pill inline-flex items-center gap-2 border border-green-500/30 bg-green-500/10 px-3 py-1.5 text-xs text-green-400"
				>
					<span class="h-1.5 w-1.5 rounded-full bg-green-400"></span>
					active session
				</div>
			</div>

			{#if revokeError}
				<div
					class="rounded-container mt-3 border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
				>
					{revokeError}
				</div>
			{/if}

			<button
				type="button"
				onclick={confirmRevokeSessions}
				disabled={revoking}
				class="rounded-pill mt-4 inline-flex w-full cursor-pointer items-center justify-center gap-2 border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-50"
			>
				<SignOut class="h-4 w-4" />
				{#if revoking}
					<ShimmerText className="inline-block">logging out</ShimmerText>
				{:else}
					log out all sessions
				{/if}
			</button>
			<p class="text-foreground/45 mt-2 text-xs">
				signs out every signed-in device, this one included.
			</p>
		</SettingsField>

		<SettingsField field={securityFields.changePassword}>
			{#snippet leading()}
				<LockClosed class="text-foreground/60 h-5 w-5" />
			{/snippet}

			<form
				class="mt-4 space-y-3"
				autocomplete="off"
				onsubmit={(event) => {
					event.preventDefault()
					void submitPassword()
				}}
			>
				{#if formError}
					<div
						class="rounded-container border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
					>
						{formError}
					</div>
				{/if}
				{#if success}
					<div
						class="rounded-container flex items-start gap-2 border border-green-500/25 bg-green-500/10 p-3 text-sm text-green-300"
					>
						<CheckCircle class="mt-0.5 h-4 w-4 shrink-0" />
						<span>password updated. taking you to sign in with the new one...</span>
					</div>
				{/if}

				<div>
					<label
						class="text-foreground/55 mb-1.5 block pl-4 text-xs font-medium"
						for="current-password"
					>
						current password
					</label>
					<input
						id="current-password"
						type="password"
						autocomplete="current-password"
						class={fieldClass(Boolean(currentError))}
						placeholder="your password today"
						aria-invalid={Boolean(currentError)}
						aria-describedby="current-password-error"
						bind:value={currentPassword}
						onblur={() => (touchedCurrent = true)}
						disabled={saving}
					/>
					{#if currentError}
						{@render fieldMessage('current-password-error', currentError)}
					{/if}
				</div>

				<div>
					<label
						class="text-foreground/55 mb-1.5 block pl-4 text-xs font-medium"
						for="new-password"
					>
						new password
					</label>
					<input
						id="new-password"
						type="password"
						autocomplete="new-password"
						class={fieldClass(Boolean(newError))}
						placeholder="at least {MIN_PASSWORD_LENGTH} characters"
						aria-invalid={Boolean(newError)}
						aria-describedby="new-password-error"
						bind:value={newPassword}
						onblur={() => (touchedNew = true)}
						disabled={saving}
					/>
					{#if newError}
						{@render fieldMessage('new-password-error', newError)}
					{/if}
				</div>

				<div>
					<label
						class="text-foreground/55 mb-1.5 block pl-4 text-xs font-medium"
						for="confirm-password"
					>
						confirm new password
					</label>
					<input
						id="confirm-password"
						type="password"
						autocomplete="new-password"
						class={fieldClass(Boolean(confirmError))}
						placeholder="type it again"
						aria-invalid={Boolean(confirmError)}
						aria-describedby="confirm-password-error"
						bind:value={confirmPassword}
						onblur={() => (touchedConfirm = true)}
						disabled={saving}
					/>
					{#if confirmError}
						{@render fieldMessage('confirm-password-error', confirmError)}
					{/if}
				</div>

				<ActionButton
					variant="secondary"
					class="dark:border-foreground dark:bg-foreground dark:text-background dark:hover:bg-foreground/90 mt-4 w-full"
					disabled={!canSubmitPassword || saving}
					onclick={() => void submitPassword()}
				>
					<FloppyDisk class="h-4 w-4" />
					{#if saving}
						<ShimmerText className="inline-block">updating password</ShimmerText>
					{:else}
						update password
					{/if}
				</ActionButton>
				<p class="text-foreground/45 mt-2 text-xs">
					changing your password signs out every device, this one included.
				</p>
			</form>
		</SettingsField>

		<SettingsField field={securityFields.emailAddress}>
			{#snippet leading()}
				<Mail class="text-foreground/60 h-5 w-5" />
			{/snippet}

			<div
				class="rounded-pill border-foreground/14 bg-foreground/3 text-foreground/60 mt-4 flex w-full items-center gap-2 border px-4 py-2.5 text-sm"
			>
				<span class="truncate">{currentEmail}</span>
			</div>

			<div class="mt-4 flex items-center justify-between gap-3">
				<div class="text-foreground/70 text-sm font-medium">change email</div>
				{@render parkedBadge('admin only')}
			</div>
			<p class="text-foreground/45 mt-1 text-xs">
				email changes are handled by an administrator until address verification ships.
			</p>

			<form
				class="mt-3 space-y-3 {emailChangeDisabled ? 'opacity-55' : ''}"
				autocomplete="off"
				onsubmit={(event) => {
					event.preventDefault()
					void submitEmail()
				}}
			>
				<div>
					<label
						class="text-foreground/55 mb-1.5 block pl-4 text-xs font-medium"
						for="new-email"
					>
						new email
					</label>
					<input
						id="new-email"
						type="email"
						autocomplete="email"
						class={fieldClass(false)}
						placeholder="new email address"
						bind:value={newEmail}
						disabled={emailChangeDisabled || emailSaving}
					/>
				</div>
				<div>
					<label
						class="text-foreground/55 mb-1.5 block pl-4 text-xs font-medium"
						for="email-current-password"
					>
						current password
					</label>
					<input
						id="email-current-password"
						type="password"
						autocomplete="current-password"
						class={fieldClass(false)}
						placeholder="your password today"
						bind:value={emailCurrentPassword}
						disabled={emailChangeDisabled || emailSaving}
					/>
				</div>

				{#if emailError}
					<div
						class="rounded-container border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300"
					>
						{emailError}
					</div>
				{/if}
				{#if emailSuccess}
					<div
						class="rounded-container flex items-start gap-2 border border-green-500/25 bg-green-500/10 p-3 text-sm text-green-300"
					>
						<CheckCircle class="mt-0.5 h-4 w-4 shrink-0" />
						<span>email updated.</span>
					</div>
				{/if}

				<ActionButton
					variant="secondary"
					class="w-full"
					disabled={!canSubmitEmail || emailSaving}
					onclick={() => void submitEmail()}
				>
					<FloppyDisk class="h-4 w-4" />
					{#if emailSaving}
						<ShimmerText className="inline-block">updating email</ShimmerText>
					{:else}
						update email
					{/if}
				</ActionButton>
			</form>
		</SettingsField>

		<SettingsField field={securityFields.externalAuthentication}>
			{#snippet leading()}
				<Link class="text-foreground/60 h-5 w-5" />
			{/snippet}

			<div class="mt-4 flex items-center justify-between gap-3">
				<div class="text-foreground/70 text-sm font-medium">connect a provider</div>
				{@render parkedBadge('soon')}
			</div>
			<ActionButton variant="secondary" class="mt-3 w-full" disabled>
				<Link class="h-4 w-4" />
				connect OIDC provider
			</ActionButton>
		</SettingsField>
	</div>
</SettingsSectionLayout>
