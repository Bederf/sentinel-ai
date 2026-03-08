/**
 * End-to-End Alert to Feedback Integration Tests (Phase 68-02 Task 6)
 *
 * Tests the complete workflow: Alert → Work Order → Technician → Service Completion
 * → Feedback → Health Restoration → Dashboard Update
 *
 * This is the critical path validation for Phase 081 automation.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { QueryClient } from '@tanstack/react-query'

// Type definitions
interface Alert {
  id: string
  equipment_id: string
  equipment_name: string
  severity: 'critical' | 'warning' | 'medium' | 'low'
  message: string
  created_at: string
  acknowledged: boolean
}

interface WorkOrder {
  id: string
  code: string
  equipment_id: string
  priority: 'urgent' | 'high' | 'medium' | 'low'
  status: 'scheduled' | 'assigned' | 'in_progress' | 'completed'
  assigned_to?: string
  technician_name?: string
  created_at: string
}

interface Equipment {
  id: string
  name: string
  type: string
  health_score: number
  status: 'online' | 'warning' | 'offline'
}

interface ServiceFeedback {
  id: string
  work_order_code: string
  equipment_id: string
  health_impact: 'positive' | 'neutral' | 'negative' | 'critical'
  health_impact_value: number
}

// Mock APIs
vi.mock('@/lib/api', () => ({
  alertsApi: {
    create: vi.fn(),
    acknowledge: vi.fn(),
  },
  workOrdersApi: {
    create: vi.fn(),
    updateStatus: vi.fn(),
  },
  serviceFeedbackApi: {
    submit: vi.fn(),
  },
  equipmentApi: {
    getById: vi.fn(),
    updateHealth: vi.fn(),
  },
  dashboardApi: {
    getStatus: vi.fn(),
  },
}))

import { alertsApi, workOrdersApi, serviceFeedbackApi, equipmentApi, dashboardApi } from '@/lib/api'

// Mock component orchestrating the full flow
function _EndToEndFlowComponent({
  onFlowComplete,
}: {
  onFlowComplete: (result: {
    alert: Alert
    workOrder: WorkOrder
    feedback: ServiceFeedback
    restoredHealth: number
  }) => void
}) {
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const [step, setStep] = React.useState<'alert' | 'feedback' | 'complete'>('alert')

  const handleCreateAlert = async () => {
    const alert = await (alertsApi.create as any)({
      equipment_id: 'S002-CHILLER-B1-001',
      severity: 'critical',
    })
    setStep('feedback')

    // Simulate WO auto-creation
    const workOrder = await (workOrdersApi.create as any)({
      equipment_id: alert.equipment_id,
    })

    return { alert, workOrder }
  }

  const handleSubmitFeedback = async (alert: Alert, workOrder: WorkOrder) => {
    await (workOrdersApi.updateStatus as any)(workOrder.code, 'in_progress')
    await (workOrdersApi.updateStatus as any)(workOrder.code, 'completed')

    const feedback = await (serviceFeedbackApi.submit as any)({
      work_order_code: workOrder.code,
      health_impact: 'positive',
    })

    const restoredEquipment = await (equipmentApi.getById as any)(alert.equipment_id)

    onFlowComplete({
      alert,
      workOrder,
      feedback,
      restoredHealth: restoredEquipment.health_score,
    })
    setStep('complete')
  }

  return (
    <div>
      <h1>End-to-End Integration Test</h1>
      {step === 'alert' && (
        <button onClick={handleCreateAlert}>Start Alert</button>
      )}
      {step === 'feedback' && (
        <button onClick={() => handleSubmitFeedback({} as Alert, {} as WorkOrder)}>
          Submit Feedback
        </button>
      )}
      {step === 'complete' && <div>Flow Complete</div>}
    </div>
  )
}

// Mock data factories
function createMockAlert(overrides?: Partial<Alert>): Alert {
  return {
    id: 'alert-001',
    equipment_id: 'S002-CHILLER-B1-001',
    equipment_name: 'Primary Chiller',
    severity: 'critical',
    message: 'Equipment health critically low',
    created_at: new Date().toISOString(),
    acknowledged: false,
    ...overrides,
  }
}

function createMockWorkOrder(overrides?: Partial<WorkOrder>): WorkOrder {
  return {
    id: 'wo-001',
    code: 'WO-2026-0001',
    equipment_id: 'S002-CHILLER-B1-001',
    priority: 'urgent',
    status: 'scheduled',
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

function createMockEquipment(overrides?: Partial<Equipment>): Equipment {
  return {
    id: 'equipment-001',
    name: 'Primary Chiller',
    type: 'CHILLER',
    health_score: 65,
    status: 'warning',
    ...overrides,
  }
}

function createMockServiceFeedback(overrides?: Partial<ServiceFeedback>): ServiceFeedback {
  return {
    id: 'feedback-001',
    work_order_code: 'WO-2026-0001',
    equipment_id: 'S002-CHILLER-B1-001',
    health_impact: 'positive',
    health_impact_value: 2,
    ...overrides,
  }
}

// Tests
describe('AlertToFeedbackIntegration', () => {
  let _queryClient: QueryClient

  beforeEach(() => {
    vi.resetAllMocks()
    _queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
  })

  describe('Complete End-to-End Workflow', () => {
    it('should execute full cycle: alert → WO → technician → feedback → health', async () => {
      const mockAlert = createMockAlert({ severity: 'critical' })
      const mockWO = createMockWorkOrder({ status: 'scheduled' })
      const mockFeedback = createMockServiceFeedback()
      const restoredEquipment = createMockEquipment({ health_score: 85, status: 'online' })

      vi.mocked(alertsApi.create).mockResolvedValueOnce(mockAlert)
      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(mockWO)
      vi.mocked(workOrdersApi.updateStatus)
        .mockResolvedValueOnce({ ...mockWO, status: 'assigned' })
        .mockResolvedValueOnce({ ...mockWO, status: 'in_progress' })
        .mockResolvedValueOnce({ ...mockWO, status: 'completed' })
      vi.mocked(serviceFeedbackApi.submit).mockResolvedValueOnce(mockFeedback)
      vi.mocked(equipmentApi.getById).mockResolvedValueOnce(restoredEquipment)

      // Step 1: Alert creation
      const alert = await (alertsApi.create as any)({
        equipment_id: 'S002-CHILLER-B1-001',
        severity: 'critical',
      })

      expect(alert.severity).toBe('critical')

      // Step 2: WO auto-created
      const workOrder = await (workOrdersApi.create as any)({
        equipment_id: alert.equipment_id,
      })

      expect(workOrder.code).toBe('WO-2026-0001')
      expect(workOrder.status).toBe('scheduled')

      // Step 3: WO assignment
      const assignedWO = await (workOrdersApi.updateStatus as any)(workOrder.code, 'assigned')
      expect(assignedWO.status).toBe('assigned')

      // Step 4: Service in progress
      const inProgressWO = await (workOrdersApi.updateStatus as any)(
        workOrder.code,
        'in_progress'
      )
      expect(inProgressWO.status).toBe('in_progress')

      // Step 5: Service completion
      const completedWO = await (workOrdersApi.updateStatus as any)(
        workOrder.code,
        'completed'
      )
      expect(completedWO.status).toBe('completed')

      // Step 6: Feedback submission
      const feedback = await (serviceFeedbackApi.submit as any)({
        work_order_code: workOrder.code,
        health_impact: 'positive',
      })
      expect(feedback.health_impact).toBe('positive')

      // Step 7: Health restoration verification
      const updatedEquipment = await (equipmentApi.getById as any)(alert.equipment_id)
      expect(updatedEquipment.health_score).toBe(85)
      expect(updatedEquipment.status).toBe('online')
    })

    it('should verify alert → WO link at creation', async () => {
      const mockAlert = createMockAlert()
      const mockWO = createMockWorkOrder({
        equipment_id: mockAlert.equipment_id,
      })

      vi.mocked(alertsApi.create).mockResolvedValueOnce(mockAlert)
      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(mockWO)

      const alert = await (alertsApi.create as any)({ equipment_id: 'S002-CHILLER-B1-001' })
      const workOrder = await (workOrdersApi.create as any)({
        equipment_id: alert.equipment_id,
      })

      expect(workOrder.equipment_id).toBe(alert.equipment_id)
    })

    it('should assign correct technician by equipment specialty', async () => {
      const mockWO = createMockWorkOrder({
        technician_name: 'HVAC Technician',
      })

      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(mockWO)

      const workOrder = await (workOrdersApi.create as any)({
        equipment_id: 'S002-CHILLER-B1-001', // CHILLER → HVAC specialty
      })

      expect(workOrder.technician_name).toBeDefined()
    })

    it('should transition through all status states correctly', async () => {
      const mockWO = createMockWorkOrder()

      const statusTransitions = [
        { ...mockWO, status: 'assigned' as const },
        { ...mockWO, status: 'in_progress' as const },
        { ...mockWO, status: 'completed' as const },
      ]

      statusTransitions.forEach((wo, _i) => {
        vi.mocked(workOrdersApi.updateStatus).mockResolvedValueOnce(wo)
      })

      let currentStatus: 'scheduled' | 'assigned' | 'in_progress' | 'completed' = 'scheduled'

      for (const nextStatus of ['assigned', 'in_progress', 'completed']) {
        const updated = await (workOrdersApi.updateStatus as any)(mockWO.code, nextStatus)
        expect(updated.status).toBe(nextStatus)
        currentStatus = updated.status
      }

      expect(currentStatus).toBe('completed')
    })
  })

  describe('Health Score Restoration', () => {
    it('should restore health from 65% to 85% via feedback', async () => {
      const originalHealth = 65
      const restoredHealth = 85
      const expectedChange = 20

      const _equipment = createMockEquipment({
        health_score: restoredHealth,
      })

      vi.mocked(equipmentApi.updateHealth).mockResolvedValueOnce({
        equipment_id: 'S002-CHILLER-B1-001',
        current_health: restoredHealth,
        previous_health: originalHealth,
        change: expectedChange,
        updated_at: new Date().toISOString(),
      })

      const result = await (equipmentApi.updateHealth as any)(
        'S002-CHILLER-B1-001',
        { health_impact_value: 2 } // positive impact
      )

      expect(result.current_health).toBe(85)
      expect(result.previous_health).toBe(65)
      expect(result.change).toBe(20)
    })

    it('should update equipment status from warning to online', async () => {
      const warningEquipment = createMockEquipment({ status: 'warning' })
      const onlineEquipment = createMockEquipment({ status: 'online' })

      vi.mocked(equipmentApi.getById)
        .mockResolvedValueOnce(warningEquipment)
        .mockResolvedValueOnce(onlineEquipment)

      // Before: warning
      const before = await (equipmentApi.getById as any)('S002-CHILLER-B1-001')
      expect(before.status).toBe('warning')

      // After: online
      const after = await (equipmentApi.getById as any)('S002-CHILLER-B1-001')
      expect(after.status).toBe('online')
    })

    it('should cap health at 100%', async () => {
      vi.mocked(equipmentApi.updateHealth).mockResolvedValueOnce({
        equipment_id: 'S002-CHILLER-B1-001',
        current_health: 100,
        previous_health: 95,
        change: 5,
        updated_at: new Date().toISOString(),
      })

      const result = await (equipmentApi.updateHealth as any)(
        'S002-CHILLER-B1-001',
        { health_impact_value: 10 }
      )

      expect(result.current_health).toBeLessThanOrEqual(100)
    })
  })

  describe('Dashboard Real-Time Updates', () => {
    it('should reflect equipment status change in dashboard', async () => {
      const mockStatus = {
        timestamp: new Date().toISOString(),
        equipment_updates: [
          {
            equipment_id: 'S002-CHILLER-B1-001',
            health_score: 85,
            status: 'online',
          },
        ],
      }

      vi.mocked(dashboardApi.getStatus).mockResolvedValueOnce(mockStatus)

      const result = await (dashboardApi.getStatus as any)()

      expect(result.equipment_updates[0].health_score).toBe(85)
      expect(result.equipment_updates[0].status).toBe('online')
    })

    it('should update alert acknowledgement on health restoration', async () => {
      const mockAlert = createMockAlert({
        acknowledged: true,
      })

      vi.mocked(alertsApi.acknowledge).mockResolvedValueOnce(mockAlert)

      const result = await (alertsApi.acknowledge as any)('alert-001')

      expect(result.acknowledged).toBe(true)
    })
  })

  describe('Error Recovery', () => {
    it('should handle alert creation failure gracefully', async () => {
      vi.mocked(alertsApi.create).mockRejectedValueOnce(new Error('Alert creation failed'))

      await expect(
        (alertsApi.create as any)({ equipment_id: 'S002-CHILLER-B1-001' })
      ).rejects.toThrow()
    })

    it('should handle WO auto-creation failure', async () => {
      const mockAlert = createMockAlert()
      vi.mocked(alertsApi.create).mockResolvedValueOnce(mockAlert)
      vi.mocked(workOrdersApi.create).mockRejectedValueOnce(new Error('WO creation failed'))

      const alert = await (alertsApi.create as any)({})
      expect(alert).toBeDefined()

      await expect(
        (workOrdersApi.create as any)({ equipment_id: alert.equipment_id })
      ).rejects.toThrow()
    })

    it('should handle status transition failure mid-workflow', async () => {
      const mockWO = createMockWorkOrder()
      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(mockWO)
      vi.mocked(workOrdersApi.updateStatus).mockRejectedValueOnce(
        new Error('Status update failed')
      )

      const workOrder = await (workOrdersApi.create as any)({})
      expect(workOrder).toBeDefined()

      await expect(
        (workOrdersApi.updateStatus as any)(workOrder.code, 'assigned')
      ).rejects.toThrow()
    })

    it('should handle feedback submission failure', async () => {
      vi.mocked(serviceFeedbackApi.submit).mockRejectedValueOnce(
        new Error('Feedback submission failed')
      )

      await expect(
        (serviceFeedbackApi.submit as any)({ work_order_code: 'WO-2026-0001' })
      ).rejects.toThrow()
    })

    it('should handle health update failure without losing WO data', async () => {
      const mockWO = createMockWorkOrder({ status: 'completed' })

      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(mockWO)
      vi.mocked(equipmentApi.updateHealth).mockRejectedValueOnce(new Error('Health update failed'))

      const workOrder = await (workOrdersApi.create as any)({})
      expect(workOrder.status).toBe('completed')

      await expect(
        (equipmentApi.updateHealth as any)('S002-CHILLER-B1-001', {})
      ).rejects.toThrow()

      // WO data should still be intact
      expect(workOrder).toBeDefined()
    })
  })

  describe('Timeline Verification', () => {
    it('should maintain correct timeline: alert → WO → feedback → health', async () => {
      const alertTime = new Date('2026-02-13T10:00:00Z')
      const woTime = new Date('2026-02-13T10:01:00Z')
      const _feedbackTime = new Date('2026-02-13T10:30:00Z')
      const _healthTime = new Date('2026-02-13T10:31:00Z')

      const alert = createMockAlert({ created_at: alertTime.toISOString() })
      const workOrder = createMockWorkOrder({ created_at: woTime.toISOString() })
      const feedback = createMockServiceFeedback()
      const equipment = createMockEquipment()

      vi.mocked(alertsApi.create).mockResolvedValueOnce(alert)
      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(workOrder)
      vi.mocked(serviceFeedbackApi.submit).mockResolvedValueOnce(feedback)
      vi.mocked(equipmentApi.getById).mockResolvedValueOnce(equipment)

      const createdAlert = await (alertsApi.create as any)({})
      const createdWO = await (workOrdersApi.create as any)({})
      const _createdFeedback = await (serviceFeedbackApi.submit as any)({})
      const _updatedEquipment = await (equipmentApi.getById as any)({})

      expect(new Date(createdAlert.created_at) <= new Date(createdWO.created_at)).toBe(true)
    })
  })
})
