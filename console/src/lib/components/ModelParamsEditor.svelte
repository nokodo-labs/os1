<script lang="ts">
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'

	type ModelType = 'chat_model' | 'embedding' | 'image' | 'audio' | 'video'

	interface Props {
		modelType: ModelType
		params: Record<string, unknown>
	}

	let { modelType, params = $bindable() }: Props = $props()

	// -- helpers ----------------------------------------------------------------

	function setParam(key: string, value: unknown) {
		if (value === '' || value === null || value === undefined) {
			const next = { ...params }
			delete next[key]
			params = next
		} else {
			params = { ...params, [key]: value }
		}
	}

	function numParam(key: string): string {
		const v = params[key]
		if (v === null || v === undefined || v === '') return ''
		return String(v)
	}

	function strParam(key: string): string {
		const v = params[key]
		if (v === null || v === undefined) return ''
		return String(v)
	}

	function selectParam(key: string): string | undefined {
		const v = params[key]
		if (v === null || v === undefined || v === '') return undefined
		return String(v)
	}

	function handleNum(key: string, raw: string, integer = false) {
		const trimmed = raw.trim()
		if (!trimmed) {
			setParam(key, undefined)
			return
		}
		const n = integer ? parseInt(trimmed, 10) : parseFloat(trimmed)
		if (Number.isFinite(n)) {
			setParam(key, n)
		}
	}

	function stopListStr(): string {
		const v = params['stop']
		if (!Array.isArray(v)) return ''
		return v.join(', ')
	}

	function handleStopList(raw: string) {
		const trimmed = raw.trim()
		if (!trimmed) {
			setParam('stop', undefined)
			return
		}
		const items = trimmed
			.split(',')
			.map((s) => s.trim())
			.filter(Boolean)
		if (items.length === 0) {
			setParam('stop', undefined)
		} else {
			setParam('stop', items)
		}
	}
</script>

{#if modelType === 'chat_model'}
	<div class="space-y-3">
		<p class="text-xs font-medium text-zinc-400">chat parameters</p>

		<div class="grid gap-3 sm:grid-cols-2">
			<div class="space-y-1">
				<Label for="p-temperature" class="text-xs">temperature</Label>
				<Input
					id="p-temperature"
					type="number"
					step="0.05"
					min="0"
					max="2"
					placeholder="default"
					value={numParam('temperature')}
					oninput={(e: Event) =>
						handleNum('temperature', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-max_tokens" class="text-xs">max tokens</Label>
				<Input
					id="p-max_tokens"
					type="number"
					step="1"
					min="1"
					placeholder="default"
					value={numParam('max_tokens')}
					oninput={(e: Event) =>
						handleNum('max_tokens', (e.target as HTMLInputElement).value, true)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-top_p" class="text-xs">top p</Label>
				<Input
					id="p-top_p"
					type="number"
					step="0.05"
					min="0"
					max="1"
					placeholder="default"
					value={numParam('top_p')}
					oninput={(e: Event) => handleNum('top_p', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-top_k" class="text-xs">top k</Label>
				<Input
					id="p-top_k"
					type="number"
					step="1"
					min="0"
					placeholder="default"
					value={numParam('top_k')}
					oninput={(e: Event) =>
						handleNum('top_k', (e.target as HTMLInputElement).value, true)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-freq_pen" class="text-xs">frequency penalty</Label>
				<Input
					id="p-freq_pen"
					type="number"
					step="0.1"
					min="-2"
					max="2"
					placeholder="default"
					value={numParam('frequency_penalty')}
					oninput={(e: Event) =>
						handleNum('frequency_penalty', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-pres_pen" class="text-xs">presence penalty</Label>
				<Input
					id="p-pres_pen"
					type="number"
					step="0.1"
					min="-2"
					max="2"
					placeholder="default"
					value={numParam('presence_penalty')}
					oninput={(e: Event) =>
						handleNum('presence_penalty', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-min_p" class="text-xs">min p</Label>
				<Input
					id="p-min_p"
					type="number"
					step="0.01"
					min="0"
					max="1"
					placeholder="default"
					value={numParam('min_p')}
					oninput={(e: Event) => handleNum('min_p', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-seed" class="text-xs">seed</Label>
				<Input
					id="p-seed"
					type="number"
					step="1"
					placeholder="default"
					value={numParam('seed')}
					oninput={(e: Event) =>
						handleNum('seed', (e.target as HTMLInputElement).value, true)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
		</div>

		<div class="grid gap-3 sm:grid-cols-2">
			<div class="space-y-1">
				<Label for="p-reasoning" class="text-xs">reasoning effort</Label>
				<Select
					value={selectParam('reasoning_effort')}
					onValueChange={(v: string) =>
						setParam('reasoning_effort', v === '__default__' ? undefined : v)}
				>
					<SelectTrigger id="p-reasoning" class="h-8 rounded-lg text-xs">
						<span class="truncate text-left">
							{selectParam('reasoning_effort') ?? 'default'}
						</span>
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="__default__">default</SelectItem>
						<SelectItem value="none">no reasoning</SelectItem>
						<SelectItem value="low">low</SelectItem>
						<SelectItem value="medium">medium</SelectItem>
						<SelectItem value="high">high</SelectItem>
						<SelectItem value="max">max</SelectItem>
					</SelectContent>
				</Select>
			</div>
			<div class="space-y-1">
				<Label for="p-repeat_pen" class="text-xs">repeat penalty</Label>
				<Input
					id="p-repeat_pen"
					type="number"
					step="0.1"
					min="0"
					placeholder="default"
					value={numParam('repeat_penalty')}
					oninput={(e: Event) =>
						handleNum('repeat_penalty', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
		</div>

		<div class="space-y-1">
			<Label for="p-stop" class="text-xs">stop sequences</Label>
			<Input
				id="p-stop"
				placeholder="comma-separated, e.g. <|end|>, ###"
				value={stopListStr()}
				oninput={(e: Event) => handleStopList((e.target as HTMLInputElement).value)}
				class="h-8 rounded-lg text-xs"
			/>
			<p class="text-[10px] text-zinc-500">comma-separated list of stop tokens.</p>
		</div>
	</div>
{:else if modelType === 'embedding'}
	<div class="space-y-3">
		<p class="text-xs text-zinc-500 italic">
			embedding models have no configurable generation parameters.
		</p>
	</div>
{:else if modelType === 'image'}
	<div class="space-y-3">
		<p class="text-xs font-medium text-zinc-400">image parameters</p>

		<div class="grid gap-3 sm:grid-cols-2">
			<div class="space-y-1">
				<Label for="p-n" class="text-xs">count (n)</Label>
				<Input
					id="p-n"
					type="number"
					step="1"
					min="1"
					max="10"
					placeholder="1"
					value={numParam('n')}
					oninput={(e: Event) =>
						handleNum('n', (e.target as HTMLInputElement).value, true)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-size" class="text-xs">size</Label>
				<Input
					id="p-size"
					placeholder="e.g. 1024x1024"
					value={strParam('size')}
					oninput={(e: Event) => setParam('size', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-aspect" class="text-xs">aspect ratio</Label>
				<Input
					id="p-aspect"
					placeholder="e.g. 16:9"
					value={strParam('aspect_ratio')}
					oninput={(e: Event) =>
						setParam('aspect_ratio', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-quality" class="text-xs">quality</Label>
				<Select
					value={selectParam('quality')}
					onValueChange={(v: string) =>
						setParam('quality', v === '__none__' ? undefined : v)}
				>
					<SelectTrigger id="p-quality" class="h-8 rounded-lg text-xs">
						<span class="truncate text-left">
							{selectParam('quality') ?? 'default'}
						</span>
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="__none__">default</SelectItem>
						<SelectItem value="standard">standard</SelectItem>
						<SelectItem value="hd">hd</SelectItem>
						<SelectItem value="auto">auto</SelectItem>
					</SelectContent>
				</Select>
			</div>
			<div class="space-y-1">
				<Label for="p-style" class="text-xs">style</Label>
				<Select
					value={selectParam('style')}
					onValueChange={(v: string) =>
						setParam('style', v === '__none__' ? undefined : v)}
				>
					<SelectTrigger id="p-style" class="h-8 rounded-lg text-xs">
						<span class="truncate text-left">
							{selectParam('style') ?? 'default'}
						</span>
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="__none__">default</SelectItem>
						<SelectItem value="natural">natural</SelectItem>
						<SelectItem value="vivid">vivid</SelectItem>
					</SelectContent>
				</Select>
			</div>
			<div class="space-y-1">
				<Label for="p-bg" class="text-xs">background</Label>
				<Select
					value={selectParam('background')}
					onValueChange={(v: string) =>
						setParam('background', v === '__none__' ? undefined : v)}
				>
					<SelectTrigger id="p-bg" class="h-8 rounded-lg text-xs">
						<span class="truncate text-left">
							{selectParam('background') ?? 'default'}
						</span>
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="__none__">default</SelectItem>
						<SelectItem value="transparent">transparent</SelectItem>
						<SelectItem value="opaque">opaque</SelectItem>
						<SelectItem value="auto">auto</SelectItem>
					</SelectContent>
				</Select>
			</div>
			<div class="space-y-1">
				<Label for="p-outfmt" class="text-xs">output format</Label>
				<Select
					value={selectParam('output_format')}
					onValueChange={(v: string) =>
						setParam('output_format', v === '__none__' ? undefined : v)}
				>
					<SelectTrigger id="p-outfmt" class="h-8 rounded-lg text-xs">
						<span class="truncate text-left">
							{selectParam('output_format') ?? 'default'}
						</span>
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="__none__">default</SelectItem>
						<SelectItem value="png">png</SelectItem>
						<SelectItem value="jpeg">jpeg</SelectItem>
						<SelectItem value="webp">webp</SelectItem>
					</SelectContent>
				</Select>
			</div>
			<div class="space-y-1">
				<Label for="p-strength" class="text-xs">strength</Label>
				<Input
					id="p-strength"
					type="number"
					step="0.05"
					min="0"
					max="1"
					placeholder="default"
					value={numParam('strength')}
					oninput={(e: Event) =>
						handleNum('strength', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
		</div>

		<div class="space-y-1">
			<Label for="p-negprompt" class="text-xs">negative prompt</Label>
			<Input
				id="p-negprompt"
				placeholder="default"
				value={strParam('negative_prompt')}
				oninput={(e: Event) =>
					setParam('negative_prompt', (e.target as HTMLInputElement).value)}
				class="h-8 rounded-lg text-xs"
			/>
		</div>
	</div>
{:else if modelType === 'audio'}
	<div class="space-y-3">
		<p class="text-xs font-medium text-zinc-400">audio parameters</p>

		<div class="grid gap-3 sm:grid-cols-2">
			<div class="space-y-1">
				<Label for="p-voice" class="text-xs">voice</Label>
				<Input
					id="p-voice"
					placeholder="default"
					value={strParam('voice')}
					oninput={(e: Event) => setParam('voice', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-speed" class="text-xs">speed</Label>
				<Input
					id="p-speed"
					type="number"
					step="0.1"
					min="0.25"
					max="4"
					placeholder="default"
					value={numParam('speed')}
					oninput={(e: Event) => handleNum('speed', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-duration" class="text-xs">duration (sec)</Label>
				<Input
					id="p-duration"
					type="number"
					step="0.5"
					min="0"
					placeholder="default"
					value={numParam('duration')}
					oninput={(e: Event) =>
						handleNum('duration', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-aqual" class="text-xs">quality</Label>
				<Select
					value={selectParam('quality')}
					onValueChange={(v: string) =>
						setParam('quality', v === '__none__' ? undefined : v)}
				>
					<SelectTrigger id="p-aqual" class="h-8 rounded-lg text-xs">
						<span class="truncate text-left">
							{selectParam('quality') ?? 'default'}
						</span>
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="__none__">default</SelectItem>
						<SelectItem value="standard">standard</SelectItem>
						<SelectItem value="hd">hd</SelectItem>
					</SelectContent>
				</Select>
			</div>
			<div class="space-y-1">
				<Label for="p-afmt" class="text-xs">output format</Label>
				<Select
					value={selectParam('output_format')}
					onValueChange={(v: string) =>
						setParam('output_format', v === '__none__' ? undefined : v)}
				>
					<SelectTrigger id="p-afmt" class="h-8 rounded-lg text-xs">
						<span class="truncate text-left">
							{selectParam('output_format') ?? 'default'}
						</span>
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="__none__">default</SelectItem>
						<SelectItem value="mp3">mp3</SelectItem>
						<SelectItem value="wav">wav</SelectItem>
						<SelectItem value="flac">flac</SelectItem>
						<SelectItem value="opus">opus</SelectItem>
						<SelectItem value="aac">aac</SelectItem>
					</SelectContent>
				</Select>
			</div>
		</div>
	</div>
{:else if modelType === 'video'}
	<div class="space-y-3">
		<p class="text-xs font-medium text-zinc-400">video parameters</p>

		<div class="grid gap-3 sm:grid-cols-2">
			<div class="space-y-1">
				<Label for="p-vduration" class="text-xs">duration (sec)</Label>
				<Input
					id="p-vduration"
					type="number"
					step="0.5"
					min="0"
					placeholder="default"
					value={numParam('duration')}
					oninput={(e: Event) =>
						handleNum('duration', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-vsize" class="text-xs">size</Label>
				<Input
					id="p-vsize"
					placeholder="e.g. 1920x1080"
					value={strParam('size')}
					oninput={(e: Event) => setParam('size', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-vaspect" class="text-xs">aspect ratio</Label>
				<Input
					id="p-vaspect"
					placeholder="e.g. 16:9"
					value={strParam('aspect_ratio')}
					oninput={(e: Event) =>
						setParam('aspect_ratio', (e.target as HTMLInputElement).value)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-fps" class="text-xs">fps</Label>
				<Input
					id="p-fps"
					type="number"
					step="1"
					min="1"
					placeholder="default"
					value={numParam('fps')}
					oninput={(e: Event) =>
						handleNum('fps', (e.target as HTMLInputElement).value, true)}
					class="h-8 rounded-lg text-xs"
				/>
			</div>
			<div class="space-y-1">
				<Label for="p-vqual" class="text-xs">quality</Label>
				<Select
					value={selectParam('quality')}
					onValueChange={(v: string) =>
						setParam('quality', v === '__none__' ? undefined : v)}
				>
					<SelectTrigger id="p-vqual" class="h-8 rounded-lg text-xs">
						<span class="truncate text-left">
							{selectParam('quality') ?? 'default'}
						</span>
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="__none__">default</SelectItem>
						<SelectItem value="standard">standard</SelectItem>
						<SelectItem value="hd">hd</SelectItem>
					</SelectContent>
				</Select>
			</div>
		</div>
	</div>
{/if}
