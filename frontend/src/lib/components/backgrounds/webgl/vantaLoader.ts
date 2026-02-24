import * as THREE from 'three'

type VantaFactory = (options: Record<string, unknown>) => { destroy?: () => void }

type VantaNamespace = {
	FOG?: VantaFactory
	CLOUDS?: VantaFactory
	CLOUDS2?: VantaFactory
}

declare global {
	interface Window {
		VANTA?: VantaNamespace
		THREE?: typeof THREE
	}
}

const scriptPromises = new Map<string, Promise<void>>()

function loadScriptOnce(src: string): Promise<void> {
	const existing = scriptPromises.get(src)
	if (existing) return existing

	const promise = new Promise<void>((resolve, reject) => {
		const already = document.querySelector(`script[src="${src}"]`)
		if (already) {
			resolve()
			return
		}

		const script = document.createElement('script')
		script.src = src
		script.async = true
		script.onload = () => resolve()
		script.onerror = () => reject(new Error(`failed to load script: ${src}`))
		document.head.appendChild(script)
	})

	scriptPromises.set(src, promise)
	return promise
}

export async function ensureVanta(effectScriptPath: string): Promise<VantaNamespace> {
	window.THREE = THREE
	await loadScriptOnce(effectScriptPath)
	if (!window.VANTA) {
		throw new Error('vanta failed to initialize')
	}
	return window.VANTA
}
