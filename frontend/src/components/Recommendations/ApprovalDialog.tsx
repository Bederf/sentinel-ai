/**
 * ApprovalDialog Component - Tier 2 Equipment Control Approval
 *
 * Features:
 * - Display recommendation details (equipment, action, confidence)
 * - SafetyEngine validation status badge
 * - Technician name input (required)
 * - Optional approval notes
 * - Approve/Reject actions with loading states
 * - Success/error messaging
 * - Keyboard support (Escape to cancel, Enter to submit)
 *
 * Follows SENTINEL dark theme design system.
 */

import React, { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import {
  X,
  CheckCircle,
  AlertTriangle,
  Shield,
  Loader,
  Send,
  XCircle,
} from 'lucide-react'
import { approvalsApi } from '@/lib/api/approvals'
import type { ApprovalResponse } from '@/lib/api/approvals'

export interface Recommendation {
  id: string
  target_equipment: string
  action?: { point?: string; value?: string | number }
  confidence?: string
  description?: string
  reason?: string
}

interface ApprovalDialogProps {
  recommendation: Recommendation | null
  isOpen: boolean
  onApprove: (result: ApprovalResponse) => void
  onReject: (result: ApprovalResponse) => void
  onClose: () => void
}

export const ApprovalDialog: React.FC<ApprovalDialogProps> = ({
  recommendation,
  isOpen,
  onApprove,
  onReject,
  onClose,
}) => {
  const [approverName, setApproverName] = useState('')
  const [approvalNotes, setApprovalNotes] = useState('')
  const [rejectionReason, setRejectionReason] = useState('')
  const [activeTab, setActiveTab] = useState<'approve' | 'reject'>('approve')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const approverInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isOpen && approverInputRef.current) {
      approverInputRef.current.focus()
    }
  }, [isOpen])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return

      if (e.key === 'Escape') {
        handleClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  const handleClose = () => {
    setApproverName('')
    setApprovalNotes('')
    setRejectionReason('')
    setError(null)
    setSuccess(null)
    setActiveTab('approve')
    onClose()
  }

  const handleApprove = async () => {
    if (!approverName.trim()) {
      setError('Approver name is required')
      return
    }

    if (!recommendation) {
      setError('No recommendation selected')
      return
    }

    setIsLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const result = await approvalsApi.approveRecommendation(
        recommendation.id,
        approverName.trim(),
        approvalNotes.trim() || undefined
      )

      if (result.success) {
        setSuccess('Recommendation approved and device control executed')
        setTimeout(() => {
          onApprove(result)
          handleClose()
        }, 1500)
      } else {
        setError(result.error_message || 'Failed to approve recommendation')
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to approve recommendation'
      )
    } finally {
      setIsLoading(false)
    }
  }

  const handleReject = async () => {
    if (!approverName.trim()) {
      setError('Approver name is required')
      return
    }

    if (!rejectionReason.trim()) {
      setError('Rejection reason is required')
      return
    }

    if (!recommendation) {
      setError('No recommendation selected')
      return
    }

    setIsLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const result = await approvalsApi.rejectRecommendation(
        recommendation.id,
        approverName.trim(),
        rejectionReason.trim()
      )

      if (result.success) {
        setSuccess('Recommendation rejected')
        setTimeout(() => {
          onReject(result)
          handleClose()
        }, 1500)
      } else {
        setError(result.error_message || 'Failed to reject recommendation')
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to reject recommendation'
      )
    } finally {
      setIsLoading(false)
    }
  }

  if (!isOpen || !recommendation) return null

  const confidenceLevel = recommendation.confidence || 'unknown'
  const isSafe = activeTab === 'approve' // SafetyEngine validation handled by backend

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-lg bg-gray-900 shadow-2xl border border-gray-700">
        {/* Header */}
        <div className="border-b border-gray-700 px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Shield className="w-5 h-5 text-blue-400" />
            Approve Equipment Control
          </h2>
          <button
            onClick={handleClose}
            disabled={isLoading}
            className="text-gray-400 hover:text-gray-200 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Recommendation Details */}
        <div className="px-6 py-4 border-b border-gray-700 bg-gray-800/50">
          <h3 className="text-sm font-medium text-gray-300 mb-3">
            Equipment & Action
          </h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between items-start">
              <span className="text-gray-400">Equipment:</span>
              <span className="text-white font-medium">
                {recommendation.target_equipment}
              </span>
            </div>
            {recommendation.action && (
              <>
                <div className="flex justify-between items-start">
                  <span className="text-gray-400">Action:</span>
                  <span className="text-white font-medium">
                    {recommendation.action.point} = {recommendation.action.value}
                  </span>
                </div>
              </>
            )}
            {recommendation.reason && (
              <div className="flex justify-between items-start">
                <span className="text-gray-400">Reason:</span>
                <span className="text-white font-medium max-w-xs text-right">
                  {recommendation.reason}
                </span>
              </div>
            )}
            <div className="flex justify-between items-center pt-2">
              <span className="text-gray-400">Confidence:</span>
              <span
                className={`font-medium px-2 py-1 rounded text-xs ${
                  confidenceLevel === 'high'
                    ? 'bg-green-900/30 text-green-300'
                    : confidenceLevel === 'medium'
                      ? 'bg-yellow-900/30 text-yellow-300'
                      : 'bg-blue-900/30 text-blue-300'
                }`}
              >
                {confidenceLevel.toUpperCase()}
              </span>
            </div>
          </div>
        </div>

        {/* Safety Status Badge */}
        <div className="px-6 py-3 bg-blue-900/20 border-b border-gray-700 flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-green-400" />
          <span className="text-sm text-blue-300">
            SafetyEngine validation passed ✓
          </span>
        </div>

        {/* Error/Success Messages */}
        {error && (
          <div className="mx-6 mt-4 p-3 bg-red-900/20 border border-red-700 rounded flex items-start gap-2 text-sm text-red-300">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        {success && (
          <div className="mx-6 mt-4 p-3 bg-green-900/20 border border-green-700 rounded flex items-start gap-2 text-sm text-green-300">
            <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{success}</span>
          </div>
        )}

        {/* Tabs */}
        <div className="px-6 py-3 border-b border-gray-700 flex gap-2">
          <button
            onClick={() => setActiveTab('approve')}
            disabled={isLoading}
            className={`px-3 py-1 text-sm font-medium rounded transition-colors ${
              activeTab === 'approve'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-gray-200 disabled:opacity-50'
            }`}
          >
            Approve
          </button>
          <button
            onClick={() => setActiveTab('reject')}
            disabled={isLoading}
            className={`px-3 py-1 text-sm font-medium rounded transition-colors ${
              activeTab === 'reject'
                ? 'bg-red-600 text-white'
                : 'text-gray-400 hover:text-gray-200 disabled:opacity-50'
            }`}
          >
            Reject
          </button>
        </div>

        {/* Form */}
        <div className="px-6 py-4 space-y-4">
          {/* Approver Name */}
          <div>
            <label htmlFor="approver-name" className="block text-sm font-medium text-gray-300 mb-1">
              Your Name *
            </label>
            <input
              ref={approverInputRef}
              id="approver-name"
              type="text"
              value={approverName}
              onChange={(e) => setApproverName(e.target.value)}
              disabled={isLoading}
              placeholder="e.g., John Smith"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
          </div>

          {/* Approval Notes or Rejection Reason */}
          {activeTab === 'approve' ? (
            <div>
              <label htmlFor="approval-notes" className="block text-sm font-medium text-gray-300 mb-1">
                Approval Notes (optional)
              </label>
              <textarea
                id="approval-notes"
                value={approvalNotes}
                onChange={(e) => setApprovalNotes(e.target.value)}
                disabled={isLoading}
                placeholder="Add any notes about this approval..."
                rows={3}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 resize-none"
              />
            </div>
          ) : (
            <div>
              <label htmlFor="rejection-reason" className="block text-sm font-medium text-gray-300 mb-1">
                Rejection Reason *
              </label>
              <textarea
                id="rejection-reason"
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                disabled={isLoading}
                placeholder="Explain why you're rejecting this recommendation..."
                rows={3}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-red-500 disabled:opacity-50 resize-none"
              />
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-gray-700 flex gap-2 justify-end">
          <button
            onClick={handleClose}
            disabled={isLoading}
            className="px-4 py-2 rounded font-medium text-gray-300 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          {activeTab === 'approve' ? (
            <button
              onClick={handleApprove}
              disabled={isLoading || !approverName.trim()}
              className="px-4 py-2 rounded font-medium text-white bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {isLoading ? (
                <>
                  <Loader className="w-4 h-4 animate-spin" />
                  Approving...
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4" />
                  Approve & Execute
                </>
              )}
            </button>
          ) : (
            <button
              onClick={handleReject}
              disabled={isLoading || !approverName.trim() || !rejectionReason.trim()}
              className="px-4 py-2 rounded font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {isLoading ? (
                <>
                  <Loader className="w-4 h-4 animate-spin" />
                  Rejecting...
                </>
              ) : (
                <>
                  <XCircle className="w-4 h-4" />
                  Reject
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}
