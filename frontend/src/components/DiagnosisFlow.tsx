/**
 * DiagnosisFlow Component - Guided diagnosis conversation flow
 *
 * Features:
 * - Step-by-step progress indicator
 * - Visual checkpoint questions with tap-to-answer options
 * - Response tracking and branching logic
 * - Mobile-optimized for field technicians
 */

import { useState, useEffect, useCallback } from 'react';
import {
  CheckCircle,
  Circle,
  AlertTriangle,
  ChevronRight,
  RefreshCw,
  X,
  Clipboard,
  ArrowRight
} from 'lucide-react';
import { authorizedFetch } from '../lib/api/client';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Flow states matching backend DiagnosisState enum
type FlowState = 'identifying' | 'checking' | 'analyzing' | 'resolving' | 'complete';

interface Checkpoint {
  id: string;
  question: string;
  options?: string[];
  response?: string;
  timestamp?: string;
}

interface DiagnosisSession {
  session_id: string;
  state: FlowState;
  equipment?: {
    manufacturer?: string;
    model?: string;
    type?: string;
  };
  fault_code?: string;
  current_step_index: number;
  checkpoints: Checkpoint[];
  created_at: string;
}

interface DiagnosisFlowProps {
  /** Initial query to start diagnosis */
  initialQuery: string;
  /** Callback when diagnosis completes */
  onComplete?: (summary: DiagnosisSummary) => void;
  /** Callback to close the flow */
  onClose?: () => void;
  /** Optional session ID to resume */
  sessionId?: string;
}

interface DiagnosisSummary {
  session_id: string;
  equipment: {
    manufacturer?: string;
    model?: string;
    type?: string;
  };
  fault_code?: string;
  checkpoints_completed: number;
  total_duration: string;
  diagnosis_result?: string;
}

interface CurrentCheck {
  id: string;
  question: string;
  options?: string[];
  step_number: number;
  total_steps: number;
}

export default function DiagnosisFlow({
  initialQuery,
  onComplete,
  onClose,
  sessionId: resumeSessionId
}: DiagnosisFlowProps) {
  const [session, setSession] = useState<DiagnosisSession | null>(null);
  const [currentCheck, setCurrentCheck] = useState<CurrentCheck | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customResponse, setCustomResponse] = useState('');

  // Start or resume diagnosis session
  const startDiagnosis = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await authorizedFetch(`${API_BASE_URL}/api/diagnosis/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: initialQuery,
          session_id: resumeSessionId
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to start diagnosis: ${response.status}`);
      }

      const data = await response.json();

      // Handle response format - backend returns flow object with session details
      const flow = data.flow || data;
      const sessionId = flow.session_id || data.session_id;

      // Update session state
      setSession({
        session_id: sessionId,
        state: flow.state || data.state,
        equipment: flow.equipment || data.equipment,
        fault_code: flow.fault_code || data.fault_code,
        current_step_index: 0,
        checkpoints: [],
        created_at: new Date().toISOString()
      });

      // Set current check - backend may return "questions" array or "check" object
      if (data.questions && data.questions.length > 0) {
        const firstQuestion = data.questions[0];
        setCurrentCheck({
          id: firstQuestion.id,
          question: firstQuestion.question,
          options: firstQuestion.options,
          step_number: 1,
          total_steps: data.questions.length
        });
      } else if (data.check) {
        setCurrentCheck({
          id: data.check.id,
          question: data.check.question,
          options: data.check.options,
          step_number: data.progress?.current || 1,
          total_steps: data.progress?.total || 1
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start diagnosis');
    } finally {
      setIsLoading(false);
    }
  }, [initialQuery, resumeSessionId]);

  // Start diagnosis on mount
  useEffect(() => {
    startDiagnosis();
  }, [startDiagnosis]);

  // Submit response to current checkpoint
  const submitResponse = async (response: string) => {
    if (!session || !currentCheck) return;

    setIsLoading(true);
    setError(null);

    try {
      const apiResponse = await authorizedFetch(`${API_BASE_URL}/api/diagnosis/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: session.session_id,
          step_id: currentCheck.id,
          response
        })
      });

      if (!apiResponse.ok) {
        throw new Error(`Failed to submit response: ${apiResponse.status}`);
      }

      const data = await apiResponse.json();

      // Handle response format - backend returns flow object
      const flow = data.flow || data;
      const newState = flow.state || data.state;

      // Update session with new checkpoint
      setSession(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          state: newState,
          current_step_index: prev.current_step_index + 1,
          checkpoints: [
            ...prev.checkpoints,
            {
              id: currentCheck.id,
              question: currentCheck.question,
              response,
              timestamp: new Date().toISOString()
            }
          ]
        };
      });

      // Handle next state
      if (newState === 'complete') {
        // Diagnosis complete - get summary
        const summaryResponse = await authorizedFetch(
          `${API_BASE_URL}/api/diagnosis/${session.session_id}`,
          { method: 'DELETE' }
        );

        if (summaryResponse.ok) {
          const summary = await summaryResponse.json();
          onComplete?.(summary);
        }
        setCurrentCheck(null);
      } else if (data.questions && data.questions.length > 0) {
        // Backend returns questions array - find next unanswered question
        const answeredIds = session.checkpoints.map(c => c.id);
        answeredIds.push(currentCheck.id); // Include current one being answered
        const nextQuestion = data.questions.find((q: { id: string }) => !answeredIds.includes(q.id));

        if (nextQuestion) {
          setCurrentCheck({
            id: nextQuestion.id,
            question: nextQuestion.question,
            options: nextQuestion.options,
            step_number: currentCheck.step_number + 1,
            total_steps: data.questions.length
          });
        } else {
          // All questions answered, move to checking state
          setCurrentCheck(null);
        }
      } else if (data.check) {
        // Move to next checkpoint
        setCurrentCheck({
          id: data.check.id,
          question: data.check.question,
          options: data.check.options,
          step_number: data.progress?.current || (currentCheck.step_number + 1),
          total_steps: data.progress?.total || currentCheck.total_steps
        });
      } else if (data.type === 'analysis' || data.type === 'diagnosis') {
        // Analysis/diagnosis result - show completion
        setCurrentCheck(null);
        if (onComplete && data.diagnosis) {
          onComplete({
            session_id: session.session_id,
            equipment: session.equipment || {},
            fault_code: session.fault_code,
            checkpoints_completed: session.checkpoints.length + 1,
            total_duration: 'N/A',
            diagnosis_result: data.diagnosis.summary || data.message
          });
        }
      }

      setCustomResponse('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit response');
    } finally {
      setIsLoading(false);
    }
  };

  // Render progress indicator
  const renderProgress = () => {
    if (!currentCheck || !session) return null;

    const completedSteps = session.checkpoints.length;
    const totalSteps = currentCheck.total_steps;

    return (
      <div className="mb-4">
        {/* Progress bar */}
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Step {currentCheck.step_number} of {totalSteps}
          </span>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {Math.round((completedSteps / totalSteps) * 100)}% complete
          </span>
        </div>
        <div
          className="w-full rounded-full h-2"
          style={{ background: "var(--color-sentinel-bg-secondary)" }}
        >
          <div
            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${(completedSteps / totalSteps) * 100}%` }}
          />
        </div>

        {/* Step indicators */}
        <div className="flex items-center justify-center mt-3 gap-1.5">
          {Array.from({ length: totalSteps }, (_, idx) => {
            const isComplete = idx < completedSteps;
            const isCurrent = idx === completedSteps;

            return (
              <div
                key={idx}
                className={`w-2.5 h-2.5 rounded-full transition-colors ${
                  isComplete
                    ? 'bg-green-500'
                    : isCurrent
                    ? 'bg-blue-500'
                    : 'bg-gray-300 dark:bg-gray-600'
                }`}
              />
            );
          })}
        </div>
      </div>
    );
  };

  // Render completed checkpoints
  const renderCompletedSteps = () => {
    if (!session || session.checkpoints.length === 0) return null;

    return (
      <div className="mb-4 space-y-2">
        {session.checkpoints.map((checkpoint) => (
          <div
            key={checkpoint.id}
            className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400"
          >
            <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 flex-none" />
            <div className="flex-1 min-w-0">
              <p className="truncate">{checkpoint.question}</p>
              <p className="font-medium text-gray-800 dark:text-gray-200 mt-0.5">
                {checkpoint.response}
              </p>
            </div>
          </div>
        ))}
      </div>
    );
  };

  // Render current question
  const renderCurrentQuestion = () => {
    if (!currentCheck) {
      if (session?.state === 'complete') {
        return (
          <div className="text-center py-6">
            <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Diagnosis Complete
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              All checkpoints have been reviewed.
            </p>
          </div>
        );
      }
      return null;
    }

    return (
      <div className="space-y-4">
        {/* Question */}
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <div className="flex-none w-8 h-8 bg-blue-100 dark:bg-blue-800 rounded-full flex items-center justify-center">
              <Clipboard className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-gray-900 dark:text-white">
                {currentCheck.question}
              </p>
            </div>
          </div>
        </div>

        {/* Quick response options */}
        {currentCheck.options && currentCheck.options.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Quick responses:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {currentCheck.options.map((option, idx) => (
                <button
                  key={idx}
                  onClick={() => submitResponse(option)}
                  disabled={isLoading}
                  className="flex items-center justify-between p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-left hover:bg-gray-50 dark:hover:bg-gray-700 hover:border-blue-300 dark:hover:border-blue-600 transition-colors disabled:opacity-50"
                >
                  <span>{option}</span>
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Custom response input */}
        <div className="space-y-2">
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Or describe what you found:
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={customResponse}
              onChange={(e) => setCustomResponse(e.target.value)}
              placeholder="Type your observation..."
              disabled={isLoading}
              className="flex-1 px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && customResponse.trim()) {
                  submitResponse(customResponse.trim());
                }
              }}
            />
            <button
              onClick={() => customResponse.trim() && submitResponse(customResponse.trim())}
              disabled={isLoading || !customResponse.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors"
            >
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    );
  };

  // Loading state
  if (isLoading && !session) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-md border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-center gap-3">
          <RefreshCw className="w-5 h-5 text-blue-500 animate-spin" />
          <span className="text-sm text-gray-600 dark:text-gray-400">
            Starting diagnosis flow...
          </span>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !session) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-md border border-red-200 dark:border-red-800 p-6">
        <div className="flex items-center gap-3 text-red-600 dark:text-red-400">
          <AlertTriangle className="w-5 h-5" />
          <span className="text-sm">{error}</span>
        </div>
        <button
          onClick={startDiagnosis}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-md border border-gray-200 dark:border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <Circle className="w-3 h-3 text-green-500 animate-pulse" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Guided Diagnosis
          </span>
          {session?.fault_code && (
            <span className="px-2 py-0.5 bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400 text-xs rounded">
              {session.fault_code}
            </span>
          )}
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <X className="w-4 h-4 text-gray-500 dark:text-gray-400" />
          </button>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Equipment info */}
        {session?.equipment && (
          <div className="mb-4 px-3 py-2 bg-gray-50 dark:bg-gray-900 rounded-lg">
            <p className="text-xs text-gray-500 dark:text-gray-400">Equipment:</p>
            <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
              {[session.equipment.manufacturer, session.equipment.model, session.equipment.type]
                .filter(Boolean)
                .join(' • ')}
            </p>
          </div>
        )}

        {renderProgress()}
        {renderCompletedSteps()}
        {renderCurrentQuestion()}

        {/* Loading overlay for responses */}
        {isLoading && session && (
          <div className="mt-4 flex items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <RefreshCw className="w-4 h-4 animate-spin" />
            Processing response...
          </div>
        )}

        {/* Error message */}
        {error && session && (
          <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          </div>
        )}
      </div>
    </div>
  );
}
