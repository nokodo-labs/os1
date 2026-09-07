// example asks the home composer cycles through while it sits empty.
//
// they double as a menu of what the system can actually do, so every surface
// gets a fair share. adding one is a single line - keep it lowercase, short
// enough to survive a phone-width composer, and phrased the way a person
// would actually ask.

export const PLACEHOLDER_SURFACES = [
	'chats',
	'notes',
	'reminders',
	'calendar',
	'files',
	'projects',
	'web',
	'media',
	'social',
	'playful',
] as const

export type PlaceholderSurface = (typeof PLACEHOLDER_SURFACES)[number]

export interface PlaceholderExample {
	/** the line shown in the composer. */
	text: string
	/** which part of the system the ask lands in. */
	surface: PlaceholderSurface
}

export const HOME_PLACEHOLDER_EXAMPLES: readonly PlaceholderExample[] = [
	// chats
	{ text: 'summarize my unread messages', surface: 'chats' },
	{ text: 'catch me up on what i missed today', surface: 'chats' },
	{ text: 'find the chat where we talked about the lease', surface: 'chats' },
	{ text: 'who is still waiting on a reply from me', surface: 'chats' },
	{ text: 'draft a reply to the last message from mom', surface: 'chats' },
	{ text: 'turn this thread into something i can forward', surface: 'chats' },
	{ text: 'what did we decide in the design thread', surface: 'chats' },

	// notes
	{ text: 'make a note about the espresso machine i want', surface: 'notes' },
	{ text: 'what did i write down about the roadmap', surface: 'notes' },
	{ text: 'start a note for the trip packing list', surface: 'notes' },
	{ text: 'turn my meeting scribbles into clean notes', surface: 'notes' },
	{ text: 'find the note with the wifi password', surface: 'notes' },
	{ text: 'add these book recommendations to my reading note', surface: 'notes' },
	{ text: 'turn my notes from monday into a checklist', surface: 'notes' },

	// reminders
	{ text: 'remind me to water the plants on sunday', surface: 'reminders' },
	{ text: 'remind me to call the dentist tomorrow at 10', surface: 'reminders' },
	{ text: "what's overdue on my reminders", surface: 'reminders' },
	{ text: 'add milk, eggs and coffee to the groceries list', surface: 'reminders' },
	{ text: 'nudge me about the passport renewal in two weeks', surface: 'reminders' },
	{ text: 'clear everything i already finished today', surface: 'reminders' },
	{ text: 'what do i keep forgetting to do', surface: 'reminders' },

	// calendar
	{ text: "what's on my calendar friday", surface: 'calendar' },
	{ text: 'am i free thursday afternoon', surface: 'calendar' },
	{ text: 'block two hours tomorrow for deep work', surface: 'calendar' },
	{ text: 'move my 3pm to next week', surface: 'calendar' },
	{ text: "when's my next flight", surface: 'calendar' },
	{ text: 'how many meetings do i have this week', surface: 'calendar' },
	{ text: 'find a slot where everyone is actually free', surface: 'calendar' },

	// files
	{ text: 'find the invoice i uploaded last month', surface: 'files' },
	{ text: "what's in that PDF i saved yesterday", surface: 'files' },
	{ text: 'pull the numbers out of the spreadsheet', surface: 'files' },
	{ text: 'find every screenshot from the trip', surface: 'files' },
	{ text: 'summarize the contract i dropped in earlier', surface: 'files' },
	{ text: 'which files did i touch this week', surface: 'files' },

	// projects
	{ text: "what's left on the kitchen renovation", surface: 'projects' },
	{ text: 'start a project for the podcast', surface: 'projects' },
	{ text: 'what did i decide about the launch date', surface: 'projects' },
	{ text: 'show me everything tied to the move', surface: 'projects' },
	{ text: 'break this idea into steps i can actually start', surface: 'projects' },
	{ text: 'which project have i been ignoring', surface: 'projects' },

	// web
	{ text: 'what happened in the news today', surface: 'web' },
	{ text: 'compare these two laptops for me', surface: 'web' },
	{ text: "find a recipe for what's in my fridge", surface: 'web' },
	{ text: 'is this restaurant any good', surface: 'web' },
	{ text: 'look up the return policy for that order', surface: 'web' },
	{ text: "what's the weather doing this weekend", surface: 'web' },
	{ text: 'track my package', surface: 'web' },

	// media
	{ text: 'what should i watch tonight', surface: 'media' },
	{ text: 'find that movie with the boat and the storm', surface: 'media' },
	{ text: 'add the new season to my watchlist', surface: 'media' },
	{ text: 'show me something short and funny', surface: 'media' },
	{ text: "what's that song from the ad", surface: 'media' },
	{ text: 'is it worth finishing this show', surface: 'media' },

	// social
	{ text: "remind me when it's my sister's birthday", surface: 'social' },
	{ text: "who haven't i talked to in a while", surface: 'social' },
	{ text: 'draft a message to the group about saturday', surface: 'social' },
	{ text: 'help me pick a gift for a friend', surface: 'social' },

	// playful + everyday glue
	{ text: 'plan my day around my meetings', surface: 'playful' },
	{ text: 'what should i focus on right now', surface: 'playful' },
	{ text: 'what did i actually get done this week', surface: 'playful' },
	{ text: 'write a haiku about my to-do list', surface: 'playful' },
	{ text: 'talk me out of buying another keyboard', surface: 'playful' },
	{ text: 'give me a pep talk, i have 14 tabs open', surface: 'playful' },
	{ text: 'settle a bet: is a hotdog a sandwich', surface: 'playful' },
	{ text: 'name my new plant', surface: 'playful' },
	{ text: "pick something for me, i can't decide", surface: 'playful' },
	{ text: 'what should i cook with three eggs and regret', surface: 'playful' },
	{ text: 'make today feel less chaotic', surface: 'playful' },
	{ text: 'explain what i just read like i am five', surface: 'playful' },
	{ text: 'ask me something i keep avoiding', surface: 'playful' },
	{ text: 'surprise me', surface: 'playful' },
]

/** just the lines, optionally narrowed to a few surfaces. */
export function placeholderTexts(
	surfaces?: readonly PlaceholderSurface[],
	examples: readonly PlaceholderExample[] = HOME_PLACEHOLDER_EXAMPLES
): string[] {
	const pool = surfaces ? examples.filter((e) => surfaces.includes(e.surface)) : examples
	return pool.map((e) => e.text)
}

/** the full home library, ready to hand to the composer. */
export const HOME_PLACEHOLDER_TEXTS: readonly string[] = placeholderTexts()
