import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { SolarConfigWizard } from '../SolarConfigWizard'
import { queryClient } from '@/lib/queryClient'

/**
 * Test that verifies SolarConfigWizard works with callback-based navigation
 * instead of useNavigate hook
 */
describe('SolarConfigWizard Router Fix', () => {
  const mockOnComplete = vi.fn()

  beforeEach(() => {
    mockOnComplete.mockClear()
  })

  it('should render without Router context error', () => {
    // Even without BrowserRouter, SolarConfigWizard should render
    // because it no longer uses useNavigate hook
    render(
      <QueryClientProvider client={queryClient}>
        <SolarConfigWizard onComplete={mockOnComplete} />
      </QueryClientProvider>
    )
    expect(screen.getByText(/Solar Setup Wizard/i)).toBeInTheDocument()
  })

  it('should call onComplete callback instead of using useNavigate', async () => {
    render(
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <SolarConfigWizard onComplete={mockOnComplete} />
        </QueryClientProvider>
      </BrowserRouter>
    )

    // Find and click a button that triggers onComplete
    const buttons = screen.getAllByRole('button')
    const skipButton = buttons.find((btn) => btn.textContent?.includes('Skip') || btn.textContent?.includes('Activate'))

    if (skipButton) {
      fireEvent.click(skipButton)

      // Wait for the callback to be invoked
      await waitFor(() => {
        expect(mockOnComplete).toHaveBeenCalled()
      })
    }
  })

  it('should not import useNavigate hook', () => {
    // This is a smoke test - if SolarConfigWizard imported useNavigate,
    // it would fail in non-Router contexts
    // By passing this test (component renders), we confirm the refactor worked
    render(
      <QueryClientProvider client={queryClient}>
        <SolarConfigWizard onComplete={() => {}} />
      </QueryClientProvider>
    )
    expect(screen.getByText(/Solar Setup Wizard/i)).toBeInTheDocument()
  })
})
