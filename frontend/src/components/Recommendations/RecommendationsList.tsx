/**
 * RecommendationsList Component
 *
 * Features:
 * - Display list of pending recommendations
 * - Integrate ApprovalDialog for tier-2 approval workflow
 * - Show equipment details, confidence, and risk level
 * - Handle approval/rejection with side effects (refresh list, etc)
 * - Empty state messaging
 * - Loading and error states
 */

import React, { useState } from 'react'
import { CheckCircle, XCircle, AlertTriangle, ChevronRight } from 'lucide-react'
import { ApprovalDialog, type Recommendation } from './ApprovalDialog'
import type { ApprovalResponse } from '@/lib/api/approvals'

interface RecommendationsListProps {
  recommendations: Recommendation[]
  isLoading?: boolean
  error?: string | null
  onApproved?: (result: ApprovalResponse) => void
  onRejected?: (result: ApprovalResponse) => void
}

export const RecommendationsList: React.FC<RecommendationsListProps> = ({
  recommendations,
  isLoading = false,
  error = null,
  onApproved,
  onRejected,
}) => {
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  const handleOpenDialog = (rec: Recommendation) => {
    setSelectedRec(rec)
    setIsDialogOpen(true)
  }

  const handleApprove = (result: ApprovalResponse) => {
    setIsDialogOpen(false)
    setSelectedRec(null)
    onApproved?.(result)
  }

  const handleReject = (result: ApprovalResponse) => {
    setIsDialogOpen(false)
    setSelectedRec(null)
    onRejected?.(result)
  }

  const getConfidenceColor = (confidence?: string) => {
    switch (confidence?.toLowerCase()) {
      case 'high':
        return 'bg-green-900/20 text-green-300'
      case 'medium':
        return 'bg-yellow-900/20 text-yellow-300'
      case 'low':
        return 'bg-red-900/20 text-red-300'
      default:
        return 'bg-blue-900/20 text-blue-300'
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-24 bg-gray-800 rounded-lg animate-pulse border border-gray-700"
          />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 bg-red-900/20 border border-red-700 rounded-lg flex items-start gap-2 text-sm text-red-300">
        <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
        <div>
          <p className="font-medium">Error loading recommendations</p>
          <p className="mt-1">{error}</p>
        </div>
      </div>
    )
  }

  if (recommendations.length === 0) {
    return (
      <div className="p-8 text-center bg-gray-800/50 border border-gray-700 rounded-lg">
        <CheckCircle className="w-12 h-12 text-green-400 mx-auto mb-3 opacity-50" />
        <p className="text-gray-300">No pending recommendations</p>
        <p className="text-sm text-gray-500 mt-1">
          All equipment is operating within expected parameters
        </p>
      </div>
    )
  }

  return (
    <>
      <div className="space-y-3">
        {recommendations.map((rec) => (
          <div
            key={rec.id}
            className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 hover:border-gray-600 transition-colors"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                {/* Equipment */}
                <h3 className="font-semibold text-white truncate">
                  {rec.target_equipment}
                </h3>

                {/* Action */}
                {rec.action && (
                  <p className="text-sm text-gray-400 mt-1">
                    {rec.action.point} → {rec.action.value}
                  </p>
                )}

                {/* Reason */}
                {rec.reason && (
                  <p className="text-sm text-gray-300 mt-2 line-clamp-2">
                    {rec.reason}
                  </p>
                )}

                {/* Metadata */}
                <div className="flex items-center gap-2 mt-3 flex-wrap">
                  <span className={`text-xs font-medium px-2 py-1 rounded ${getConfidenceColor(rec.confidence)}`}>
                    {rec.confidence || 'medium'} confidence
                  </span>
                  {rec.description && (
                    <span className="text-xs text-gray-500">
                      {rec.description}
                    </span>
                  )}
                </div>
              </div>

              {/* Approve Button */}
              <button
                onClick={() => handleOpenDialog(rec)}
                className="flex-shrink-0 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium text-sm flex items-center gap-1 transition-colors whitespace-nowrap"
              >
                Approve
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Approval Dialog */}
      <ApprovalDialog
        recommendation={selectedRec}
        isOpen={isDialogOpen}
        onApprove={handleApprove}
        onReject={handleReject}
        onClose={() => {
          setIsDialogOpen(false)
          setSelectedRec(null)
        }}
      />
    </>
  )
}
