/** shared helpers for safely deriving display data from urls. */

/** returns a hostname for a url, or null when the input is invalid. */
export function safeHostname(url: string): string | null {
	try {
		return new URL(url).hostname.replace(/^www\./, '')
	} catch {
		return null
	}
}
