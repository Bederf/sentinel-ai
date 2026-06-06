import { expect, it } from 'vitest'
import {
  getModuleScope,
  voiceBelongsToModule,
  subsystemBelongsToModule,
  equipmentTypeBelongsToModule,
} from '../moduleScopes'

it('getModuleScope overview returns all-accepting scope', () => {
  const scope = getModuleScope('overview')
  expect(scope.id).toBe('overview')
  expect(scope.acceptedVoices).toEqual([])
  expect(scope.equipmentTypes).toEqual([])
  expect(scope.subsystemAliases).toEqual([])
})

it('voiceBelongsToModule hvac_pressure for hvac returns true', () => {
  expect(voiceBelongsToModule('comfort_stress', 'hvac')).toBe(true)
})

it('voiceBelongsToModule leak_detection for hvac returns false', () => {
  expect(voiceBelongsToModule('leak_detection', 'hvac')).toBe(false)
})

it('subsystemBelongsToModule water for hvac returns false', () => {
  expect(subsystemBelongsToModule('water', 'hvac')).toBe(false)
})

it('subsystemBelongsToModule hvac for hvac returns true', () => {
  expect(subsystemBelongsToModule('hvac', 'hvac')).toBe(true)
})

it('equipmentTypeBelongsToModule chiller for water returns false', () => {
  expect(equipmentTypeBelongsToModule('chiller', 'water')).toBe(false)
})

it('equipmentTypeBelongsToModule water_meter for water returns true', () => {
  expect(equipmentTypeBelongsToModule('water_meter', 'water')).toBe(true)
})

it('getModuleScope solar_bess returns correct id', () => {
  expect(getModuleScope('solar_bess').id).toBe('solar_bess')
})
