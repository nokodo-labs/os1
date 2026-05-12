export function faviconCandidates(origin: string): string[] {
	try {
		const url = new URL(origin)
		return [
			`https://www.google.com/s2/favicons?sz=64&domain_url=${encodeURIComponent(url.origin)}`,
			`${url.origin}/favicon.svg`,
			`${url.origin}/favicon.ico`,
			`${url.origin}/favicon.png`,
			`${url.origin}/apple-touch-icon.png`,
		]
	} catch {
		return []
	}
}

export function faviconUrl(origin: string): string | undefined {
	return faviconCandidates(origin)[0]
}
