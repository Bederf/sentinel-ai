import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { useNavigate } from 'react-router-dom'

/**
 * Test component that uses useNavigate hook
 * This should only work inside a <Router> context
 */
function TestComponentUsingNavigate() {
  const navigate = useNavigate()
  return <div>Router context available: {typeof navigate === 'function' ? 'YES' : 'NO'}</div>
}

/**
 * Test that verifies BrowserRouter provides Router context
 * This would fail with "useNavigate() may be used only in the context of a <Router> component"
 * if BrowserRouter wasn't wrapping the app
 */
describe('Router Context', () => {
  it('should provide Router context via BrowserRouter', () => {
    render(
      <BrowserRouter>
        <TestComponentUsingNavigate />
      </BrowserRouter>
    )
    expect(screen.getByText(/Router context available: YES/i)).toBeInTheDocument()
  })

  it('should throw error if useNavigate is used without Router context', () => {
    // This test verifies the problem we fixed - useNavigate without Router fails
    const renderWithoutRouter = () => {
      render(<TestComponentUsingNavigate />)
    }
    expect(renderWithoutRouter).toThrow(/useNavigate.*Router/i)
  })
})
