/**
 * FooterConfirmation: Operator confirmation footer
 */

export function FooterConfirmation() {
  return (
    <div className="rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 p-4">
      <p className="text-sm text-green-900 dark:text-green-300">
        <span className="font-semibold">Execute now in the BMS</span> using the steps above, then verify the{' '}
        <span className="font-semibold">primary metric improves</span> in the next telemetry update.
      </p>
    </div>
  )
}
