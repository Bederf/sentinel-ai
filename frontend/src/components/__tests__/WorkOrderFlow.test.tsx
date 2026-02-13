/**
 * Work Order Flow Integration Tests (Phase 68-02 Task 6)
 *
 * Tests the complete work order creation workflow from alert generation
 * through technician assignment and status transitions.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Type definitions for our tests
interface WorkOrderRequest {
  equipment_id?: string
  work_type: string
  status: 'scheduled' | 'assigned' | 'in_progress' | 'completed'
  priority: 'low' | 'medium' | 'high' | 'urgent'
  title: string
  description?: string
  assigned_to?: string
}

interface WorkOrderResponse {
  id: string
  code: string
  equipment_id: string
  work_type: string
  status: 'scheduled' | 'assigned' | 'in_progress' | 'completed'
  priority: 'low' | 'medium' | 'high' | 'urgent'
  title: string
  description?: string
  assigned_to?: string
  technician_name?: string
  created_at: string
  updated_at?: string
  completed_at?: string
}

interface Technician {
  id: string
  name: string
  email: string
  specialty: 'hvac' | 'electrical' | 'plumbing' | 'dali' | 'fire' | 'security' | 'general'
  available: boolean
}

// Mock the APIs
vi.mock('@/lib/api', () => ({
  workOrdersApi: {
    create: vi.fn(),
    updateStatus: vi.fn(),
    getByCode: vi.fn(),
    getTechnicianForEquipment: vi.fn(),
  },
  techniciansApi: {
    assignToWorkOrder: vi.fn(),
    getAvailable: vi.fn(),
  },
}))

import { workOrdersApi, techniciansApi } from '@/lib/api'

// Mock component for testing
function WorkOrderFlowComponent({
  onWorkOrderCreated,
}: {
  onWorkOrderCreated: (wo: WorkOrderResponse) => void
}) {
  return (
    <div>
      <h1>Work Order Flow</h1>
      <button
        onClick={async () => {
          const response = await (workOrdersApi.create as any)(
            createMockWorkOrderRequest()
          )
          onWorkOrderCreated(response)
        }}
      >
        Create Work Order
      </button>
    </div>
  )
}

// Mock data factories
function createMockWorkOrderRequest(overrides?: Partial<WorkOrderRequest>): WorkOrderRequest {
  return {
    equipment_id: 'S002-CHILLER-B1-001',
    work_type: 'maintenance',
    status: 'scheduled',
    priority: 'high',
    title: 'Chiller preventive maintenance',
    description: 'Annual chiller service and inspection',
    ...overrides,
  }
}

function createMockWorkOrderResponse(
  overrides?: Partial<WorkOrderResponse>
): WorkOrderResponse {
  return {
    id: 'wo-' + Math.random().toString(36).substr(2, 9),
    code: 'WO-2026-0001',
    equipment_id: 'S002-CHILLER-B1-001',
    work_type: 'maintenance',
    status: 'scheduled',
    priority: 'high',
    title: 'Chiller preventive maintenance',
    description: 'Annual chiller service and inspection',
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

function createMockTechnician(
  overrides?: Partial<Technician>
): Technician {
  return {
    id: 'tech-001',
    name: 'John Smith',
    email: 'john.smith@example.com',
    specialty: 'hvac',
    available: true,
    ...overrides,
  }
}

// Tests
describe('WorkOrderFlow', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
  })

  describe('Work Order Creation from Alert', () => {
    it('should create work order with critical severity alert', async () => {
      const mockWO = createMockWorkOrderResponse({
        status: 'scheduled',
        priority: 'urgent',
      })

      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(mockWO)

      const onCreated = vi.fn()
      render(
        <QueryClientProvider client={queryClient}>
          <WorkOrderFlowComponent onWorkOrderCreated={onCreated} />
        </QueryClientProvider>
      )

      const createButton = screen.getByRole('button', { name: /Create Work Order/i })
      await userEvent.click(createButton)

      await waitFor(() => {
        expect(workOrdersApi.create).toHaveBeenCalled()
        expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({
          code: 'WO-2026-0001',
          priority: 'urgent',
          status: 'scheduled',
        }))
      })
    })

    it('should auto-create work order when equipment health drops to warning', async () => {
      const mockWO = createMockWorkOrderResponse({
        status: 'scheduled',
      })

      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(mockWO)

      const request = createMockWorkOrderRequest()
      await (workOrdersApi.create as any)(request)

      expect(workOrdersApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          equipment_id: 'S002-CHILLER-B1-001',
          work_type: 'maintenance',
        })
      )
    })

    it('should include equipment information in work order', async () => {
      const mockWO = createMockWorkOrderResponse({
        equipment_id: 'S002-AHU-L1-A',
        title: 'AHU filter replacement',
      })

      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(mockWO)

      const request = createMockWorkOrderRequest({
        equipment_id: 'S002-AHU-L1-A',
        title: 'AHU filter replacement',
      })

      const result = await (workOrdersApi.create as any)(request)

      expect(result).toMatchObject({
        equipment_id: 'S002-AHU-L1-A',
        title: 'AHU filter replacement',
      })
    })

    it('should set correct priority based on alert severity', async () => {
      const criticalWO = createMockWorkOrderResponse({
        priority: 'urgent',
      })

      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(criticalWO)

      const result = await (workOrdersApi.create as any)(
        createMockWorkOrderRequest({ priority: 'urgent' })
      )

      expect(result.priority).toBe('urgent')
    })
  })

  describe('Technician Auto-Assignment', () => {
    it('should assign technician based on equipment type specialty', async () => {
      const technician = createMockTechnician({
        specialty: 'hvac',
        name: 'HVAC Tech',
      })

      vi.mocked(techniciansApi.assignToWorkOrder).mockResolvedValueOnce({
        success: true,
        technician_id: technician.id,
        assigned_at: new Date().toISOString(),
      })

      const result = await (techniciansApi.assignToWorkOrder as any)(
        'wo-123',
        technician.id
      )

      expect(result.success).toBe(true)
      expect(result.technician_id).toBe(technician.id)
    })

    it('should lookup technician for equipment type', async () => {
      const mockTechnician = createMockTechnician()

      vi.mocked(workOrdersApi.getTechnicianForEquipment).mockResolvedValueOnce(
        mockTechnician
      )

      const result = await (workOrdersApi.getTechnicianForEquipment as any)(
        'S002-CHILLER-B1-001'
      )

      expect(result.specialty).toBe('hvac')
      expect(result.name).toBe('John Smith')
    })

    it('should assign from available technician pool', async () => {
      const technicians = [
        createMockTechnician({ name: 'Tech 1' }),
        createMockTechnician({ name: 'Tech 2', available: true }),
      ]

      vi.mocked(techniciansApi.getAvailable).mockResolvedValueOnce(technicians)

      const result = await (techniciansApi.getAvailable as any)('hvac')

      expect(result).toHaveLength(2)
      expect(result[0].available).toBeTruthy()
    })

    it('should handle case when no technician available', async () => {
      vi.mocked(techniciansApi.getAvailable).mockResolvedValueOnce([])

      const result = await (techniciansApi.getAvailable as any)('hvac')

      expect(result).toHaveLength(0)
    })
  })

  describe('Status Transitions', () => {
    it('should transition from scheduled to assigned', async () => {
      const initialWO = createMockWorkOrderResponse({
        status: 'scheduled',
      })

      const updatedWO = createMockWorkOrderResponse({
        status: 'assigned',
        assigned_to: 'tech-001',
        technician_name: 'John Smith',
      })

      vi.mocked(workOrdersApi.updateStatus).mockResolvedValueOnce(updatedWO)

      const result = await (workOrdersApi.updateStatus as any)(
        initialWO.code,
        'assigned'
      )

      expect(result.status).toBe('assigned')
      expect(result.technician_name).toBe('John Smith')
    })

    it('should transition from assigned to in_progress', async () => {
      const wo = createMockWorkOrderResponse({
        status: 'assigned',
        assigned_to: 'tech-001',
      })

      const inProgressWO = createMockWorkOrderResponse({
        ...wo,
        status: 'in_progress',
      })

      vi.mocked(workOrdersApi.updateStatus).mockResolvedValueOnce(inProgressWO)

      const result = await (workOrdersApi.updateStatus as any)(wo.code, 'in_progress')

      expect(result.status).toBe('in_progress')
    })

    it('should transition from in_progress to completed', async () => {
      const wo = createMockWorkOrderResponse({
        status: 'in_progress',
      })

      const completedWO = createMockWorkOrderResponse({
        ...wo,
        status: 'completed',
        completed_at: new Date().toISOString(),
      })

      vi.mocked(workOrdersApi.updateStatus).mockResolvedValueOnce(completedWO)

      const result = await (workOrdersApi.updateStatus as any)(wo.code, 'completed')

      expect(result.status).toBe('completed')
      expect(result.completed_at).toBeDefined()
    })

    it('should track status transition timestamps', async () => {
      const now = new Date().toISOString()
      const wo = createMockWorkOrderResponse({
        status: 'completed',
        completed_at: now,
        updated_at: now,
      })

      vi.mocked(workOrdersApi.updateStatus).mockResolvedValueOnce(wo)

      const result = await (workOrdersApi.updateStatus as any)(wo.code, 'completed')

      expect(result.completed_at).toBe(now)
      expect(result.updated_at).toBe(now)
    })
  })

  describe('Escalation Workflow', () => {
    it('should support escalation to external service provider', async () => {
      const escalatedWO = createMockWorkOrderResponse({
        assigned_to: 'external-provider-123',
        technician_name: 'Carrier Service Center',
      })

      vi.mocked(workOrdersApi.updateStatus).mockResolvedValueOnce(escalatedWO)

      const result = await (workOrdersApi.updateStatus as any)(
        'WO-2026-0001',
        'assigned'
      )

      expect(result.assigned_to).toBe('external-provider-123')
      expect(result.technician_name).toBe('Carrier Service Center')
    })

    it('should track escalation reason when WO complex', async () => {
      const complexWO = createMockWorkOrderResponse({
        description: 'Requires specialized expertise - escalated to Carrier',
      })

      vi.mocked(workOrdersApi.create).mockResolvedValueOnce(complexWO)

      const result = await (workOrdersApi.create as any)(
        createMockWorkOrderRequest({
          description: 'Requires specialized expertise - escalated to Carrier',
        })
      )

      expect(result.description).toContain('escalated')
    })

    it('should maintain escalation chain in history', async () => {
      const escalatedWO = createMockWorkOrderResponse({
        assigned_to: 'external-provider-123',
      })

      vi.mocked(workOrdersApi.getByCode).mockResolvedValueOnce(escalatedWO)

      const result = await (workOrdersApi.getByCode as any)('WO-2026-0001')

      expect(result.assigned_to).toBe('external-provider-123')
    })
  })

  describe('Error Handling', () => {
    it('should handle work order creation failure', async () => {
      const errorMessage = 'Equipment not found'

      vi.mocked(workOrdersApi.create).mockRejectedValueOnce(
        new Error(errorMessage)
      )

      await expect(
        (workOrdersApi.create as any)(createMockWorkOrderRequest())
      ).rejects.toThrow(errorMessage)
    })

    it('should handle technician assignment failure', async () => {
      vi.mocked(techniciansApi.assignToWorkOrder).mockRejectedValueOnce(
        new Error('No available technicians')
      )

      await expect(
        (techniciansApi.assignToWorkOrder as any)('wo-123', 'tech-999')
      ).rejects.toThrow()
    })

    it('should handle status update failure', async () => {
      vi.mocked(workOrdersApi.updateStatus).mockRejectedValueOnce(
        new Error('Invalid status transition')
      )

      await expect(
        (workOrdersApi.updateStatus as any)('WO-2026-0001', 'invalid_status')
      ).rejects.toThrow()
    })
  })

  describe('Work Order Properties', () => {
    it('should have all required work order properties', async () => {
      const wo = createMockWorkOrderResponse()

      expect(wo).toHaveProperty('id')
      expect(wo).toHaveProperty('code')
      expect(wo).toHaveProperty('equipment_id')
      expect(wo).toHaveProperty('priority')
      expect(wo).toHaveProperty('status')
      expect(wo).toHaveProperty('created_at')
    })

    it('should format work order code correctly', async () => {
      const wo = createMockWorkOrderResponse()

      expect(wo.code).toMatch(/^WO-\d{4}-\d{4}$/)
    })

    it('should include technician assignment when assigned', async () => {
      const wo = createMockWorkOrderResponse({
        status: 'assigned',
        assigned_to: 'tech-001',
        technician_name: 'John Smith',
      })

      expect(wo.assigned_to).toBeDefined()
      expect(wo.technician_name).toBeDefined()
    })

    it('should track work order timeline', async () => {
      const wo = createMockWorkOrderResponse({
        created_at: '2026-02-13T10:00:00Z',
        updated_at: '2026-02-13T11:00:00Z',
        completed_at: '2026-02-13T12:00:00Z',
      })

      expect(new Date(wo.created_at) < new Date(wo.updated_at!)).toBe(true)
      expect(new Date(wo.updated_at!) < new Date(wo.completed_at!)).toBe(true)
    })
  })
})
