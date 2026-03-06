export interface GlassState {
	/** backdrop blur in px */
	blur: number
	/** light distortion intensity (1-5) */
	refractiveIndex: number
	/** specular highlight opacity (0-1) */
	specularOpacity: number
	/** glass opacity/thickness (0-200) */
	glassThickness: number
	/** bezel/border width in px */
	bezelWidth: number
}

export interface GlassPreset {
	base: GlassState
	hover?: Partial<GlassState>
	focus?: Partial<GlassState>
	active?: Partial<GlassState>
	spring?: { stiffness: number; damping: number }
}

export type GlassPresetName = 'subtle' | 'standard' | 'heavy' | 'nav' | 'panel'
export type GlassInput = GlassPresetName | GlassPreset
