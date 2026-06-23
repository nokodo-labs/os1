<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { api, unwrap, type Schemas } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Switch } from '$lib/components/ui/switch'
	import { Textarea } from '$lib/components/ui/textarea'
	import {
		Ban,
		Brain,
		CalendarDays,
		CheckCircle,
		Circle,
		CircleX,
		Edit3,
		Eye,
		FileIcon,
		FileText,
		FolderKanban,
		Inbox,
		KeyRound,
		ListChecks,
		LockKeyhole,
		Mail,
		MessageSquare,
		Pencil,
		RefreshCw,
		Save,
		Shield,
		SlidersHorizontal,
		Smartphone,
		Trash2,
		User as UserIcon,
		Users,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type User = Schemas['User']
	type UserClient = Schemas['UserClient']
	type UserClientPreferences = Schemas['UserClientPreferences']
	type FriendResponse = Schemas['FriendResponse']
	type FriendshipDetail = Schemas['FriendshipDetail']
	type BlockDetail = Schemas['BlockDetail']
	type PushSubscription = Schemas['NotificationPushSubscription']
	type UserPermissions = Schemas['UserPermissions']
	type UserPrivacy = Schemas['UserPrivacy']
	type Visibility = Schemas['Visibility']

	type Props = {
		open: boolean
		userId: string | null
		onClose?: () => void
		onUpdated?: (user: User) => void
		onDeleted?: (userId: string) => void
	}

	type SectionKey =
		| 'overview'
		| 'profile'
		| 'account'
		| 'clients'
		| 'social'
		| 'permissions'
		| 'preferences'
	type ResourceRoute =
		| '/threads'
		| '/memories'
		| '/notes'
		| '/files'
		| '/groups'
		| '/reminders'
		| '/projects'
		| '/calendars'
		| '/tasks'
	type PrivacyField =
		| 'online_status'
		| 'profile_picture'
		| 'real_name'
		| 'bio'
		| 'email'
		| 'gender'
		| 'birth_date'
		| 'allow_dms'
		| 'allow_friend_requests'

	type UserCounts = {
		threads?: number
		memories?: number
		notes?: number
		files?: number
		groups?: number
		reminder_lists?: number
		projects?: number
		calendars?: number
		tasks?: number
	}

	type ClientSubscriptionGroup = {
		clientId: string
		subscriptions: PushSubscription[]
		error: string | null
	}

	let { open = $bindable(false), userId, onClose, onUpdated, onDeleted }: Props = $props()

	let activeSection = $state<SectionKey>('overview')
	let user = $state<User | null>(null)
	let counts = $state<UserCounts>({})
	let countsLoadedForUserId = $state<string | null>(null)
	let permissions = $state<UserPermissions | null>(null)
	let clients = $state<UserClient[]>([])
	let clientSubscriptions = $state<ClientSubscriptionGroup[]>([])
	let friends = $state<FriendResponse[]>([])
	let incomingRequests = $state<FriendshipDetail[]>([])
	let outgoingRequests = $state<FriendshipDetail[]>([])
	let blocks = $state<BlockDetail[]>([])
	let isLoading = $state(false)
	let loadError = $state<string | null>(null)
	let reloadToken = $state(0)

	let isEditing = $state(false)
	let editDisplayName = $state('')
	let editUsername = $state('')
	let editEmail = $state('')
	let editBio = $state('')
	let editAvatarUrl = $state('')
	let editIsActive = $state(true)
	let editIsSuperuser = $state(false)
	let editFindByEmail = $state(false)
	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let saveSuccess = $state(false)

	let prefsExpanded = $state(false)
	let prefsText = $state('')
	let prefsError = $state<string | null>(null)
	let isSavingPrefs = $state(false)
	let prefsSaveSuccess = $state(false)

	let editingClientId = $state<string | null>(null)
	let clientNameText = $state('')
	let clientInfoText = $state('{}')
	let clientPrefsText = $state('{}')
	let clientError = $state<string | null>(null)
	let isSavingClient = $state(false)
	let deletingClientId = $state<string | null>(null)
	let deletingSubscriptionId = $state<string | null>(null)
	let socialError = $state<string | null>(null)
	let socialBusyId = $state<string | null>(null)

	let privacyOnlineStatus = $state<Visibility>('friends')
	let privacyProfilePicture = $state<Visibility>('everyone')
	let privacyRealName = $state<Visibility>('friends')
	let privacyBio = $state<Visibility>('everyone')
	let privacyEmail = $state<Visibility>('private')
	let privacyGender = $state<Visibility>('friends')
	let privacyBirthDate = $state<Visibility>('friends')
	let privacyAllowDms = $state<Visibility>('friends')
	let privacyAllowFriendRequests = $state<Visibility>('everyone')
	let isSavingPrivacy = $state(false)
	let privacyError = $state<string | null>(null)
	let privacySaveSuccess = $state(false)
	let isSavingAccount = $state(false)
	let accountError = $state<string | null>(null)
	let accountSaveSuccess = $state(false)
	let isDeletingUser = $state(false)
	let deleteUserError = $state<string | null>(null)
	let confirmDeleteUser = $state(false)
	const isViewingSelf = $derived(Boolean(user && auth.user?.id === user.id))

	const sections: Array<{ key: SectionKey; label: string; icon: typeof UserIcon }> = [
		{ key: 'overview', label: 'overview', icon: UserIcon },
		{ key: 'profile', label: 'profile', icon: Pencil },
		{ key: 'account', label: 'account', icon: LockKeyhole },
		{ key: 'clients', label: 'clients', icon: Smartphone },
		{ key: 'social', label: 'social', icon: Users },
		{ key: 'permissions', label: 'permissions', icon: KeyRound },
		{ key: 'preferences', label: 'preferences', icon: SlidersHorizontal },
	]

	const visibilityOptions: Visibility[] = ['everyone', 'friends', 'private']

	const privacyFields: Array<{ key: PrivacyField; label: string }> = [
		{ key: 'online_status', label: 'online status' },
		{ key: 'profile_picture', label: 'profile picture' },
		{ key: 'real_name', label: 'real name' },
		{ key: 'bio', label: 'bio' },
		{ key: 'email', label: 'email' },
		{ key: 'gender', label: 'gender' },
		{ key: 'birth_date', label: 'birth date' },
		{ key: 'allow_dms', label: 'allow DMs' },
		{ key: 'allow_friend_requests', label: 'allow friend requests' },
	]

	const resourceActions = $derived([
		{
			key: 'threads',
			label: 'threads',
			icon: MessageSquare,
			route: '/threads' as ResourceRoute,
			count: counts.threads,
		},
		{
			key: 'memories',
			label: 'memories',
			icon: Brain,
			route: '/memories' as ResourceRoute,
			count: counts.memories,
		},
		{
			key: 'notes',
			label: 'notes',
			icon: FileText,
			route: '/notes' as ResourceRoute,
			count: counts.notes,
		},
		{
			key: 'files',
			label: 'files',
			icon: FileIcon,
			route: '/files' as ResourceRoute,
			count: counts.files,
		},
		{
			key: 'groups',
			label: 'groups',
			icon: Users,
			route: '/groups' as ResourceRoute,
			count: counts.groups,
		},
		{
			key: 'reminders',
			label: 'reminder lists',
			icon: ListChecks,
			route: '/reminders' as ResourceRoute,
			count: counts.reminder_lists,
		},
		{
			key: 'projects',
			label: 'projects',
			icon: FolderKanban,
			route: '/projects' as ResourceRoute,
			count: counts.projects,
		},
		{
			key: 'calendars',
			label: 'calendars',
			icon: CalendarDays,
			route: '/calendars' as ResourceRoute,
			count: counts.calendars,
		},
		{
			key: 'tasks',
			label: 'tasks',
			icon: CheckCircle,
			route: '/tasks' as ResourceRoute,
			count: counts.tasks,
		},
	])

	function close() {
		open = false
		activeSection = 'overview'
		isEditing = false
		prefsExpanded = false
		editingClientId = null
		saveError = null
		clientError = null
		socialError = null
		accountError = null
		accountSaveSuccess = false
		deleteUserError = null
		confirmDeleteUser = false
		onClose?.()
	}

	function openResource(route: ResourceRoute, uid: string) {
		void goto(resolve(`${route}?user=${encodeURIComponent(uid)}`))
		close()
	}

	function openCurrentUserResource(route: ResourceRoute) {
		if (!user) return
		openResource(route, user.id)
	}

	function refresh() {
		reloadToken += 1
	}

	function formatDate(value: string | null | undefined): string {
		if (!value) return 'never'
		const date = new Date(value)
		if (Number.isNaN(date.getTime())) return 'unknown'
		return date.toLocaleString()
	}

	function formatJson(value: unknown): string {
		return JSON.stringify(value ?? {}, null, 2)
	}

	function countValue(value: number | undefined): number {
		return typeof value === 'number' ? value : 0
	}

	function parseVisibility(value: string): Visibility {
		if (value === 'everyone' || value === 'friends' || value === 'private') return value
		return 'private'
	}

	function normalizePrivacy(privacy: UserPrivacy | null | undefined): UserPrivacy {
		return {
			online_status: privacy?.online_status ?? 'friends',
			profile_picture: privacy?.profile_picture ?? 'everyone',
			real_name: privacy?.real_name ?? 'friends',
			bio: privacy?.bio ?? 'everyone',
			email: privacy?.email ?? 'private',
			gender: privacy?.gender ?? 'friends',
			birth_date: privacy?.birth_date ?? 'friends',
			allow_dms: privacy?.allow_dms ?? 'friends',
			allow_friend_requests: privacy?.allow_friend_requests ?? 'everyone',
		}
	}

	function syncPrivacyForm(privacy: UserPrivacy | null | undefined) {
		const normalized = normalizePrivacy(privacy)
		privacyOnlineStatus = normalized.online_status
		privacyProfilePicture = normalized.profile_picture
		privacyRealName = normalized.real_name
		privacyBio = normalized.bio
		privacyEmail = normalized.email
		privacyGender = normalized.gender
		privacyBirthDate = normalized.birth_date
		privacyAllowDms = normalized.allow_dms
		privacyAllowFriendRequests = normalized.allow_friend_requests
	}

	function syncAccountForm(value: User) {
		editIsActive = value.is_active !== false
		editIsSuperuser = value.is_superuser
		editFindByEmail = value.find_by_email
	}

	function currentPrivacy(): UserPrivacy {
		return {
			online_status: privacyOnlineStatus,
			profile_picture: privacyProfilePicture,
			real_name: privacyRealName,
			bio: privacyBio,
			email: privacyEmail,
			gender: privacyGender,
			birth_date: privacyBirthDate,
			allow_dms: privacyAllowDms,
			allow_friend_requests: privacyAllowFriendRequests,
		}
	}

	function privacyValue(field: PrivacyField): Visibility {
		switch (field) {
			case 'online_status':
				return privacyOnlineStatus
			case 'profile_picture':
				return privacyProfilePicture
			case 'real_name':
				return privacyRealName
			case 'bio':
				return privacyBio
			case 'email':
				return privacyEmail
			case 'gender':
				return privacyGender
			case 'birth_date':
				return privacyBirthDate
			case 'allow_dms':
				return privacyAllowDms
			case 'allow_friend_requests':
				return privacyAllowFriendRequests
		}
		return 'private'
	}

	function setPrivacyValue(field: PrivacyField, value: Visibility) {
		switch (field) {
			case 'online_status':
				privacyOnlineStatus = value
				break
			case 'profile_picture':
				privacyProfilePicture = value
				break
			case 'real_name':
				privacyRealName = value
				break
			case 'bio':
				privacyBio = value
				break
			case 'email':
				privacyEmail = value
				break
			case 'gender':
				privacyGender = value
				break
			case 'birth_date':
				privacyBirthDate = value
				break
			case 'allow_dms':
				privacyAllowDms = value
				break
			case 'allow_friend_requests':
				privacyAllowFriendRequests = value
				break
		}
	}

	function userLabel(
		value: User | FriendResponse | null | undefined,
		fallbackId: string
	): string {
		if (!value) return fallbackId
		return value.display_name || value.username || value.email || fallbackId
	}

	function requestUser(
		request: FriendshipDetail,
		direction: 'incoming' | 'outgoing'
	): User | null {
		return direction === 'incoming' ? (request.requester ?? null) : (request.addressee ?? null)
	}

	function subscriptionGroup(clientId: string): ClientSubscriptionGroup | null {
		return clientSubscriptions.find((group) => group.clientId === clientId) ?? null
	}

	function clientPushError(clientId: string): string | null {
		return subscriptionGroup(clientId)?.error ?? null
	}

	function clientPushSubscriptions(clientId: string): PushSubscription[] {
		return subscriptionGroup(clientId)?.subscriptions ?? []
	}

	function startEdit() {
		if (!user) return
		editDisplayName = user.display_name ?? ''
		editUsername = user.username
		editEmail = user.email
		editBio = user.bio ?? ''
		editAvatarUrl = user.avatar_url ?? ''
		isEditing = true
		saveError = null
	}

	function cancelEdit() {
		isEditing = false
		saveError = null
	}

	async function saveUser() {
		if (!user) return
		isSaving = true
		saveError = null
		saveSuccess = false
		try {
			const r = await api.PATCH('/v1/users/{user_id}', {
				params: { path: { user_id: user.id } },
				body: {
					display_name: editDisplayName.trim() || null,
					username: editUsername.trim() || undefined,
					email: editEmail.trim() || undefined,
					bio: editBio.trim() || null,
					avatar_url: editAvatarUrl.trim() || null,
				},
			})
			const updated = unwrap(r)
			user = updated
			syncAccountForm(updated)
			isEditing = false
			saveSuccess = true
			onUpdated?.(updated)
			setTimeout(() => (saveSuccess = false), 2000)
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'failed to save user'
		} finally {
			isSaving = false
		}
	}

	async function saveAccount() {
		if (!user) return
		isSavingAccount = true
		accountError = null
		accountSaveSuccess = false
		try {
			const r = await api.PATCH('/v1/users/{user_id}', {
				params: { path: { user_id: user.id } },
				body: {
					is_active: editIsActive,
					is_superuser: editIsSuperuser,
				},
			})
			const updated = unwrap(r)
			user = updated
			syncAccountForm(updated)
			accountSaveSuccess = true
			onUpdated?.(updated)
			setTimeout(() => (accountSaveSuccess = false), 2000)
		} catch (e) {
			accountError = e instanceof Error ? e.message : 'failed to save account'
		} finally {
			isSavingAccount = false
		}
	}

	async function deleteCurrentUser() {
		if (!user || isViewingSelf) return
		isDeletingUser = true
		deleteUserError = null
		try {
			const r = await api.DELETE('/v1/users/{user_id}', {
				params: { path: { user_id: user.id } },
			})
			unwrap(r)
			onDeleted?.(user.id)
			close()
		} catch (e) {
			deleteUserError = e instanceof Error ? e.message : 'failed to delete user'
		} finally {
			isDeletingUser = false
		}
	}

	function openPrefs() {
		if (!user) return
		prefsText = formatJson(user.preferences)
		prefsExpanded = true
		prefsError = null
	}

	async function savePrefs() {
		if (!user) return
		let parsed: unknown
		try {
			parsed = JSON.parse(prefsText)
		} catch {
			prefsError = 'invalid JSON'
			return
		}
		isSavingPrefs = true
		prefsError = null
		prefsSaveSuccess = false
		try {
			const r = await api.PATCH('/v1/users/{user_id}', {
				params: { path: { user_id: user.id } },
				body: { preferences: parsed as Schemas['UserPreferences'] },
			})
			const updated = unwrap(r)
			user = updated
			prefsSaveSuccess = true
			onUpdated?.(updated)
			setTimeout(() => (prefsSaveSuccess = false), 2000)
		} catch (e) {
			prefsError = e instanceof Error ? e.message : 'failed to save preferences'
		} finally {
			isSavingPrefs = false
		}
	}

	async function savePrivacy() {
		if (!user) return
		isSavingPrivacy = true
		privacyError = null
		privacySaveSuccess = false
		try {
			const r = await api.PATCH('/v1/users/{user_id}', {
				params: { path: { user_id: user.id } },
				body: { privacy: currentPrivacy(), find_by_email: editFindByEmail },
			})
			const updated = unwrap(r)
			user = updated
			syncPrivacyForm(updated.privacy)
			syncAccountForm(updated)
			privacySaveSuccess = true
			onUpdated?.(updated)
			setTimeout(() => (privacySaveSuccess = false), 2000)
		} catch (e) {
			privacyError = e instanceof Error ? e.message : 'failed to save privacy'
		} finally {
			isSavingPrivacy = false
		}
	}

	async function loadCounts(uid: string) {
		const [
			threadResult,
			memoryResult,
			noteResult,
			fileResult,
			groupResult,
			reminderListResult,
			projectResult,
			calendarResult,
			taskResult,
		] = await Promise.all([
			api.GET('/v1/threads/count', { params: { query: { owner_id: uid } } }),
			api.GET('/v1/memories/count', { params: { query: { owner_id: uid } } }),
			api.GET('/v1/notes/count', { params: { query: { owner_id: uid } } }),
			api.GET('/v1/files/count', { params: { query: { owner_id: uid } } }),
			api.GET('/v1/groups/count', { params: { query: { owner_id: uid } } }),
			api.GET('/v1/reminder-lists/count', { params: { query: { owner_id: uid } } }),
			api.GET('/v1/projects/count', { params: { query: { owner_id: uid } } }),
			api.GET('/v1/calendars/count', { params: { query: { owner_id: uid } } }),
			api.GET('/v1/tasks/count', { params: { query: { owner_id: uid } } }),
		])

		counts = {
			threads: countValue(threadResult.data),
			memories: countValue(memoryResult.data),
			notes: countValue(noteResult.data),
			files: fileResult.data?.total ?? 0,
			groups: countValue(groupResult.data),
			reminder_lists: countValue(reminderListResult.data),
			projects: countValue(projectResult.data),
			calendars: countValue(calendarResult.data),
			tasks: countValue(taskResult.data),
		}
	}

	async function loadClients(uid: string) {
		const result = await api.GET('/v1/users/{user_id}/clients', {
			params: { path: { user_id: uid } },
		})
		const loadedClients = unwrap(result)
		clients = loadedClients
		clientSubscriptions = await Promise.all(
			loadedClients.map(async (client) => {
				try {
					const subscriptions = await api.GET(
						'/v1/users/{user_id}/clients/{client_id}/push-subscriptions',
						{
							params: { path: { user_id: uid, client_id: client.id } },
						}
					)
					return {
						clientId: client.id,
						subscriptions: subscriptions.data ?? [],
						error: null,
					}
				} catch (e) {
					return {
						clientId: client.id,
						subscriptions: [],
						error: e instanceof Error ? e.message : 'failed to load push subscriptions',
					}
				}
			})
		)
	}

	async function loadSocial(uid: string) {
		const [friendResult, incomingResult, outgoingResult, blockResult] = await Promise.all([
			api.GET('/v1/users/{user_id}/friends', { params: { path: { user_id: uid } } }),
			api.GET('/v1/users/{user_id}/friends/requests/incoming', {
				params: { path: { user_id: uid } },
			}),
			api.GET('/v1/users/{user_id}/friends/requests/outgoing', {
				params: { path: { user_id: uid } },
			}),
			api.GET('/v1/users/{user_id}/blocks', {
				params: { path: { user_id: uid } },
			}),
		])
		friends = friendResult.data ?? []
		incomingRequests = incomingResult.data ?? []
		outgoingRequests = outgoingResult.data ?? []
		blocks = blockResult.data ?? []
	}

	async function loadDetails(uid: string) {
		const [userResult, permissionsResult] = await Promise.all([
			api.GET('/v1/users/{user_id}', { params: { path: { user_id: uid } } }),
			api.GET('/v1/users/{user_id}/permissions', { params: { path: { user_id: uid } } }),
			loadClients(uid),
			loadSocial(uid),
		])
		const loadedUser = unwrap(userResult)
		user = loadedUser
		syncPrivacyForm(loadedUser.privacy)
		syncAccountForm(loadedUser)
		permissions = permissionsResult.data ?? null
	}

	function startClientEdit(client: UserClient) {
		editingClientId = client.id
		clientNameText = client.name ?? ''
		clientInfoText = formatJson(client.info)
		clientPrefsText = formatJson(client.preferences)
		clientError = null
	}

	function cancelClientEdit() {
		editingClientId = null
		clientError = null
	}

	async function saveClient(client: UserClient) {
		if (!user) return
		let parsedInfo: unknown
		let parsedPrefs: unknown
		try {
			parsedInfo = JSON.parse(clientInfoText)
			parsedPrefs = JSON.parse(clientPrefsText)
		} catch {
			clientError = 'invalid JSON'
			return
		}

		isSavingClient = true
		clientError = null
		try {
			await api.PATCH('/v1/users/{user_id}/clients/{client_id}', {
				params: { path: { user_id: user.id, client_id: client.id } },
				body: {
					name: clientNameText.trim() || null,
					info: parsedInfo as Schemas['JSONObject-Input'],
				},
			})
			await api.PUT('/v1/users/{user_id}/clients/{client_id}/preferences', {
				params: { path: { user_id: user.id, client_id: client.id } },
				body: parsedPrefs as UserClientPreferences,
			})
			editingClientId = null
			await loadClients(user.id)
			countsLoadedForUserId = null
		} catch (e) {
			clientError = e instanceof Error ? e.message : 'failed to save client'
		} finally {
			isSavingClient = false
		}
	}

	async function deleteClient(client: UserClient) {
		if (!user) return
		if (!window.confirm('delete this user client and its push subscriptions?')) return
		deletingClientId = client.id
		clientError = null
		try {
			await api.DELETE('/v1/users/{user_id}/clients/{client_id}', {
				params: { path: { user_id: user.id, client_id: client.id } },
			})
			await loadClients(user.id)
			countsLoadedForUserId = null
		} catch (e) {
			clientError = e instanceof Error ? e.message : 'failed to delete client'
		} finally {
			deletingClientId = null
		}
	}

	async function deletePushSubscription(client: UserClient, subscription: PushSubscription) {
		if (!user) return
		if (!window.confirm('delete this push subscription?')) return
		deletingSubscriptionId = subscription.id
		clientError = null
		try {
			await api.DELETE(
				'/v1/users/{user_id}/clients/{client_id}/push-subscriptions/{subscription_id}',
				{
					params: {
						path: {
							user_id: user.id,
							client_id: client.id,
							subscription_id: subscription.id,
						},
					},
				}
			)
			await loadClients(user.id)
		} catch (e) {
			clientError = e instanceof Error ? e.message : 'failed to delete subscription'
		} finally {
			deletingSubscriptionId = null
		}
	}

	async function runSocialAction(id: string, action: () => Promise<void>) {
		if (!user) return
		socialBusyId = id
		socialError = null
		accountError = null
		accountSaveSuccess = false
		deleteUserError = null
		confirmDeleteUser = false
		try {
			await action()
			await loadSocial(user.id)
			countsLoadedForUserId = null
		} catch (e) {
			socialError = e instanceof Error ? e.message : 'failed to update social graph'
		} finally {
			socialBusyId = null
		}
	}

	function acceptRequest(request: FriendshipDetail) {
		if (!user) return
		const uid = user.id
		void runSocialAction(request.id, async () => {
			await api.POST('/v1/users/{user_id}/friends/requests/{friendship_id}/accept', {
				params: { path: { user_id: uid, friendship_id: request.id } },
			})
		})
	}

	function declineRequest(request: FriendshipDetail) {
		if (!user) return
		if (!window.confirm('decline this friend request?')) return
		const uid = user.id
		void runSocialAction(request.id, async () => {
			await api.POST('/v1/users/{user_id}/friends/requests/{friendship_id}/decline', {
				params: { path: { user_id: uid, friendship_id: request.id } },
			})
		})
	}

	function cancelRequest(request: FriendshipDetail) {
		if (!user) return
		if (!window.confirm('cancel this outgoing friend request?')) return
		const uid = user.id
		void runSocialAction(request.id, async () => {
			await api.DELETE('/v1/users/{user_id}/friends/requests/{friendship_id}', {
				params: { path: { user_id: uid, friendship_id: request.id } },
			})
		})
	}

	function removeFriend(friend: FriendResponse) {
		if (!user) return
		if (!window.confirm('remove this friend connection?')) return
		const uid = user.id
		void runSocialAction(friend.friendship_id, async () => {
			await api.DELETE('/v1/users/{user_id}/friends/{friend_user_id}', {
				params: { path: { user_id: uid, friend_user_id: friend.id } },
			})
		})
	}

	function unblock(block: BlockDetail) {
		if (!user) return
		if (!window.confirm('unblock this user?')) return
		const uid = user.id
		void runSocialAction(block.id, async () => {
			await api.DELETE('/v1/users/{user_id}/blocks/{blocked_user_id}', {
				params: { path: { user_id: uid, blocked_user_id: block.blocked_id } },
			})
		})
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!userId) return
		void reloadToken

		const uid = userId
		isLoading = true
		loadError = null
		user = null
		counts = {}
		countsLoadedForUserId = null
		permissions = null
		clients = []
		clientSubscriptions = []
		friends = []
		incomingRequests = []
		outgoingRequests = []
		blocks = []
		isEditing = false
		prefsExpanded = false
		editingClientId = null
		privacyError = null
		privacySaveSuccess = false
		socialError = null

		loadDetails(uid)
			.catch((e: unknown) => {
				loadError = e instanceof Error ? e.message : 'failed to load user'
			})
			.finally(() => {
				isLoading = false
			})
	})

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!user) return
		if (activeSection !== 'overview') return
		if (countsLoadedForUserId === user.id) return

		const uid = user.id
		countsLoadedForUserId = uid
		void loadCounts(uid).catch(() => {
			if (countsLoadedForUserId === uid) countsLoadedForUserId = null
		})
	})
</script>

<Dialog.Root
	bind:open
	onOpenChange={(v) => {
		if (!v) close()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			data-dialog-content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-[min(96vw,76rem)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-xl"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div class="min-w-0">
					<Dialog.Title class="truncate text-base font-semibold">
						{user ? user.display_name || user.email : 'user details'}
					</Dialog.Title>
					<Dialog.Description class="truncate text-xs text-zinc-500">
						{user?.id ?? userId ?? ''}
					</Dialog.Description>
				</div>
				<div class="flex items-center gap-2">
					<Button
						variant="outline"
						size="sm"
						class="rounded-xl"
						onclick={refresh}
						disabled={isLoading}
					>
						<RefreshCw class="mr-1.5 h-3.5 w-3.5 {isLoading ? 'animate-spin' : ''}" />
						refresh
					</Button>
					<Button variant="ghost" size="icon" class="rounded-xl" onclick={close}>
						<X class="h-4 w-4" />
					</Button>
				</div>
			</div>

			<div class="flex min-h-0 flex-1">
				<aside class="hidden w-52 shrink-0 border-r border-zinc-800 p-4 md:block">
					<div class="space-y-1">
						{#each sections as section (section.key)}
							<button
								type="button"
								class="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition {activeSection ===
								section.key
									? 'bg-zinc-800 text-zinc-100'
									: 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'}"
								onclick={() => (activeSection = section.key)}
							>
								<section.icon class="h-4 w-4" />
								{section.label}
							</button>
						{/each}
					</div>
				</aside>

				<div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
					<div class="mb-4 flex gap-2 overflow-x-auto md:hidden">
						{#each sections as section (section.key)}
							<Button
								variant={activeSection === section.key ? 'default' : 'outline'}
								size="sm"
								class="shrink-0 rounded-xl"
								onclick={() => (activeSection = section.key)}
							>
								<section.icon class="mr-1.5 h-3.5 w-3.5" />
								{section.label}
							</Button>
						{/each}
					</div>

					{#if isLoading}
						<div class="flex items-center justify-center py-16">
							<NokodoLoader />
						</div>
					{:else if loadError}
						<div
							class="rounded-xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
						>
							{loadError}
						</div>
					{:else if user}
						{#if activeSection === 'overview'}
							<div class="space-y-5">
								<div
									class="flex flex-col gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 sm:flex-row sm:items-center"
								>
									<div
										class="h-20 w-20 shrink-0 overflow-hidden rounded-2xl bg-zinc-800"
									>
										{#if user.avatar_url}
											<img
												src={user.avatar_url}
												alt=""
												class="h-full w-full object-cover"
											/>
										{:else}
											<div
												class="flex h-full w-full items-center justify-center text-zinc-500"
											>
												<UserIcon class="h-9 w-9" />
											</div>
										{/if}
									</div>
									<div class="min-w-0 flex-1">
										<div class="flex flex-wrap items-center gap-2">
											<h3 class="truncate text-lg font-semibold">
												{user.display_name || user.email}
											</h3>
											{#if user.is_online}
												<span
													class="inline-flex items-center gap-1 rounded-lg bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300"
												>
													<Circle class="h-3 w-3 fill-emerald-400" />
													online
												</span>
											{/if}
											{#if user.is_superuser}
												<span
													class="inline-flex items-center gap-1 rounded-lg bg-amber-500/10 px-2 py-1 text-xs text-amber-300"
												>
													<Shield class="h-3 w-3" />
													superuser
												</span>
											{/if}
											{#if user.is_active === false}
												<span
													class="inline-flex items-center gap-1 rounded-lg bg-red-500/10 px-2 py-1 text-xs text-red-300"
												>
													<CircleX class="h-3 w-3" />
													inactive
												</span>
											{/if}
										</div>
										<div
											class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400"
										>
											<span class="inline-flex items-center gap-1.5"
												><Mail class="h-3.5 w-3.5" />{user.email}</span
											>
											<span>@{user.username}</span>
											<span class="font-mono text-zinc-500">{user.id}</span>
										</div>
										<p class="mt-3 line-clamp-2 text-sm text-zinc-400">
											{user.bio || 'no bio set'}
										</p>
									</div>
								</div>

								<div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
									<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
										<div class="text-xs text-zinc-500">created</div>
										<div class="mt-1 text-sm text-zinc-200">
											{formatDate(user.created_at)}
										</div>
									</div>
									<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
										<div class="text-xs text-zinc-500">updated</div>
										<div class="mt-1 text-sm text-zinc-200">
											{formatDate(user.updated_at)}
										</div>
									</div>
									<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
										<div class="text-xs text-zinc-500">last active</div>
										<div class="mt-1 text-sm text-zinc-200">
											{formatDate(user.last_active_at)}
										</div>
									</div>
									<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
										<div class="text-xs text-zinc-500">
											discoverable by email
										</div>
										<div class="mt-1 text-sm text-zinc-200">
											{user.find_by_email ? 'yes' : 'no'}
										</div>
									</div>
								</div>

								<div class="space-y-3">
									<p
										class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
									>
										<FolderKanban class="h-3.5 w-3.5" />owned resources
									</p>
									<div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
										{#each resourceActions as resource (resource.key)}
											<Button
												variant="outline"
												class="justify-between rounded-xl"
												onclick={() =>
													openCurrentUserResource(resource.route)}
											>
												<span class="inline-flex items-center gap-2">
													<resource.icon class="h-4 w-4" />
													{resource.label}
												</span>
												<span
													class="rounded-md bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400"
													>{resource.count ?? 0}</span
												>
											</Button>
										{/each}
									</div>
									<div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-sm"
										>
											<Smartphone
												class="mb-2 h-4 w-4 text-zinc-500"
											/>clients: {clients.length}
										</div>
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-sm"
										>
											<Users class="mb-2 h-4 w-4 text-zinc-500" />friends: {friends.length}
										</div>
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-sm"
										>
											<Inbox class="mb-2 h-4 w-4 text-zinc-500" />incoming: {incomingRequests.length}
										</div>
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-sm"
										>
											<Ban class="mb-2 h-4 w-4 text-zinc-500" />blocks: {blocks.length}
										</div>
									</div>
								</div>
							</div>
						{:else if activeSection === 'profile'}
							<div class="space-y-5">
								<div class="flex items-center justify-between">
									<p
										class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
									>
										<Pencil class="h-3.5 w-3.5" />profile
									</p>
									{#if !isEditing}
										<Button
											variant="ghost"
											size="sm"
											class="rounded-xl"
											onclick={startEdit}
										>
											<Pencil class="mr-1.5 h-3.5 w-3.5" />edit
										</Button>
									{/if}
								</div>
								{#if isEditing}
									<div class="grid gap-5 xl:grid-cols-[16rem_1fr]">
										<div
											class="space-y-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-4"
										>
											<div
												class="aspect-square overflow-hidden rounded-2xl bg-zinc-800"
											>
												{#if editAvatarUrl.trim()}
													<img
														src={editAvatarUrl.trim()}
														alt=""
														class="h-full w-full object-cover"
													/>
												{:else}
													<div
														class="flex h-full w-full items-center justify-center text-zinc-500"
													>
														<UserIcon class="h-12 w-12" />
													</div>
												{/if}
											</div>
											<div class="space-y-1.5">
												<Label class="text-xs text-zinc-400"
													>avatar URL</Label
												>
												<Input
													bind:value={editAvatarUrl}
													placeholder="https://..."
													class="rounded-xl border-zinc-700 bg-zinc-950 text-sm"
												/>
											</div>
											<Button
												variant="outline"
												size="sm"
												class="w-full rounded-xl"
												onclick={() => (editAvatarUrl = '')}
												>clear avatar</Button
											>
										</div>
										<div class="space-y-3">
											<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
												<div class="space-y-1.5">
													<Label class="text-xs text-zinc-400"
														>display name</Label
													><Input
														bind:value={editDisplayName}
														class="rounded-xl border-zinc-700 bg-zinc-900 text-sm"
													/>
												</div>
												<div class="space-y-1.5">
													<Label class="text-xs text-zinc-400"
														>username</Label
													><Input
														bind:value={editUsername}
														class="rounded-xl border-zinc-700 bg-zinc-900 text-sm"
													/>
												</div>
											</div>
											<div class="space-y-1.5">
												<Label class="text-xs text-zinc-400">email</Label
												><Input
													bind:value={editEmail}
													type="email"
													class="rounded-xl border-zinc-700 bg-zinc-900 text-sm"
												/>
											</div>
											<div class="space-y-1.5">
												<Label class="text-xs text-zinc-400">bio</Label
												><Textarea
													bind:value={editBio}
													rows={4}
													class="rounded-xl border-zinc-700 bg-zinc-900 text-sm"
												/>
											</div>
											{#if saveError}<div
													class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
												>
													{saveError}
												</div>{/if}
											{#if saveSuccess}<div
													class="rounded-lg border border-emerald-900/50 bg-emerald-900/10 px-3 py-2 text-xs text-emerald-300"
												>
													saved
												</div>{/if}
											<div class="flex gap-2">
												<Button
													variant="outline"
													size="sm"
													class="rounded-xl"
													onclick={saveUser}
													disabled={isSaving}
													><Save class="mr-1.5 h-3.5 w-3.5" />{isSaving
														? 'saving...'
														: 'save user'}</Button
												><Button
													variant="ghost"
													size="sm"
													class="rounded-xl"
													onclick={cancelEdit}
													><X class="mr-1.5 h-3.5 w-3.5" />cancel</Button
												>
											</div>
										</div>
									</div>
								{:else}
									<div class="grid gap-3 md:grid-cols-2">
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-900 p-4"
										>
											<div class="text-xs text-zinc-500">display name</div>
											<div class="mt-1 text-sm">
												{user.display_name ?? 'not set'}
											</div>
										</div>
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-900 p-4"
										>
											<div class="text-xs text-zinc-500">username</div>
											<div class="mt-1 text-sm">@{user.username}</div>
										</div>
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-900 p-4"
										>
											<div class="text-xs text-zinc-500">email</div>
											<div class="mt-1 text-sm">{user.email}</div>
										</div>
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-900 p-4"
										>
											<div class="text-xs text-zinc-500">avatar</div>
											<div class="mt-1 truncate text-sm">
												{user.avatar_url ?? 'not set'}
											</div>
										</div>
										<div
											class="rounded-xl border border-zinc-800 bg-zinc-900 p-4 md:col-span-2"
										>
											<div class="text-xs text-zinc-500">bio</div>
											<div class="mt-1 text-sm whitespace-pre-wrap">
												{user.bio ?? 'not set'}
											</div>
										</div>
									</div>
								{/if}
							</div>
						{:else if activeSection === 'account'}
							<div class="space-y-5">
								<div class="flex items-center justify-between">
									<p
										class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
									>
										<LockKeyhole class="h-3.5 w-3.5" />account
									</p>
									<Button
										variant="outline"
										size="sm"
										class="rounded-xl"
										onclick={saveAccount}
										disabled={isSavingAccount}
									>
										<Save class="mr-1.5 h-3.5 w-3.5" />{isSavingAccount
											? 'saving...'
											: 'save account'}
									</Button>
								</div>

								<div class="grid gap-3 md:grid-cols-2">
									<div
										class="flex items-center justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-sm"
									>
										<div class="min-w-0">
											<div class="text-zinc-100">account enabled</div>
											<div class="text-xs text-zinc-500">can sign in</div>
										</div>
										<Switch bind:checked={editIsActive} />
									</div>
									<div
										class="flex items-center justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-sm"
									>
										<div class="min-w-0">
											<div class="text-zinc-100">superuser</div>
											<div class="text-xs text-zinc-500">admin access</div>
										</div>
										<Switch bind:checked={editIsSuperuser} />
									</div>
								</div>

								{#if accountError}<div
										class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
									>
										{accountError}
									</div>{/if}
								{#if accountSaveSuccess}<div
										class="rounded-lg border border-emerald-900/50 bg-emerald-900/10 px-3 py-2 text-xs text-emerald-300"
									>
										saved
									</div>{/if}

								<div class="rounded-xl border border-red-900/30 bg-red-950/10 p-4">
									<p class="text-xs font-medium text-red-400">delete user</p>
									<p class="mt-2 text-xs text-zinc-400">
										permanently removes this account and owned resources.
									</p>
									{#if deleteUserError}<div
											class="mt-3 rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
										>
											{deleteUserError}
										</div>{/if}
									{#if isViewingSelf}
										<div
											class="mt-3 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-400"
										>
											you cannot delete your own account from here.
										</div>
									{:else if confirmDeleteUser}
										<p class="mt-3 text-xs text-zinc-400">
											delete this user permanently? this cannot be undone.
										</p>
										<div class="mt-3 flex gap-2">
											<Button
												variant="outline"
												size="sm"
												class="rounded-xl border-red-800 text-red-400 hover:bg-red-950"
												onclick={deleteCurrentUser}
												disabled={isDeletingUser}
												><Trash2
													class="mr-1.5 h-3.5 w-3.5"
												/>{isDeletingUser
													? 'deleting...'
													: 'delete user'}</Button
											><Button
												variant="ghost"
												size="sm"
												class="rounded-xl"
												onclick={() => (confirmDeleteUser = false)}
												>cancel</Button
											>
										</div>
									{:else}
										<Button
											variant="outline"
											size="sm"
											class="mt-3 rounded-xl border-red-800 text-red-400 hover:bg-red-950"
											onclick={() => (confirmDeleteUser = true)}
											><Trash2 class="mr-1.5 h-3.5 w-3.5" />delete user</Button
										>
									{/if}
								</div>
							</div>
						{:else if activeSection === 'clients'}
							<div class="space-y-4">
								<div class="flex items-center justify-between">
									<p
										class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
									>
										<Smartphone class="h-3.5 w-3.5" />user clients
									</p>
									<Button
										variant="outline"
										size="sm"
										class="rounded-xl"
										onclick={() => user && loadClients(user.id)}
										><RefreshCw class="mr-1.5 h-3.5 w-3.5" />refresh</Button
									>
								</div>
								{#if clientError}<div
										class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
									>
										{clientError}
									</div>{/if}
								{#if clients.length === 0}<div
										class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
									>
										no registered clients
									</div>{/if}
								{#each clients as client (client.id)}
									<div class="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
										<div
											class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"
										>
											<div class="min-w-0">
												<div class="flex items-center gap-2">
													<Smartphone class="h-4 w-4 text-zinc-500" />
													<h4 class="truncate font-medium">
														{client.name || 'unnamed client'}
													</h4>
												</div>
												<div
													class="mt-1 truncate font-mono text-xs text-zinc-500"
												>
													{client.id}
												</div>
												<div class="mt-2 text-xs text-zinc-400">
													last seen {formatDate(client.last_seen_at)}
												</div>
											</div>
											<div class="flex gap-2">
												<Button
													variant="outline"
													size="sm"
													class="rounded-xl"
													onclick={() => startClientEdit(client)}
													><Edit3
														class="mr-1.5 h-3.5 w-3.5"
													/>edit</Button
												><Button
													variant="outline"
													size="sm"
													class="rounded-xl border-red-800 text-red-400 hover:bg-red-950"
													onclick={() => deleteClient(client)}
													disabled={deletingClientId === client.id}
													><Trash2
														class="mr-1.5 h-3.5 w-3.5"
													/>delete</Button
												>
											</div>
										</div>
										<div class="mt-3 grid gap-3 lg:grid-cols-3">
											<div
												class="rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-xs"
											>
												<div class="mb-1 text-zinc-500">client key</div>
												<div class="font-mono break-all text-zinc-300">
													{client.client_key}
												</div>
											</div>
											<div
												class="rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-xs"
											>
												<div class="mb-1 text-zinc-500">user agent</div>
												<div
													class="break-all whitespace-pre-wrap text-zinc-300"
												>
													{client.user_agent ?? 'not set'}
												</div>
											</div>
											<div
												class="rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-xs"
											>
												<div class="mb-1 text-zinc-500">
													push subscriptions
												</div>
												<div class="text-zinc-300">
													{subscriptionGroup(client.id)?.subscriptions
														.length ?? 0}
												</div>
											</div>
										</div>
										{#if editingClientId === client.id}
											<div
												class="mt-4 space-y-3 border-t border-zinc-800 pt-4"
											>
												<div class="space-y-1.5">
													<Label class="text-xs text-zinc-400">name</Label
													><Input
														bind:value={clientNameText}
														class="rounded-xl border-zinc-700 bg-zinc-950 text-sm"
													/>
												</div>
												<div class="grid gap-3 lg:grid-cols-2">
													<div class="space-y-1.5">
														<Label class="text-xs text-zinc-400"
															>info JSON</Label
														><Textarea
															bind:value={clientInfoText}
															rows={8}
															spellcheck={false}
															class="rounded-xl border-zinc-700 bg-zinc-950 font-mono text-xs"
														/>
													</div>
													<div class="space-y-1.5">
														<Label class="text-xs text-zinc-400"
															>preference overrides JSON</Label
														><Textarea
															bind:value={clientPrefsText}
															rows={8}
															spellcheck={false}
															class="rounded-xl border-zinc-700 bg-zinc-950 font-mono text-xs"
														/>
													</div>
												</div>
												<div class="flex gap-2">
													<Button
														variant="outline"
														size="sm"
														class="rounded-xl"
														onclick={() => saveClient(client)}
														disabled={isSavingClient}
														><Save
															class="mr-1.5 h-3.5 w-3.5"
														/>{isSavingClient
															? 'saving...'
															: 'save client'}</Button
													><Button
														variant="ghost"
														size="sm"
														class="rounded-xl"
														onclick={cancelClientEdit}>cancel</Button
													>
												</div>
											</div>
										{:else}
											<div class="mt-3 grid gap-3 lg:grid-cols-2">
												<div
													class="rounded-xl border border-zinc-800 bg-zinc-950 p-3"
												>
													<div class="mb-1 text-xs text-zinc-500">
														info
													</div>
													<pre
														class="overflow-auto text-xs whitespace-pre-wrap text-zinc-400">{formatJson(
															client.info
														)}</pre>
												</div>
												<div
													class="rounded-xl border border-zinc-800 bg-zinc-950 p-3"
												>
													<div class="mb-1 text-xs text-zinc-500">
														preference overrides
													</div>
													<pre
														class="overflow-auto text-xs whitespace-pre-wrap text-zinc-400">{formatJson(
															client.preferences
														)}</pre>
												</div>
											</div>
										{/if}
										{#if clientPushError(client.id)}
											<div
												class="mt-3 rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
											>
												{clientPushError(client.id)}
											</div>
										{/if}
										{#if clientPushSubscriptions(client.id).length > 0}
											<div class="mt-4 space-y-2">
												<div class="text-xs font-medium text-zinc-500">
													push subscriptions
												</div>
												{#each clientPushSubscriptions(client.id) as subscription (subscription.id)}
													<div
														class="flex items-start justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-950 p-3"
													>
														<div class="min-w-0 text-xs">
															<div
																class="font-mono break-all text-zinc-300"
															>
																{subscription.endpoint}
															</div>
															<div class="mt-1 text-zinc-500">
																created {formatDate(
																	subscription.created_at
																)} · last used {formatDate(
																	subscription.last_used_at
																)}
															</div>
														</div>
														<Button
															variant="ghost"
															size="icon"
															class="shrink-0 rounded-xl text-red-400"
															onclick={() =>
																deletePushSubscription(
																	client,
																	subscription
																)}
															disabled={deletingSubscriptionId ===
																subscription.id}
														>
															<Trash2 class="h-3.5 w-3.5" />
														</Button>
													</div>
												{/each}
											</div>
										{/if}
									</div>
								{/each}
							</div>
						{:else if activeSection === 'social'}
							<div class="space-y-5">
								{#if socialError}<div
										class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
									>
										{socialError}
									</div>{/if}
								<div class="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
									<div
										class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
									>
										<p
											class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
										>
											<LockKeyhole class="h-3.5 w-3.5" />privacy access
										</p>
										<Button
											variant="outline"
											size="sm"
											class="rounded-xl"
											onclick={savePrivacy}
											disabled={isSavingPrivacy}
										>
											<Save class="mr-1.5 h-3.5 w-3.5" />{isSavingPrivacy
												? 'saving...'
												: 'save privacy'}
										</Button>
									</div>
									<div
										class="mt-4 flex items-center justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-sm"
									>
										<div class="min-w-0">
											<div class="text-zinc-100">email discovery</div>
											<div class="text-xs text-zinc-500">
												can be found by email search
											</div>
										</div>
										<Switch bind:checked={editFindByEmail} />
									</div>
									<div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
										{#each privacyFields as field (field.key)}
											<label class="space-y-1.5">
												<span
													class="inline-flex items-center gap-2 text-xs text-zinc-400"
												>
													<Eye
														class="h-3.5 w-3.5 text-zinc-500"
													/>{field.label}
												</span>
												<select
													value={privacyValue(field.key)}
													class="w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200"
													onchange={(event) =>
														setPrivacyValue(
															field.key,
															parseVisibility(
																event.currentTarget.value
															)
														)}
												>
													{#each visibilityOptions as option (option)}
														<option value={option}>{option}</option>
													{/each}
												</select>
											</label>
										{/each}
									</div>
									{#if privacyError}<div
											class="mt-3 rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
										>
											{privacyError}
										</div>{/if}
									{#if privacySaveSuccess}<div
											class="mt-3 rounded-lg border border-emerald-900/50 bg-emerald-900/10 px-3 py-2 text-xs text-emerald-300"
										>
											saved
										</div>{/if}
								</div>
								<div class="grid gap-4 xl:grid-cols-2">
									<div class="space-y-2">
										<p
											class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
										>
											<Users class="h-3.5 w-3.5" />friends
										</p>
										{#if friends.length === 0}<div
												class="rounded-xl border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500"
											>
												no friends
											</div>{/if}{#each friends as friend (friend.friendship_id)}<div
												class="flex items-center justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-900 p-3"
											>
												<div class="min-w-0">
													<div class="truncate text-sm">
														{userLabel(friend, friend.id)}
													</div>
													<div class="truncate text-xs text-zinc-500">
														{friend.email ?? friend.id}
													</div>
												</div>
												<Button
													variant="ghost"
													size="sm"
													class="rounded-xl text-red-400"
													onclick={() => removeFriend(friend)}
													disabled={socialBusyId === friend.friendship_id}
													>remove</Button
												>
											</div>{/each}
									</div>
									<div class="space-y-2">
										<p
											class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
										>
											<Ban class="h-3.5 w-3.5" />blocked people
										</p>
										{#if blocks.length === 0}<div
												class="rounded-xl border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500"
											>
												no blocks
											</div>{/if}{#each blocks as block (block.id)}<div
												class="rounded-xl border border-zinc-800 bg-zinc-900 p-3"
											>
												<div class="flex items-start justify-between gap-3">
													<div class="min-w-0">
														<div
															class="flex items-center gap-2 text-sm"
														>
															<Ban
																class="h-4 w-4 text-zinc-500"
															/>{userLabel(
																block.blocked,
																block.blocked_id
															)}
														</div>
														<div class="mt-1 text-xs text-zinc-500">
															{formatDate(block.created_at)}
														</div>
													</div>
													<Button
														variant="ghost"
														size="sm"
														class="rounded-xl"
														onclick={() => unblock(block)}
														disabled={socialBusyId === block.id}
														>unblock</Button
													>
												</div>
											</div>{/each}
									</div>
								</div>
								<div class="grid gap-4 xl:grid-cols-2">
									<div class="space-y-2">
										<p
											class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
										>
											<Inbox class="h-3.5 w-3.5" />incoming requests
										</p>
										{#if incomingRequests.length === 0}<div
												class="rounded-xl border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500"
											>
												no incoming requests
											</div>{/if}{#each incomingRequests as request (request.id)}{@const requester =
												requestUser(request, 'incoming')}
											<div
												class="rounded-xl border border-zinc-800 bg-zinc-900 p-3"
											>
												<div class="text-sm">
													{userLabel(requester, request.requester_id)}
												</div>
												<div class="mt-1 text-xs text-zinc-500">
													sent {formatDate(request.created_at)}
												</div>
												<div class="mt-3 flex gap-2">
													<Button
														variant="outline"
														size="sm"
														class="rounded-xl"
														onclick={() => acceptRequest(request)}
														disabled={socialBusyId === request.id}
														><CheckCircle
															class="mr-1.5 h-3.5 w-3.5"
														/>accept</Button
													><Button
														variant="ghost"
														size="sm"
														class="rounded-xl text-red-400"
														onclick={() => declineRequest(request)}
														disabled={socialBusyId === request.id}
														>decline</Button
													>
												</div>
											</div>{/each}
									</div>
									<div class="space-y-2">
										<p
											class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
										>
											<MessageSquare class="h-3.5 w-3.5" />outgoing requests
										</p>
										{#if outgoingRequests.length === 0}<div
												class="rounded-xl border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500"
											>
												no outgoing requests
											</div>{/if}{#each outgoingRequests as request (request.id)}{@const addressee =
												requestUser(request, 'outgoing')}
											<div
												class="rounded-xl border border-zinc-800 bg-zinc-900 p-3"
											>
												<div class="text-sm">
													{userLabel(addressee, request.addressee_id)}
												</div>
												<div class="mt-1 text-xs text-zinc-500">
													sent {formatDate(request.created_at)}
												</div>
												<Button
													variant="ghost"
													size="sm"
													class="mt-3 rounded-xl text-red-400"
													onclick={() => cancelRequest(request)}
													disabled={socialBusyId === request.id}
													>cancel request</Button
												>
											</div>{/each}
									</div>
								</div>
							</div>
						{:else if activeSection === 'permissions'}
							<div class="space-y-4">
								<p
									class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
								>
									<KeyRound class="h-3.5 w-3.5" />resolved permissions
								</p>
								{#if !permissions}<div
										class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
									>
										permissions unavailable
									</div>{:else if permissions.permissions.length === 0}<div
										class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
									>
										no explicit action permissions
									</div>{:else}<div class="flex flex-wrap gap-2">
										{#each permissions.permissions as permission (permission)}<span
												class="inline-flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-300"
												><KeyRound
													class="h-3 w-3 text-zinc-500"
												/>{permission}</span
											>{/each}
									</div>{/if}
							</div>
						{:else if activeSection === 'preferences'}
							<div class="space-y-3">
								<div class="flex items-center justify-between">
									<p
										class="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-zinc-500 uppercase"
									>
										<SlidersHorizontal class="h-3.5 w-3.5" />preferences
									</p>
									<Button
										variant="ghost"
										size="sm"
										class="rounded-xl"
										onclick={() =>
											prefsExpanded ? (prefsExpanded = false) : openPrefs()}
										>{prefsExpanded ? 'collapse' : 'edit JSON'}</Button
									>
								</div>
								{#if prefsExpanded}<Textarea
										bind:value={prefsText}
										rows={18}
										spellcheck={false}
										class="rounded-xl border-zinc-700 bg-zinc-900 font-mono text-xs text-zinc-300"
									/>{#if prefsError}<div
											class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
										>
											{prefsError}
										</div>{/if}{#if prefsSaveSuccess}<div
											class="rounded-lg border border-emerald-900/50 bg-emerald-900/10 px-3 py-2 text-xs text-emerald-300"
										>
											saved
										</div>{/if}<Button
										variant="outline"
										size="sm"
										class="rounded-xl"
										onclick={savePrefs}
										disabled={isSavingPrefs}
										><Save class="mr-1.5 h-3.5 w-3.5" />{isSavingPrefs
											? 'saving...'
											: 'save preferences'}</Button
									>{:else}<pre
										class="max-h-128 overflow-auto rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-xs text-zinc-400">{formatJson(
											user.preferences
										)}</pre>{/if}
							</div>
						{/if}
					{:else}
						<div
							class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500"
						>
							no user selected
						</div>
					{/if}
				</div>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
