import { Component, type ErrorInfo, type ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
  /** Optional fallback label — defaults to 'Twin canvas unavailable' */
  label?: string
}

interface State {
  hasError: boolean
  errorMessage: string | null
}

/**
 * CockpitTwinErrorBoundary
 *
 * Wraps the twin canvas (Three.js / SVG / lite) in a componentDidCatch boundary.
 * Catches WebGL context loss, Three.js init failures, and mobile battery-saver
 * crashes without taking down the entire CockpitView.
 *
 * Usage:
 *   <CockpitTwinErrorBoundary>
 *     {canvas}
 *   </CockpitTwinErrorBoundary>
 */
export class CockpitTwinErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, errorMessage: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      errorMessage: error?.message ?? 'Unknown render error',
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface to console — Sentry/Grafana will pick this up via existing error transport
    console.error('[CockpitTwinErrorBoundary] Twin canvas crashed:', error, info.componentStack)
  }

  handleRetry = () => {
    this.setState({ hasError: false, errorMessage: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full w-full flex-col items-center justify-center rounded-md border border-white/8 bg-black/20 px-6 py-8 text-center">
          <div className="mb-3 text-[10px] uppercase tracking-[0.24em] text-slate-500">
            {this.props.label ?? 'Twin canvas unavailable'}
          </div>
          <p className="mb-5 max-w-xs text-xs leading-5 text-slate-400">
            The building twin failed to render. This may be caused by a WebGL context loss or
            unsupported GPU on this device.
          </p>
          {this.state.errorMessage && (
            <p className="mb-5 font-mono text-[10px] text-slate-600">
              {this.state.errorMessage}
            </p>
          )}
          <button
            type="button"
            onClick={this.handleRetry}
            className="flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-slate-300 transition hover:border-white/40"
          >
            <RefreshCw className="h-3 w-3" />
            Retry
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
