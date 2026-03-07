<script lang="ts">
	import type { ToolExecution } from '$lib/tools'

	interface Props {
		execution: ToolExecution
	}

	let { execution }: Props = $props()

	let isActive = $derived(execution.status === 'pending' || execution.status === 'running')

	// extract code: prefer parsed args, fall back to raw stream extraction
	let code = $derived.by(() => {
		const parsed = execution.toolCall.arguments.code
		if (typeof parsed === 'string' && parsed) return parsed
		// fallback: extract from raw accumulated JSON string
		const raw = execution.rawArguments ?? ''
		if (!raw) return ''
		const extracted = extractStreamingCode(raw)
		return extracted
	})

	// parse result JSON from tool message
	interface CodeResult {
		action?: string
		stdout?: string
		stderr?: string
		error?: string
		results?: unknown[]
	}

	let resultData = $derived.by((): CodeResult | null => {
		if (!execution.result) return null
		try {
			const parsed = JSON.parse(execution.result.output)
			if (typeof parsed === 'object' && parsed !== null) {
				// ensure string fields are actually strings
				const r = parsed as Record<string, unknown>
				return {
					action: typeof r.action === 'string' ? r.action : undefined,
					stdout: stringify(r.stdout),
					stderr: stringify(r.stderr),
					error: stringify(r.error),
					results: Array.isArray(r.results) ? r.results : undefined,
				}
			}
		} catch {
			// not json, treat whole output as stdout
			return { stdout: execution.result.output }
		}
		return null
	})

	let hasOutput = $derived(
		resultData !== null &&
			(!!resultData.stdout ||
				!!resultData.stderr ||
				!!resultData.error ||
				(resultData.results && resultData.results.length > 0))
	)

	/** extract a partial/full code value from the raw accumulated JSON string */
	function extractStreamingCode(raw: string): string {
		// match "code": " followed by content (handles escapes, no closing quote needed)
		const match = raw.match(/"code"\s*:\s*"((?:[^"\\]|\\.)*)/)
		if (!match) return ''
		try {
			return JSON.parse('"' + match[1] + '"')
		} catch {
			return match[1]
				.replace(/\\n/g, '\n')
				.replace(/\\t/g, '\t')
				.replace(/\\r/g, '\r')
				.replace(/\\"/g, '"')
				.replace(/\\\\/g, '\\')
		}
	}

	/** safely coerce a value to string — avoids [object Object] in templates */
	function stringify(val: unknown): string | undefined {
		if (val === undefined || val === null) return undefined
		if (typeof val === 'string') return val
		return JSON.stringify(val)
	}
</script>

<div class="space-y-1.5">
	<!-- code input block -->
	{#if code}
		<div class="bg-muted/50 border-border overflow-hidden rounded-lg border text-xs">
			<div
				class="border-border text-muted-foreground flex items-center gap-1.5 border-b px-2.5 py-1"
			>
				<span class="font-mono text-[10px] tracking-wide uppercase">input</span>
				{#if isActive}
					<span class="bg-foreground/15 h-1.5 w-1.5 animate-pulse rounded-full"></span>
				{/if}
			</div>
			<pre
				class="text-foreground/80 max-h-48 overflow-auto px-2.5 py-2 font-mono leading-relaxed whitespace-pre-wrap">{code}</pre>
		</div>
	{/if}

	<!-- output block -->
	{#if hasOutput && resultData}
		<div class="bg-muted/50 border-border overflow-hidden rounded-lg border text-xs">
			<div
				class="border-border text-muted-foreground flex items-center gap-1.5 border-b px-2.5 py-1"
			>
				<span class="font-mono text-[10px] tracking-wide uppercase">output</span>
			</div>
			<div class="space-y-0">
				{#if resultData.stdout}
					<pre
						class="text-foreground/80 max-h-48 overflow-auto px-2.5 py-2 font-mono leading-relaxed whitespace-pre-wrap">{resultData.stdout}</pre>
				{/if}
				{#if resultData.results && resultData.results.length > 0}
					<pre
						class="text-foreground/80 max-h-48 overflow-auto px-2.5 py-2 font-mono leading-relaxed whitespace-pre-wrap {resultData.stdout
							? 'border-border border-t'
							: ''}">{resultData.results
							.map((r) => (typeof r === 'string' ? r : JSON.stringify(r)))
							.join('\n')}</pre>
				{/if}
				{#if resultData.stderr}
					<pre
						class="text-muted-foreground max-h-32 overflow-auto px-2.5 py-2 font-mono leading-relaxed whitespace-pre-wrap {resultData.stdout ||
						(resultData.results && resultData.results.length > 0)
							? 'border-border border-t'
							: ''}">{resultData.stderr}</pre>
				{/if}
				{#if resultData.error}
					<pre
						class="text-destructive max-h-32 overflow-auto px-2.5 py-2 font-mono leading-relaxed whitespace-pre-wrap {resultData.stdout ||
						resultData.stderr ||
						(resultData.results && resultData.results.length > 0)
							? 'border-border border-t'
							: ''}">{resultData.error}</pre>
				{/if}
			</div>
		</div>
	{/if}
</div>
