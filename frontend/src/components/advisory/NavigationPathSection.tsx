/**
 * NavigationPathSection: BMS navigation path display
 */

interface NavigationPathSectionProps {
  navigationPath: string[] | null
}

export function NavigationPathSection({ navigationPath }: NavigationPathSectionProps) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
          BMS Navigation
        </p>
      </div>
      <div className="px-4 py-4">
        {navigationPath && navigationPath.length > 0 ? (
          <div className="space-y-2">
            {/* Breadcrumb view */}
            <div className="flex flex-wrap items-center gap-2 text-sm font-mono text-gray-900 dark:text-white">
              {navigationPath.map((step, index) => (
                <div key={`${step}-${index}`} className="flex items-center gap-2">
                  <span className="px-2 py-1 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                    {step}
                  </span>
                  {index < navigationPath.length - 1 && (
                    <span className="text-gray-400 dark:text-gray-600">&gt;</span>
                  )}
                </div>
              ))}
            </div>

            {/* Numbered list for clarity */}
            <div className="mt-3 space-y-1">
              {navigationPath.map((step, index) => (
                <div
                  key={`list-${step}-${index}`}
                  className="flex items-start gap-3 text-sm text-gray-700 dark:text-gray-300"
                >
                  <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-gray-200 dark:bg-gray-700 text-xs font-semibold flex-shrink-0">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400 italic">
            BMS navigation path not available. Contact support for mapping.
          </p>
        )}
      </div>
    </div>
  )
}
