import { describe, expect, it } from 'vitest'
import { buildBmsExecutionGuide, buildDecisionSurface } from '../decisionSurface'

describe('decisionSurface', () => {
  it('uses Time to Discomfort for site-002 decisions', () => {
    const surface = buildDecisionSurface({
      building_id: 'site-002',
      primary_asset_id: 'S002-CHILLER-B1-001',
      alert_text: 'Chiller fault detected',
      recommended_action: 'Switch to backup chiller B1-002',
      time_to_discomfort: 42,
      building_metadata: { deployment_mode: 'advisory' },
    })

    expect(surface.time.label).toBe('Time to Discomfort')
    expect(surface.time.value).toBe('42 min')
    expect(surface.behavior.showInstructions).toBe(true)
    expect(surface.action.operatorPrompt).toBe('Execute this now in the BMS using the mapped navigation path below.')
  })

  it('uses Time to Constraint Breach outside site-002', () => {
    const surface = buildDecisionSurface({
      building_id: 'site-101',
      primary_asset_id: 'S101-AHU-L2-003',
      alert_text: 'Airflow constraint approaching',
      recommended_action: 'Increase outside air damper to 50%',
      building_metadata: { deployment_mode: 'supervised' },
    })

    expect(surface.time.label).toBe('Time to Constraint Breach')
    expect(surface.behavior.showApproval).toBe(true)
    expect(surface.action.operatorPrompt).toBe('[HOLD TO APPROVE]')
  })

  it('builds a chiller BMS guide with navigation, command, and verification', () => {
    const guide = buildBmsExecutionGuide({
      building_id: 'site-002',
      primary_asset_id: 'S002-CHILLER-B1-001',
      recommended_action: 'Switch to backup chiller B1-002 and schedule emergency maintenance',
    })

    expect(guide).not.toBeNull()
    expect(guide?.navigationPath).toEqual([
      'Desigo CC',
      'Site-002',
      'Plant Controls',
      'Basement B1',
      'Chillers',
      'S002-CHILLER-B1-001',
    ])
    expect(guide?.command).toContain('standby chiller')
    expect(guide?.verification).toContain('chilled-water')
  })

  it('treats autonomous mode as result-only', () => {
    const surface = buildDecisionSurface({
      building_id: 'site-002',
      alert_text: 'Load-shed recovery in progress',
      recommended_action: 'Reset lighting schedules to occupied mode',
      building_metadata: { deployment_mode: 'autonomous' },
    })

    expect(surface.behavior.showResultOnly).toBe(true)
    expect(surface.behavior.showApproval).toBe(false)
    expect(surface.action.expectedOutcome).toContain('executes and reports')
  })

  it('advisory mode guide renders all four sections for CHILLER decision', () => {
    const surface = buildDecisionSurface({
      building_id: 'site-002',
      primary_asset_id: 'S002-CHILLER-B1-001',
      alert_text: 'Chiller leaving-water temperature rising',
      recommended_action: 'Adjust chilled-water setpoint down 2 degrees',
      time_to_discomfort: 15,
      building_metadata: { deployment_mode: 'advisory' },
    })

    expect(surface.behavior.showInstructions).toBe(true)
    expect(surface.action.bmsGuide).not.toBeNull()

    const guide = surface.action.bmsGuide
    // Section 1: Navigation path includes Desigo CC, Site-002, and Chillers
    expect(guide?.navigationPath).toContain('Desigo CC')
    expect(guide?.navigationPath).toContain('Site-002')
    expect(guide?.navigationPath).toContain('Chillers')
    expect(guide?.assetId).toBe('S002-CHILLER-B1-001')

    // Section 2: Command contains equipment-specific instruction
    expect(guide?.command).toContain('chilled-water setpoint')
    expect(guide?.command).toContain('S002-CHILLER-B1-001')

    // Section 3: Verification includes primary metric
    expect(guide?.verification).toContain('chilled-water')
    expect(guide?.verification).toContain('temperature')
    expect(surface.time.label).toBe('Time to Discomfort')
  })

  it('advisory mode handles missing BMS guide gracefully', () => {
    const surface = buildDecisionSurface({
      building_id: 'site-002',
      alert_text: 'System-wide condition detected',
      recommended_action: 'Review telemetry and confirm status',
      building_metadata: { deployment_mode: 'advisory' },
    })

    expect(surface.behavior.showInstructions).toBe(true)
    expect(surface.action.bmsGuide).toBeNull()
    expect(surface.action.operatorPrompt).toBe('Execute this now in the BMS using the mapped navigation path below.')
    expect(surface.action.expectedOutcome).toContain('operator applies')
  })

  it('advisory mode differs from supervised mode rendering', () => {
    const input = {
      building_id: 'site-002',
      primary_asset_id: 'S002-AHU-G-001',
      alert_text: 'Supply-air temperature alarm',
      recommended_action: 'Open AHU controls and adjust damper position',
      time_to_discomfort: 8,
    }

    const advisoryMode = buildDecisionSurface({
      ...input,
      building_metadata: { deployment_mode: 'advisory' },
    })

    const supervisedMode = buildDecisionSurface({
      ...input,
      building_metadata: { deployment_mode: 'supervised' },
    })

    // Advisory mode shows instructions
    expect(advisoryMode.behavior.showInstructions).toBe(true)
    expect(advisoryMode.behavior.showApproval).toBe(false)
    expect(advisoryMode.action.bmsGuide).not.toBeNull()

    // Supervised mode requires approval
    expect(supervisedMode.behavior.showInstructions).toBe(false)
    expect(supervisedMode.behavior.showApproval).toBe(true)
    expect(supervisedMode.action.operatorPrompt).toBe('[HOLD TO APPROVE]')
  })
})
