import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import type { StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { device } from '$lib/stores/device.svelte'
import { session } from '$lib/stores/session.svelte'
import { settingsState } from '$lib/stores/settings.svelte'
import { STORE_EVENT_TYPES, storeEventData, subscribeToStoreEvents } from '$lib/stores/storeEvents'
import { ensureUserClient, userClient } from '$lib/stores/userClient.svelte'
import { deepMerge, isPlainObject } from '$lib/utils'

type UserPreferences = components['schemas']['UserPreferences']
type UserClient = components['schemas']['UserClient']
type UserClientPreferences = components['schemas']['UserClientPreferences']
type AppearancePreferences = components['schemas']['AppearancePreferences']
type AccountPreferences = components['schemas']['AccountPreferences']
type AIPreferences = components['schemas']['AIPreferences']
type NotificationPreferences = components['schemas']['NotificationPreferences']
type PrivacyPreferences = components['schemas']['PrivacyPreferences']
type AccessibilityPreferences = components['schemas']['AccessibilityPreferences']
type AdvancedPreferences = components['schemas']['AdvancedPreferences']
type DebugPreferences = components['schemas']['DebugPreferences']
type HomepagePreferences = components['schemas']['HomepagePreferences']

export type {
	AccessibilityPreferences,
	AccountPreferences,
	AdvancedPreferences,
	AIPreferences,
	AppearancePreferences,
	DebugPreferences,
	HomepagePreferences,
	NotificationPreferences,
	PrivacyPreferences,
	UserClientPreferences,
	UserPreferences,
}

export type ThemeMode = NonNullable<AppearancePreferences['themeMode']>
export type AccentColor = NonNullable<AppearancePreferences['accent']>
export type BackgroundType = NonNullable<AppearancePreferences['background']>
export type BubbleTailStyle = NonNullable<AppearancePreferences['bubbleTailStyle']>
export type BubbleAnimation = NonNullable<AppearancePreferences['bubbleAnimation']>
export type ClientPreferenceScope = 'synced' | 'client'
export type WallpaperPreferenceScope = ClientPreferenceScope

type WallpaperPreferenceUpdates = Pick<
	AppearancePreferences,
	'autoBackground' | 'background' | 'staticColor'
>

type ExperimentalUiPreferenceUpdates = Pick<
	AdvancedPreferences,
	'svgLiquidGlass' | 'svgLiquidGlassIsland' | 'svgLiquidMetal'
>

type Resolved = {
	appearance: Required<AppearancePreferences>
	account: Required<AccountPreferences>
	ai: Required<AIPreferences>
	notifications: Required<NotificationPreferences>
	privacy: Required<PrivacyPreferences>
	accessibility: Required<AccessibilityPreferences>
	advanced: Required<AdvancedPreferences>
	debug: Required<DebugPreferences>
	homepage: Required<HomepagePreferences>
}

const STORAGE_KEY = 'user-preferences:'

// local storage helpers

function readStorage(userId: string): UserPreferences {
	if (!browser) return {}
	try {
		const raw = localStorage.getItem(`${STORAGE_KEY}${userId}`)
		if (!raw) return {}
		const parsed = JSON.parse(raw)
		return isPlainObject(parsed) ? (parsed as UserPreferences) : {}
	} catch {
		return {}
	}
}

function writeStorage(userId: string, prefs: UserPreferences): void {
	if (!browser) return
	try {
		localStorage.setItem(`${STORAGE_KEY}${userId}`, JSON.stringify(prefs))
	} catch {
		// ignore storage errors (quota, etc)
	}
}

function hasValue(value: unknown): boolean {
	return value !== undefined && value !== null
}

function hasWallpaperOverride(preferences: UserClientPreferences | null | undefined): boolean {
	const appearance = preferences?.appearance
	if (!appearance) return false
	return (
		hasValue(appearance.autoBackground) ||
		hasValue(appearance.background) ||
		hasValue(appearance.staticColor)
	)
}

function hasThemeModeOverride(preferences: UserClientPreferences | null | undefined): boolean {
	return hasValue(preferences?.appearance?.themeMode)
}

function hasBubbleTailOverride(preferences: UserClientPreferences | null | undefined): boolean {
	return hasValue(preferences?.appearance?.bubbleTailStyle)
}

function hasBubbleAnimationOverride(
	preferences: UserClientPreferences | null | undefined
): boolean {
	return hasValue(preferences?.appearance?.bubbleAnimation)
}

function hasHapticFeedbackOverride(preferences: UserClientPreferences | null | undefined): boolean {
	return hasValue(preferences?.accessibility?.hapticFeedback)
}

function hasExperimentalUiOverride(preferences: UserClientPreferences | null | undefined): boolean {
	const advanced = preferences?.advanced
	if (!advanced) return false
	return (
		hasValue(advanced.svgLiquidGlass) ||
		hasValue(advanced.svgLiquidGlassIsland) ||
		hasValue(advanced.svgLiquidMetal)
	)
}

function withAppearancePreferences(
	preferences: UserClientPreferences,
	appearance: AppearancePreferences
): UserClientPreferences {
	const nextPreferences: UserClientPreferences = { ...preferences }
	if (Object.keys(appearance).length > 0) {
		nextPreferences.appearance = appearance
	} else {
		delete nextPreferences.appearance
	}
	return nextPreferences
}

function withAccessibilityPreferences(
	preferences: UserClientPreferences,
	accessibility: AccessibilityPreferences
): UserClientPreferences {
	const nextPreferences: UserClientPreferences = { ...preferences }
	if (Object.keys(accessibility).length > 0) {
		nextPreferences.accessibility = accessibility
	} else {
		delete nextPreferences.accessibility
	}
	return nextPreferences
}

function withAdvancedPreferences(
	preferences: UserClientPreferences,
	advanced: AdvancedPreferences
): UserClientPreferences {
	const nextPreferences: UserClientPreferences = { ...preferences }
	if (Object.keys(advanced).length > 0) {
		nextPreferences.advanced = advanced
	} else {
		delete nextPreferences.advanced
	}
	return nextPreferences
}

function removeWallpaperOverrides(preferences: UserClientPreferences): UserClientPreferences {
	const appearance = preferences.appearance
	if (!appearance) return preferences

	const nextAppearance: AppearancePreferences = {}
	if (hasValue(appearance.themeMode)) nextAppearance.themeMode = appearance.themeMode
	if (hasValue(appearance.accent)) nextAppearance.accent = appearance.accent
	if (hasValue(appearance.autoAccentColors)) {
		nextAppearance.autoAccentColors = appearance.autoAccentColors
	}
	if (hasValue(appearance.bubbleTailStyle)) {
		nextAppearance.bubbleTailStyle = appearance.bubbleTailStyle
	}
	if (hasValue(appearance.bubbleAnimation)) {
		nextAppearance.bubbleAnimation = appearance.bubbleAnimation
	}

	return withAppearancePreferences(preferences, nextAppearance)
}

function removeThemeModeOverride(preferences: UserClientPreferences): UserClientPreferences {
	const appearance = preferences.appearance
	if (!appearance) return preferences

	const nextAppearance: AppearancePreferences = {}
	if (hasValue(appearance.accent)) nextAppearance.accent = appearance.accent
	if (hasValue(appearance.autoAccentColors)) {
		nextAppearance.autoAccentColors = appearance.autoAccentColors
	}
	if (hasValue(appearance.autoBackground)) {
		nextAppearance.autoBackground = appearance.autoBackground
	}
	if (hasValue(appearance.background)) nextAppearance.background = appearance.background
	if (hasValue(appearance.staticColor)) nextAppearance.staticColor = appearance.staticColor
	if (hasValue(appearance.bubbleTailStyle)) {
		nextAppearance.bubbleTailStyle = appearance.bubbleTailStyle
	}
	if (hasValue(appearance.bubbleAnimation)) {
		nextAppearance.bubbleAnimation = appearance.bubbleAnimation
	}

	return withAppearancePreferences(preferences, nextAppearance)
}

function removeBubbleTailOverride(preferences: UserClientPreferences): UserClientPreferences {
	const appearance = preferences.appearance
	if (!appearance) return preferences

	const nextAppearance: AppearancePreferences = {}
	if (hasValue(appearance.themeMode)) nextAppearance.themeMode = appearance.themeMode
	if (hasValue(appearance.accent)) nextAppearance.accent = appearance.accent
	if (hasValue(appearance.autoAccentColors)) {
		nextAppearance.autoAccentColors = appearance.autoAccentColors
	}
	if (hasValue(appearance.autoBackground)) {
		nextAppearance.autoBackground = appearance.autoBackground
	}
	if (hasValue(appearance.background)) nextAppearance.background = appearance.background
	if (hasValue(appearance.staticColor)) nextAppearance.staticColor = appearance.staticColor
	if (hasValue(appearance.bubbleAnimation)) {
		nextAppearance.bubbleAnimation = appearance.bubbleAnimation
	}

	return withAppearancePreferences(preferences, nextAppearance)
}

function removeBubbleAnimationOverride(preferences: UserClientPreferences): UserClientPreferences {
	const appearance = preferences.appearance
	if (!appearance) return preferences

	const nextAppearance: AppearancePreferences = {}
	if (hasValue(appearance.themeMode)) nextAppearance.themeMode = appearance.themeMode
	if (hasValue(appearance.accent)) nextAppearance.accent = appearance.accent
	if (hasValue(appearance.autoAccentColors)) {
		nextAppearance.autoAccentColors = appearance.autoAccentColors
	}
	if (hasValue(appearance.autoBackground)) {
		nextAppearance.autoBackground = appearance.autoBackground
	}
	if (hasValue(appearance.background)) nextAppearance.background = appearance.background
	if (hasValue(appearance.staticColor)) nextAppearance.staticColor = appearance.staticColor
	if (hasValue(appearance.bubbleTailStyle)) {
		nextAppearance.bubbleTailStyle = appearance.bubbleTailStyle
	}

	return withAppearancePreferences(preferences, nextAppearance)
}

function removeHapticFeedbackOverride(preferences: UserClientPreferences): UserClientPreferences {
	const accessibility = preferences.accessibility
	if (!accessibility) return preferences

	return withAccessibilityPreferences(preferences, {})
}

function removeExperimentalUiOverrides(preferences: UserClientPreferences): UserClientPreferences {
	const advanced = preferences.advanced
	if (!advanced) return preferences

	return withAdvancedPreferences(preferences, {})
}

function withClientPreferences(client: UserClient, preferences: UserClientPreferences): UserClient {
	return { ...client, preferences }
}

// store

function createPreferencesStore() {
	let raw = $state<UserPreferences>({})
	let loading = $state(false)
	let error = $state<string | null>(null)
	let userId = $state<string | null>(null)

	// defaults: admin settings → hardcoded fallbacks
	const defaults: Resolved = $derived({
		appearance: {
			themeMode: (settingsState?.data?.ui?.default_theme as ThemeMode) ?? 'auto',
			accent: 'purple',
			background:
				(settingsState?.data?.ui?.default_background as BackgroundType) ?? 'lightrays',
			autoAccentColors: true,
			autoBackground: true,
			staticColor: '#171717',
			bubbleTailStyle: 'none',
			bubbleAnimation: 'morph',
		},
		account: {
			bio: null,
			birthDate: null,
			gender: null,
		},
		ai: {
			defaultAgentId: settingsState?.data?.ai?.default_agent_ids?.[0] ?? null,
			bio: null,
			useAccountBio: false,
			memoriesEnabled: true,
			chatRecall: true,
			customInstructions: null,
			personality: null,
		},
		notifications: {
			enabled: true,
			sound: true,
			pushEnabled: true,
		},
		privacy: {
			saveHistory: true,
			shareUsageData: false,
			useLocation: false,
			useDeviceContext: true,
			useBatteryStatus: false,
		},
		accessibility: {
			hapticFeedback: true,
		},
		advanced: {
			svgLiquidGlass: false,
			svgLiquidGlassIsland: false,
			svgLiquidMetal: false,
		},
		debug: {
			enableDebugApps: false,
		},
		homepage: {
			chats: true,
			reminders: true,
			notes: true,
			projects: true,
			friends: true,
			library: true,
			calendar: true,
		},
	})

	const clientPreferences: UserClientPreferences = $derived(userClient.current?.preferences ?? {})

	// user preferences → defaults (which already include admin settings)
	const syncedData: Resolved = $derived(
		deepMerge(structuredClone(defaults), raw as Partial<Resolved>)
	)
	const data: Resolved = $derived(
		deepMerge(structuredClone(syncedData), clientPreferences as Partial<Resolved>)
	)
	const themeScope: ClientPreferenceScope = $derived(
		hasThemeModeOverride(clientPreferences) ? 'client' : 'synced'
	)
	const wallpaperScope: ClientPreferenceScope = $derived(
		hasWallpaperOverride(clientPreferences) ? 'client' : 'synced'
	)
	const bubbleTailScope: ClientPreferenceScope = $derived(
		hasBubbleTailOverride(clientPreferences) ? 'client' : 'synced'
	)
	const bubbleAnimationScope: ClientPreferenceScope = $derived(
		hasBubbleAnimationOverride(clientPreferences) ? 'client' : 'synced'
	)
	const hapticFeedbackScope: ClientPreferenceScope = $derived(
		hasHapticFeedbackOverride(clientPreferences) ? 'client' : 'synced'
	)
	const experimentalUiScope: ClientPreferenceScope = $derived(
		hasExperimentalUiOverride(clientPreferences) ? 'client' : 'synced'
	)
	const useSvgLiquidGlass = $derived.by(
		() => device.isChromium && (data.advanced.svgLiquidGlass ?? false)
	)
	const useSvgLiquidGlassIsland = $derived.by(
		() => device.isChromium && (data.advanced.svgLiquidGlassIsland ?? false)
	)
	const useSvgLiquidMetal = $derived.by(
		() => device.isChromium && (data.advanced.svgLiquidMetal ?? false)
	)

	// event stream integration

	let prefsUnsub: (() => void) | null = null
	let syncCleanup: (() => void) | null = null

	function handlePreferencesEvent(message: StreamMessage): void {
		const eventData = storeEventData(message)
		if (message.type === 'user_client.preferences_updated') {
			const clientId = eventData?.client_id
			const incoming = eventData?.preferences as UserClientPreferences | undefined
			const currentClient = userClient.current
			if (!incoming || !currentClient || clientId !== currentClient.id) return
			userClient.current = withClientPreferences(currentClient, incoming)
			return
		}

		const incoming = eventData?.preferences as UserPreferences | undefined
		if (!incoming || !userId) return

		raw = incoming
		writeStorage(userId, incoming)

		// keep session.currentUser in sync
		if (session.currentUser) {
			session.currentUser = { ...session.currentUser, preferences: incoming }
		}
	}

	// auto-sync with session

	function startSync(): () => void {
		// immediately hydrate from the current user if available.
		// $effect is scheduled (deferred), so without this the splash would
		// fade before preferences are applied, causing a visual pop.
		const user = session.currentUser
		if (user && userId !== user.id) {
			userId = user.id
			let stored = readStorage(user.id)
			if (user.preferences) {
				stored = user.preferences
				writeStorage(user.id, stored)
			}
			raw = stored
		}

		if (syncCleanup) return syncCleanup

		// $effect.root lets us run effects outside component context
		const cleanupEffect = $effect.root(() => {
			$effect(() => {
				const user = session.currentUser

				if (!user) {
					raw = {}
					userId = null
					error = null
					return
				}

				// user changed
				if (userId !== user.id) {
					userId = user.id

					// instant hydrate from localStorage
					let stored = readStorage(user.id)

					// session preferences override
					if (user.preferences) {
						stored = user.preferences
						writeStorage(user.id, stored)
					}

					raw = stored
				}
			})
		})

		// subscribe to event stream for cross-session preference updates
		if (!prefsUnsub) {
			prefsUnsub = subscribeToStoreEvents(
				STORE_EVENT_TYPES.preferences,
				handlePreferencesEvent
			)
		}

		let cleanupActive = true
		const cleanupSync = () => {
			if (!cleanupActive) return
			cleanupActive = false
			cleanupEffect()
			prefsUnsub?.()
			prefsUnsub = null
			if (syncCleanup === cleanupSync) syncCleanup = null
		}
		syncCleanup = cleanupSync

		return syncCleanup
	}

	// api

	async function refresh(): Promise<void> {
		const uid = userId
		if (!uid) return

		loading = true
		error = null

		try {
			const { data: res, error: err } = await api.GET('/v1/users/{user_id}', {
				params: { path: { user_id: uid } },
			})

			if (err || !res) {
				error = 'could not load preferences'
				return
			}

			const fetched = (res.preferences ?? {}) as UserPreferences
			raw = fetched
			writeStorage(uid, fetched)
			session.currentUser = { ...res }
		} finally {
			loading = false
		}
	}

	async function update<K extends keyof Resolved>(
		section: K,
		updates: Partial<Resolved[K]>
	): Promise<boolean> {
		const uid = userId
		if (!uid) return false

		// snapshot for rollback
		const prevRaw = raw

		// optimistic
		const nextRaw: UserPreferences = { ...raw }
		const nextSection: Record<string, unknown> = { ...(raw[section] ?? {}) }
		for (const [key, value] of Object.entries(updates)) {
			if (value === undefined) delete nextSection[key]
			else nextSection[key] = value
		}
		if (Object.keys(nextSection).length > 0) {
			nextRaw[section] = nextSection as UserPreferences[typeof section]
		} else {
			delete nextRaw[section]
		}
		raw = nextRaw
		writeStorage(uid, nextRaw)
		error = null

		const { error: err } = await api.PATCH('/v1/users/{user_id}', {
			params: { path: { user_id: uid } },
			body: { preferences: nextRaw },
		})

		if (err) {
			// rollback
			raw = prevRaw
			writeStorage(uid, prevRaw)
			error = 'could not save preferences'
			return false
		}

		// WS event delivers authoritative state
		return true
	}

	async function saveClientPreferences(nextPreferences: UserClientPreferences): Promise<boolean> {
		const uid = userId
		if (!uid) return false

		const currentClient = userClient.current ?? (await ensureUserClient())
		if (!currentClient) return false

		const previousClient = userClient.current
		userClient.current = withClientPreferences(currentClient, nextPreferences)
		error = null

		const { data: res, error: err } = await api.PUT(
			'/v1/users/{user_id}/clients/{client_id}/preferences',
			{
				params: { path: { user_id: uid, client_id: currentClient.id } },
				body: nextPreferences,
			}
		)

		if (err || !res) {
			userClient.current = previousClient
			error = 'could not save preferences'
			return false
		}

		userClient.current = res
		return true
	}

	async function updateClientAppearance(
		updates: Partial<AppearancePreferences>
	): Promise<boolean> {
		const currentPreferences = userClient.current?.preferences ?? {}
		const nextPreferences: UserClientPreferences = {
			...currentPreferences,
			appearance: {
				...(currentPreferences.appearance ?? {}),
				...updates,
			},
		}
		return await saveClientPreferences(nextPreferences)
	}

	async function updateClientAccessibility(
		updates: Partial<AccessibilityPreferences>
	): Promise<boolean> {
		const currentPreferences = userClient.current?.preferences ?? {}
		const nextPreferences: UserClientPreferences = {
			...currentPreferences,
			accessibility: {
				...(currentPreferences.accessibility ?? {}),
				...updates,
			},
		}
		return await saveClientPreferences(nextPreferences)
	}

	async function updateClientAdvanced(updates: Partial<AdvancedPreferences>): Promise<boolean> {
		const currentPreferences = userClient.current?.preferences ?? {}
		const nextPreferences: UserClientPreferences = {
			...currentPreferences,
			advanced: {
				...(currentPreferences.advanced ?? {}),
				...updates,
			},
		}
		return await saveClientPreferences(nextPreferences)
	}

	async function setThemeScope(scope: ClientPreferenceScope): Promise<boolean> {
		if (scope === themeScope) return true
		if (scope === 'client') {
			return await updateClientAppearance({ themeMode: data.appearance.themeMode })
		}

		const currentPreferences = userClient.current?.preferences ?? {}
		return await saveClientPreferences(removeThemeModeOverride(currentPreferences))
	}

	async function updateThemeMode(themeMode: ThemeMode): Promise<boolean> {
		if (themeScope === 'client') {
			return await updateClientAppearance({ themeMode })
		}
		return await update('appearance', { themeMode })
	}

	async function setWallpaperScope(scope: WallpaperPreferenceScope): Promise<boolean> {
		if (scope === wallpaperScope) return true
		if (scope === 'client') {
			return await updateClientAppearance({
				autoBackground: data.appearance.autoBackground,
				background: data.appearance.background,
				staticColor: data.appearance.staticColor,
			})
		}

		const currentPreferences = userClient.current?.preferences ?? {}
		return await saveClientPreferences(removeWallpaperOverrides(currentPreferences))
	}

	async function updateWallpaper(updates: Partial<WallpaperPreferenceUpdates>): Promise<boolean> {
		if (wallpaperScope === 'client') {
			return await updateClientAppearance(updates)
		}
		return await update('appearance', updates)
	}

	async function setBubbleTailScope(scope: ClientPreferenceScope): Promise<boolean> {
		if (scope === bubbleTailScope) return true
		if (scope === 'client') {
			return await updateClientAppearance({
				bubbleTailStyle: data.appearance.bubbleTailStyle,
			})
		}

		const currentPreferences = userClient.current?.preferences ?? {}
		return await saveClientPreferences(removeBubbleTailOverride(currentPreferences))
	}

	async function updateBubbleTailStyle(bubbleTailStyle: BubbleTailStyle): Promise<boolean> {
		if (bubbleTailScope === 'client') {
			return await updateClientAppearance({ bubbleTailStyle })
		}
		return await update('appearance', { bubbleTailStyle })
	}

	async function setBubbleAnimationScope(scope: ClientPreferenceScope): Promise<boolean> {
		if (scope === bubbleAnimationScope) return true
		if (scope === 'client') {
			return await updateClientAppearance({
				bubbleAnimation: data.appearance.bubbleAnimation,
			})
		}

		const currentPreferences = userClient.current?.preferences ?? {}
		return await saveClientPreferences(removeBubbleAnimationOverride(currentPreferences))
	}

	async function updateBubbleAnimation(bubbleAnimation: BubbleAnimation): Promise<boolean> {
		if (bubbleAnimationScope === 'client') {
			return await updateClientAppearance({ bubbleAnimation })
		}
		return await update('appearance', { bubbleAnimation })
	}

	async function setHapticFeedbackScope(scope: ClientPreferenceScope): Promise<boolean> {
		if (scope === hapticFeedbackScope) return true
		if (scope === 'client') {
			return await updateClientAccessibility({
				hapticFeedback: data.accessibility.hapticFeedback,
			})
		}

		const currentPreferences = userClient.current?.preferences ?? {}
		return await saveClientPreferences(removeHapticFeedbackOverride(currentPreferences))
	}

	async function updateHapticFeedback(hapticFeedback: boolean): Promise<boolean> {
		if (hapticFeedbackScope === 'client') {
			return await updateClientAccessibility({ hapticFeedback })
		}
		return await update('accessibility', { hapticFeedback })
	}

	async function setExperimentalUiScope(scope: ClientPreferenceScope): Promise<boolean> {
		if (scope === experimentalUiScope) return true
		if (scope === 'client') {
			return await updateClientAdvanced({
				svgLiquidGlass: data.advanced.svgLiquidGlass,
				svgLiquidGlassIsland: data.advanced.svgLiquidGlassIsland,
				svgLiquidMetal: data.advanced.svgLiquidMetal,
			})
		}

		const currentPreferences = userClient.current?.preferences ?? {}
		return await saveClientPreferences(removeExperimentalUiOverrides(currentPreferences))
	}

	async function updateExperimentalUi(
		updates: Partial<ExperimentalUiPreferenceUpdates>
	): Promise<boolean> {
		if (experimentalUiScope === 'client') {
			return await updateClientAdvanced(updates)
		}
		return await update('advanced', updates)
	}

	return {
		// state (reactive getters)
		get data() {
			return data
		},
		get syncedData() {
			return syncedData
		},
		get themeScope() {
			return themeScope
		},
		get wallpaperScope() {
			return wallpaperScope
		},
		get bubbleTailScope() {
			return bubbleTailScope
		},
		get bubbleAnimationScope() {
			return bubbleAnimationScope
		},
		get hapticFeedbackScope() {
			return hapticFeedbackScope
		},
		get experimentalUiScope() {
			return experimentalUiScope
		},
		get useSvgLiquidGlass() {
			return useSvgLiquidGlass
		},
		get useSvgLiquidGlassIsland() {
			return useSvgLiquidGlassIsland
		},
		get useSvgLiquidMetal() {
			return useSvgLiquidMetal
		},
		get loading() {
			return loading
		},
		get error() {
			return error
		},

		// methods
		startSync,
		refresh,
		update,
		setThemeScope,
		updateThemeMode,
		setWallpaperScope,
		updateWallpaper,
		setBubbleTailScope,
		updateBubbleTailStyle,
		setBubbleAnimationScope,
		updateBubbleAnimation,
		setHapticFeedbackScope,
		updateHapticFeedback,
		setExperimentalUiScope,
		updateExperimentalUi,
	}
}

export const preferences = createPreferencesStore()
