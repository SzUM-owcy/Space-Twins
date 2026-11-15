export type Profile = 'field' | 'facility'

export const PROFILES: Record<Profile, { label: string; hint: string }> = {
  field: { label: 'Field campaign', hint: 'short rover and instrument tests' },
  facility: { label: 'Facility', hint: 'repeated campaigns and habitat tests' },
}
