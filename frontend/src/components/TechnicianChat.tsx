/**
 * TechnicianChat Component - Mobile-first AI chat for field technicians
 *
 * Features:
 * - Mobile-optimized design with touch-friendly controls
 * - Equipment lookup integration (fault codes, parts, natural language)
 * - Structured diagnosis messages with severity badges
 * - Auto-scroll to latest message
 * - Photo button placeholder for future Vision API integration
 */

import { useState, useRef, useEffect } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import {
  Send,
  Wrench,
  Search,
  AlertTriangle,
  CheckCircle,
  Info,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Clipboard,
  PlayCircle,
  Eye,
  ImageIcon,
  FileText,
  Download,
  Building2,
} from 'lucide-react';
import { authorizedFetch } from '../lib/api/client';
import {
  conceptDocumentsApi,
  type ConceptDocumentSearchResult,
  type ConceptDocumentSearchResponse,
} from '../lib/api/conceptDocuments';
import DiagnosisFlow from './DiagnosisFlow';
import PhotoCapture from './PhotoCapture';
import OfflineIndicator from './OfflineIndicator';
import {
  isOnline,
  setupOfflineListeners,
  getCachedFaultCodes,
  getCachedRepairProcedures,
  clearSyncQueue,
} from '../lib/offlineStorage';

// Message types for conversation
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  type: 'text' | 'diagnosis' | 'parts' | 'suggestions' | 'error' | 'guided-flow' | 'vision' | 'photo';
  data?: DiagnosisData | PartsData | SuggestionsData | VisionData;
  flowQuery?: string; // For guided-flow type
  imageUrl?: string; // For photo messages
}

// Vision analysis result data
interface VisionData {
  success: boolean;
  analysis?: string;
  components?: Array<{
    name: string;
    manufacturer?: string;
    model?: string;
    condition?: string;
    confidence?: number;
  }>;
  issues?: Array<{
    type: string;
    severity: string;
    location?: string;
    description?: string;
    recommendation?: string;
  }>;
  fault_codes?: string[];
  manufacturer?: string;
  model?: string;
  serial?: string;
  overall_condition?: string;
  maintenance_priority?: string;
  notes?: string;
}

// Diagnosis response data structure
interface DiagnosisData {
  fault?: {
    code: string;
    name: string;
    severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
    description: string;
    probable_causes?: Array<{
      cause: string;
      likelihood: 'high' | 'medium' | 'low';
      check?: string;
    }>;
    recommended_fix?: {
      immediate: string[];
      scenarios: Record<string, string>;
    };
  };
  parts?: Array<{
    part_name: string;
    part_number?: string;
    manufacturer?: string;
    suppliers?: Array<{
      supplier: string;
      price?: string;
      lead_time?: string;
      url?: string;
    }>;
  }>;
  forum_solutions?: Array<{
    source: string;
    url: string;
    title?: string;
    description?: string;
  }>;
}

interface PartsData {
  parts: Array<{
    part_name: string;
    part_number?: string;
    manufacturer?: string;
    suppliers?: Array<{
      supplier: string;
      price?: string;
      lead_time?: string;
    }>;
    generic_alternative?: {
      category: string;
      generic_part_number: string;
      manufacturer: string;
    };
  }>;
}

interface SuggestionsData {
  suggestions: Array<{
    problem: string;
    solution: string;
    source: string;
  }>;
  forum_solutions?: Array<{
    source: string;
    url: string;
    description?: string;
  }>;
  note?: string;
}

type ConceptSearchStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'unavailable' | 'error';

interface TechnicianChatProps {
  siteId?: string;
  siteLabel?: string;
}

interface ConceptSearchState {
  status: ConceptSearchStatus;
  query: string;
  results: ConceptDocumentSearchResult[];
  totalResults: number;
  weakResults: boolean;
  message: string | null;
}

function isBrowserOpenableConceptLink(url?: string | null): boolean {
  return Boolean(url && /^https?:\/\//i.test(url));
}

export default function TechnicianChat({ siteId, siteLabel }: TechnicianChatProps = {}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showQuickActions, setShowQuickActions] = useState(true);
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);
  const [isOnlineMode, setIsOnlineMode] = useState(isOnline());
  const [conceptSearchEnabled, setConceptSearchEnabled] = useState(false);
  const [conceptSearch, setConceptSearch] = useState<ConceptSearchState>({
    status: 'idle',
    query: '',
    results: [],
    totalResults: 0,
    weakResults: false,
    message: null,
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Generate unique message ID
  const generateId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, conceptSearch]);

  // Setup offline/online listeners and cache initial data
  useEffect(() => {
    // Setup event listeners for online/offline
    const cleanup = setupOfflineListeners(
      () => {
        setIsOnlineMode(true);
        // Trigger sync of queued operations
        const message: Message = {
          id: generateId(),
          role: 'assistant',
          content: 'Back online - syncing changes...',
          timestamp: new Date(),
          type: 'text'
        };
        setMessages(prev => [...prev, message]);
        clearSyncQueue();
      },
      () => {
        setIsOnlineMode(false);
        // Notify user they're offline
        const message: Message = {
          id: generateId(),
          role: 'assistant',
          content: 'You are offline - using cached data. Work orders will sync when you\'re back online.',
          timestamp: new Date(),
          type: 'text'
        };
        setMessages(prev => [...prev, message]);
      }
    );

    return cleanup;
  }, []);

  // Start guided diagnosis flow
  const startGuidedDiagnosis = (query: string) => {
    const flowId = generateId();
    setActiveFlowId(flowId);

    const flowMessage: Message = {
      id: flowId,
      role: 'assistant',
      content: 'Starting guided diagnosis...',
      timestamp: new Date(),
      type: 'guided-flow',
      flowQuery: query
    };

    setMessages(prev => [...prev, flowMessage]);
    setShowQuickActions(false);
  };

  // Handle guided diagnosis completion
  const handleFlowComplete = (summary: {
    session_id: string;
    equipment: { manufacturer?: string; model?: string; type?: string };
    fault_code?: string;
    checkpoints_completed: number;
    total_duration: string;
    diagnosis_result?: string;
  }) => {
    setActiveFlowId(null);

    const summaryMessage: Message = {
      id: generateId(),
      role: 'assistant',
      content: `Diagnosis complete! ${summary.checkpoints_completed} checkpoints reviewed in ${summary.total_duration}.${summary.diagnosis_result ? ` Result: ${summary.diagnosis_result}` : ''}`,
      timestamp: new Date(),
      type: 'text'
    };

    setMessages(prev => [...prev, summaryMessage]);
    inputRef.current?.focus();
  };

  // Close active diagnosis flow
  const handleFlowClose = () => {
    setActiveFlowId(null);
    // Remove the flow message
    setMessages(prev => prev.filter(m => m.id !== activeFlowId));
    inputRef.current?.focus();
  };

  // Handle photo analysis results
  const handlePhotoAnalysis = (result: VisionData) => {
    // Add photo message for user
    const photoMessage: Message = {
      id: generateId(),
      role: 'user',
      content: 'Sent a photo for analysis',
      timestamp: new Date(),
      type: 'photo'
    };

    // Build response message based on result
    let responseContent = 'I analyzed your photo.';
    if (result.analysis) {
      responseContent = result.analysis;
    } else if (result.components && result.components.length > 0) {
      responseContent = `Identified ${result.components.length} component(s) in the image.`;
    } else if (result.issues && result.issues.length > 0) {
      responseContent = `Found ${result.issues.length} issue(s) requiring attention.`;
    } else if (result.manufacturer || result.model) {
      responseContent = `Equipment: ${[result.manufacturer, result.model].filter(Boolean).join(' ')}`;
    }

    const visionMessage: Message = {
      id: generateId(),
      role: 'assistant',
      content: responseContent,
      timestamp: new Date(),
      type: 'vision',
      data: result
    };

    setMessages(prev => [...prev, photoMessage, visionMessage]);
    setShowQuickActions(false);
  };

  // Handle photo analysis error
  const handlePhotoError = (error: string) => {
    const errorMessage: Message = {
      id: generateId(),
      role: 'assistant',
      content: `Photo analysis failed: ${error}`,
      timestamp: new Date(),
      type: 'error'
    };
    setMessages(prev => [...prev, errorMessage]);
  };

  const runConceptSearch = async (messageText?: string) => {
    const text = messageText || input.trim();
    if (!text || isTyping) return;
    if (!siteId) {
      setConceptSearch({
        status: 'error',
        query: text,
        results: [],
        totalResults: 0,
        weakResults: false,
        message: 'Select a site before searching Concept documents.',
      });
      return;
    }

    setInput('');
    setIsTyping(true);
    setShowQuickActions(false);
      setConceptSearch({
        status: 'loading',
        query: text,
        results: [],
        totalResults: 0,
      weakResults: false,
      message: null,
    });

    try {
      const response: ConceptDocumentSearchResponse = await conceptDocumentsApi.search({
        site_id: siteId,
        query: text,
        top_k: 10,
      });

      setConceptSearch({
        status: response.total_results > 0 ? 'ready' : 'empty',
        query: text,
        results: response.results,
        totalResults: response.total_results,
        weakResults: response.weak_results ?? false,
        message: null,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Concept document search failed.';
      const unavailable = message.toLowerCase().includes('unavailable');
      setConceptSearch({
        status: unavailable ? 'unavailable' : 'error',
        query: text,
        results: [],
        totalResults: 0,
        weakResults: false,
        message,
      });
    } finally {
      setIsTyping(false);
      inputRef.current?.focus();
    }
  };

  const openConceptDocument = async (
    result: ConceptDocumentSearchResult,
    action: 'open' | 'download',
  ) => {
    if (!siteId) return;

    const targetUrl = action === 'download' ? result.download_url : result.open_url;
    if (!targetUrl) return;
    if (!isBrowserOpenableConceptLink(targetUrl)) {
      setConceptSearch((current) => ({
        ...current,
        message:
          'This result does not have a live browser-openable Concept link yet. The current export only provides an internal document reference or file path.',
      }));
      return;
    }

    try {
      await conceptDocumentsApi.logAction({
        site_id: siteId,
        document_id: result.document_id,
        action,
        query: conceptSearch.query || undefined,
      });
    } catch (error) {
      console.error('Failed to audit Concept document action:', error);
    }

    window.open(targetUrl, '_blank', 'noopener,noreferrer');
  };

  // Send message to equipment lookup API
  const sendTechnicalMessage = async (messageText?: string) => {
    const text = messageText || input.trim();
    if (!text || isTyping) return;

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: text,
      timestamp: new Date(),
      type: 'text'
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);
    setShowQuickActions(false);

    try {
      // Check if offline
      if (!isOnlineMode) {
        // Try to use cached data
        const cachedCodes = await getCachedFaultCodes();
        const _cachedProcedures = await getCachedRepairProcedures();

        // Simple offline search in cached data
        const searchLower = text.toLowerCase();
        const matchedCodes = Object.entries(cachedCodes).filter(
          ([code, data]) =>
            code.toLowerCase().includes(searchLower) ||
            String(data.name || '').toLowerCase().includes(searchLower)
        );

        if (matchedCodes.length > 0) {
          const [code, data] = matchedCodes[0];
          const offlineMessage: Message = {
            id: generateId(),
            role: 'assistant',
            content: `(Offline) Found in cached data: ${code}`,
            timestamp: new Date(),
            type: 'diagnosis',
            data: {
              fault: {
                code,
                name: data.name || code,
                severity: data.severity || 'medium',
                description: data.description || 'No description available offline',
                probable_causes: data.probable_causes || [],
                recommended_fix: data.recommended_fix || { immediate: [], scenarios: {} }
              },
              parts: data.parts || []
            }
          };
          setMessages(prev => [...prev, offlineMessage]);
        } else {
          const offlineMessage: Message = {
            id: generateId(),
            role: 'assistant',
            content: 'Offline mode: No matching fault codes in cache. Please reconnect to search the full database.',
            timestamp: new Date(),
            type: 'text'
          };
          setMessages(prev => [...prev, offlineMessage]);
        }
      } else {
        // Call equipment lookup search endpoint (online)
        const params = new URLSearchParams({ query: text });
        const response = await authorizedFetch(`/api/equipment-lookup/search?${params}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
          throw new Error(`API error: ${response.status}`);
        }

        const data = await response.json();

        // Determine message type based on response
        let messageType: Message['type'] = 'text';
        let assistantData: DiagnosisData | SuggestionsData | undefined;

        if (data.fault) {
          messageType = 'diagnosis';
          assistantData = data as DiagnosisData;
        } else if (data.suggestions && data.suggestions.length > 0) {
          messageType = 'suggestions';
          assistantData = data as SuggestionsData;
        } else if (data.query_type === 'keyword') {
          messageType = 'suggestions';
          assistantData = data as SuggestionsData;
        }

        const assistantMessage: Message = {
          id: generateId(),
          role: 'assistant',
          content: formatResponse(data),
          timestamp: new Date(),
          type: messageType,
          data: assistantData
        };

        setMessages(prev => [...prev, assistantMessage]);
      }
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: isOnlineMode
          ? 'Sorry, I encountered an error connecting to the equipment database. Please check your connection and try again.'
          : 'You are offline. Please reconnect to search the equipment database.',
        timestamp: new Date(),
        type: 'error'
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsTyping(false);
      inputRef.current?.focus();
    }
  };

  // Format response for display
  const formatResponse = (data: DiagnosisData | SuggestionsData | { note?: string }): string => {
    if ('fault' in data && data.fault) {
      return `Found: ${data.fault.code} - ${data.fault.name}`;
    }
    if ('suggestions' in data && data.suggestions && data.suggestions.length > 0) {
      return `Found ${data.suggestions.length} suggestion(s) for your query.`;
    }
    if ('note' in data && data.note) {
      return data.note;
    }
    return 'I found some information that might help.';
  };

  // Handle form submission
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (conceptSearchEnabled) {
      void runConceptSearch();
      return;
    }
    void sendTechnicalMessage();
  };

  // Handle Enter key
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (conceptSearchEnabled) {
        void runConceptSearch();
        return;
      }
      void sendTechnicalMessage();
    }
  };

  // Quick action buttons
  const quickActions = [
    { label: 'Carrier E4', query: 'Carrier fault E4', icon: AlertTriangle },
    { label: 'ABB VSD fault', query: 'ABB VSD FAULT_001', icon: Wrench },
    { label: 'Chiller noise', query: 'chiller making loud noise', icon: Search },
    { label: 'Oil filter', query: 'oil filter carrier', icon: Info },
  ];

  // Guided diagnosis quick actions
  const guidedActions = [
    { label: 'E4 Diagnosis', query: 'Carrier chiller E4 fault', icon: Clipboard },
    { label: 'Low Pressure', query: 'low refrigerant pressure alarm', icon: Clipboard },
  ];

  const conceptSearchExamples = [
    { label: 'Generator sheets', query: 'last generator service sheets', icon: Search },
    { label: 'Lift inspection', query: 'elevator annual lift inspection certificate', icon: FileText },
    { label: 'Fire pump reports', query: 'fire pump maintenance reports for 2025', icon: Building2 },
    { label: 'Chiller commissioning', query: 'chiller commissioning sheets', icon: Clipboard },
  ];

  return (
    <div className="flex flex-col h-full bg-gray-50 dark:bg-gray-900">
      {/* Offline Indicator */}
      <OfflineIndicator />

      {/* Header */}
      <div className="flex-none bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <Wrench className="w-5 h-5 text-blue-600" />
              SENTINEL Tech Chat
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Your expert colleague in your pocket
            </p>
            {siteLabel && (
              <p className="mt-1 text-xs uppercase tracking-[0.16em] text-gray-400 dark:text-gray-500">
                Site scoped to {siteLabel}
              </p>
            )}
          </div>

          <div className="flex flex-col items-start gap-2 md:items-end">
            <button
              type="button"
              onClick={() => setConceptSearchEnabled((prev) => !prev)}
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                conceptSearchEnabled
                  ? 'bg-blue-600 text-white ring-1 ring-blue-600 shadow-sm hover:bg-blue-700 dark:bg-blue-500 dark:ring-blue-500 dark:hover:bg-blue-400'
                  : 'bg-white text-gray-900 ring-1 ring-gray-300 shadow-sm hover:bg-gray-50 hover:ring-gray-400 dark:bg-gray-800 dark:text-gray-100 dark:ring-gray-500 dark:hover:bg-gray-700 dark:hover:ring-gray-400'
              }`}
              aria-pressed={conceptSearchEnabled}
            >
              <FileText className="h-4 w-4" />
              Search Concept documents
            </button>
            {conceptSearchEnabled && (
              <div className="flex flex-col items-start gap-1 md:items-end">
                <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-800 dark:bg-blue-900/40 dark:text-blue-100">
                  Concept document search active
                </span>
                <p className="text-xs text-gray-600 dark:text-gray-300">
                  Find saved documents in Concept using natural language
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 pb-32 md:pb-4">
        {conceptSearchEnabled ? (
          <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
            {conceptSearch.status === 'idle' && (
              <div className="rounded-2xl border border-dashed border-blue-200 bg-blue-50/70 p-6 text-center dark:border-blue-900 dark:bg-blue-950/20">
                <div className="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-white text-blue-600 shadow-sm dark:bg-gray-800 dark:text-blue-300">
                  <FileText className="h-7 w-7" />
                </div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white">Search stored site documents</h3>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                  Find saved documents in Concept using natural language.
                </p>
                <div className="mt-5 flex flex-wrap justify-center gap-2">
                  {conceptSearchExamples.map((action, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => void runConceptSearch(action.query)}
                      className="inline-flex items-center gap-1.5 rounded-full border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-900 shadow-sm transition-colors hover:border-blue-300 hover:bg-blue-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:hover:border-blue-500 dark:hover:bg-gray-700"
                    >
                      <action.icon className="h-3.5 w-3.5" />
                      {action.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {conceptSearch.status === 'loading' && (
              <div className="rounded-2xl border border-gray-200 bg-white px-4 py-5 text-sm text-gray-500 shadow-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
                Searching Concept documents...
              </div>
            )}

            {conceptSearch.query && conceptSearch.status !== 'idle' && conceptSearch.status !== 'loading' && (
              <div className="rounded-2xl border border-gray-200 bg-white px-4 py-3 shadow-sm dark:border-gray-700 dark:bg-gray-800">
                <p className="text-xs uppercase tracking-[0.16em] text-gray-400 dark:text-gray-500">Query</p>
                <p className="mt-1 text-sm text-gray-900 dark:text-white">{conceptSearch.query}</p>
              </div>
            )}

            {conceptSearch.status === 'ready' && (
              <>
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  {conceptSearch.totalResults} matching document{conceptSearch.totalResults === 1 ? '' : 's'} found
                </div>
                {conceptSearch.weakResults && (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
                    We found related documents, but no strong exact matches.
                  </div>
                )}
                {conceptSearch.message && (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
                    {conceptSearch.message}
                  </div>
                )}
                <div className="grid gap-3">
                  {conceptSearch.results.map((result) => (
                    <ConceptDocumentCard
                      key={result.document_id}
                      result={result}
                      onAction={openConceptDocument}
                    />
                  ))}
                </div>
              </>
            )}

            {conceptSearch.status === 'empty' && (
              <div className="rounded-2xl border border-gray-200 bg-white px-4 py-5 text-sm shadow-sm dark:border-gray-700 dark:bg-gray-800">
                <p className="font-medium text-gray-900 dark:text-white">
                  No matching documents found in Concept for this site.
                </p>
                <p className="mt-2 text-gray-500 dark:text-gray-400">
                  Try broader wording or remove date-specific terms.
                </p>
              </div>
            )}

            {conceptSearch.status === 'unavailable' && (
              <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-5 text-sm shadow-sm dark:border-red-900/60 dark:bg-red-950/20">
                <p className="font-medium text-red-900 dark:text-red-200">
                  Concept document search is currently unavailable.
                </p>
                <p className="mt-2 text-red-700 dark:text-red-300">
                  Please try again later or open documents directly in Concept.
                </p>
              </div>
            )}

            {conceptSearch.status === 'error' && conceptSearch.message && (
              <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-5 text-sm text-red-800 shadow-sm dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-200">
                {conceptSearch.message}
              </div>
            )}
          </div>
        ) : (
          <>
            {messages.length === 0 && (
              <div className="text-center py-8">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 dark:bg-blue-900 rounded-full mb-4">
                  <Wrench className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                </div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  How can I help you today?
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                  Describe a fault, equipment problem, or search for parts
                </p>

                {showQuickActions && (
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <p className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wide">
                        Try asking about:
                      </p>
                      <div className="flex flex-wrap justify-center gap-2">
                        {quickActions.map((action, idx) => (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => void sendTechnicalMessage(action.query)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-full text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                          >
                            <action.icon className="w-3.5 h-3.5" />
                            {action.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <p className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wide">
                        Or start guided diagnosis:
                      </p>
                      <div className="flex flex-wrap justify-center gap-2">
                        {guidedActions.map((action, idx) => (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => startGuidedDiagnosis(action.query)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-full text-sm text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
                          >
                            <PlayCircle className="w-3.5 h-3.5" />
                            {action.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {messages.map((message) => (
              message.type === 'guided-flow' && message.flowQuery ? (
                <div key={message.id} className="w-full max-w-2xl mx-auto">
                  <DiagnosisFlow
                    initialQuery={message.flowQuery}
                    onComplete={handleFlowComplete}
                    onClose={handleFlowClose}
                  />
                </div>
              ) : (
                <MessageBubble key={message.id} message={message} onStartGuided={startGuidedDiagnosis} />
              )
            ))}

            {isTyping && (
              <div className="flex justify-start">
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl px-4 py-3 shadow-sm">
                  <div className="flex items-center gap-2">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      SENTINEL is thinking...
                    </span>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area - Fixed at bottom on mobile */}
      <form
        onSubmit={handleSubmit}
        className="flex-none bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 px-4 py-3 fixed bottom-0 left-0 right-0 md:relative md:bottom-auto"
        style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' }}
      >
        <div className="mx-auto flex max-w-4xl flex-col gap-2">
          {conceptSearchEnabled && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {siteLabel ? `Searching ${siteLabel} only.` : 'Searching the current site only.'}
            </p>
          )}
          <div className="flex items-center gap-2">
            {!conceptSearchEnabled && (
              <PhotoCapture
                onAnalysisComplete={handlePhotoAnalysis}
                onError={handlePhotoError}
                analysisType="component"
                disabled={isTyping}
              />
            )}
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={conceptSearchEnabled ? 'Search stored site documents' : 'Describe a fault or search for parts...'}
            disabled={isTyping}
            className="flex-1 px-4 py-2.5 bg-gray-100 dark:bg-gray-700 border-0 rounded-full text-sm text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!input.trim() || isTyping}
            className="flex-none p-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors"
            aria-label={conceptSearchEnabled ? 'Run Concept document search' : 'Send technical chat message'}
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        </div>
      </form>
    </div>
  );
}

// Message bubble component
function MessageBubble({ message, onStartGuided }: { message: Message; onStartGuided?: (query: string) => void }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] md:max-w-[75%] rounded-2xl px-4 py-3 shadow-sm ${
          isUser
            ? 'bg-blue-600 text-white'
            : message.type === 'error'
            ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200'
            : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white'
        }`}
      >
        {message.type === 'diagnosis' && message.data ? (
          <DiagnosisMessage data={message.data as DiagnosisData} onStartGuided={onStartGuided} />
        ) : message.type === 'suggestions' && message.data ? (
          <SuggestionsMessage data={message.data as SuggestionsData} />
        ) : message.type === 'vision' && message.data ? (
          <VisionMessage data={message.data as VisionData} />
        ) : message.type === 'photo' ? (
          <div className="flex items-center gap-2 text-sm">
            <ImageIcon className="w-4 h-4" />
            <span>{message.content}</span>
          </div>
        ) : (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        )}

        <p className={`text-xs mt-2 ${isUser ? 'text-blue-200' : 'text-gray-400 dark:text-gray-500'}`}>
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  );
}

function ConceptDocumentCard({
  result,
  onAction,
}: {
  result: ConceptDocumentSearchResult;
  onAction: (result: ConceptDocumentSearchResult, action: 'open' | 'download') => void | Promise<void>;
}) {
  const canOpenFile = isBrowserOpenableConceptLink(result.open_url);
  const canDownloadFile = isBrowserOpenableConceptLink(result.download_url);

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300">
              <FileText className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <h4 className="truncate text-base font-semibold text-gray-900 dark:text-white">{result.title}</h4>
              <div className="mt-2 grid gap-1 text-sm text-gray-500 dark:text-gray-400">
                <p><span className="font-medium text-gray-700 dark:text-gray-300">Type:</span> {result.document_type || 'Unknown'}</p>
                <p><span className="font-medium text-gray-700 dark:text-gray-300">Date:</span> {result.document_date || 'Unknown'}</p>
                <p><span className="font-medium text-gray-700 dark:text-gray-300">Site:</span> {result.building_name || 'Current site'}</p>
                {(result.equipment_category || result.equipment_name) && (
                  <p>
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {result.equipment_name ? 'Equipment:' : 'Category:'}
                    </span>{' '}
                    {result.equipment_name || result.equipment_category}
                  </p>
                )}
                <p className="truncate">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Path:</span> {result.path}
                </p>
              </div>
            </div>
          </div>
          {result.match_reasons.length > 0 && (
            <p className="mt-3 text-xs uppercase tracking-[0.16em] text-gray-400 dark:text-gray-500">
              Matched on: {result.match_reasons.join(', ')}
            </p>
          )}
          {result.snippet && (
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{result.snippet}</p>
          )}
          {!canOpenFile && (
            <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">
              Live Concept link not available in this pilot export yet.
            </p>
          )}
        </div>

        <div className="flex flex-none gap-2">
          <button
            type="button"
            onClick={() => void onAction(result, 'open')}
            disabled={!canOpenFile}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              canOpenFile
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'cursor-not-allowed bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
          >
            <ExternalLink className="h-4 w-4" />
            {canOpenFile ? 'Open file' : 'Link unavailable'}
          </button>
          {result.download_url && (
            <button
              type="button"
              onClick={() => void onAction(result, 'download')}
              disabled={!canDownloadFile}
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                canDownloadFile
                  ? 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700'
                  : 'cursor-not-allowed border-gray-200 bg-gray-100 text-gray-400 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-500'
              }`}
            >
              <Download className="h-4 w-4" />
              Download
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Diagnosis message component
function DiagnosisMessage({ data, onStartGuided }: { data: DiagnosisData; onStartGuided?: (query: string) => void }) {
  const [showCauses, setShowCauses] = useState(true);
  const [showFix, setShowFix] = useState(true);
  const [showParts, setShowParts] = useState(false);

  const fault = data.fault;
  if (!fault) return null;

  const severityColors = {
    critical: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    low: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    info: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <div className="flex items-start justify-between gap-2">
          <h4 className="font-semibold text-base">
            {fault.code}: {fault.name}
          </h4>
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${severityColors[fault.severity]}`}>
            {fault.severity.toUpperCase()}
          </span>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          {fault.description}
        </p>
      </div>

      {/* Probable Causes */}
      {fault.probable_causes && fault.probable_causes.length > 0 && (
        <div>
          <button
            onClick={() => setShowCauses(!showCauses)}
            className="flex items-center gap-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
          >
            {showCauses ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Probable Causes ({fault.probable_causes.length})
          </button>
          {showCauses && (
            <ul className="mt-2 space-y-2">
              {fault.probable_causes.map((cause, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm">
                  <span className={`mt-1 w-2 h-2 rounded-full flex-none ${
                    cause.likelihood === 'high' ? 'bg-red-500' :
                    cause.likelihood === 'medium' ? 'bg-yellow-500' : 'bg-gray-400'
                  }`} />
                  <div>
                    <span className="font-medium">{cause.cause}</span>
                    {cause.check && (
                      <p className="text-gray-500 dark:text-gray-400 text-xs mt-0.5">
                        Check: {cause.check}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Recommended Fix */}
      {fault.recommended_fix && (
        <div>
          <button
            onClick={() => setShowFix(!showFix)}
            className="flex items-center gap-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
          >
            {showFix ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Recommended Actions
          </button>
          {showFix && fault.recommended_fix.immediate && (
            <ol className="mt-2 space-y-1.5">
              {fault.recommended_fix.immediate.map((step, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm">
                  <span className="flex-none w-5 h-5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-xs font-medium flex items-center justify-center">
                    {idx + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {/* Parts */}
      {data.parts && data.parts.length > 0 && (
        <div>
          <button
            onClick={() => setShowParts(!showParts)}
            className="flex items-center gap-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
          >
            {showParts ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Parts You May Need ({data.parts.length})
          </button>
          {showParts && (
            <div className="mt-2 space-y-2">
              {data.parts.slice(0, 3).map((part, idx) => (
                <div key={idx} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2.5">
                  <p className="font-medium text-sm">{part.part_name}</p>
                  {part.part_number && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">P/N: {part.part_number}</p>
                  )}
                  {part.suppliers && part.suppliers.length > 0 && (
                    <div className="mt-1.5 space-y-1">
                      {part.suppliers.slice(0, 2).map((supplier, sidx) => (
                        <div key={sidx} className="flex items-center justify-between text-xs">
                          <span className="font-medium text-gray-700 dark:text-gray-300">{supplier.supplier}</span>
                          <span className="text-gray-500 dark:text-gray-400">
                            {supplier.price || 'Contact'} | {supplier.lead_time || 'TBD'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Forum Links */}
      {data.forum_solutions && data.forum_solutions.length > 0 && (
        <div className="pt-2 border-t border-gray-200 dark:border-gray-600">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1.5">Community solutions:</p>
          <div className="flex flex-wrap gap-1.5">
            {data.forum_solutions.slice(0, 3).map((forum, idx) => (
              <a
                key={idx}
                href={forum.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                {forum.source}
                <ExternalLink className="w-3 h-3" />
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Start Guided Diagnosis */}
      {onStartGuided && fault && (
        <div className="pt-3 mt-3 border-t border-gray-200 dark:border-gray-600">
          <button
            onClick={() => onStartGuided(`${fault.code} fault diagnosis`)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg text-sm font-medium text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
          >
            <Clipboard className="w-4 h-4" />
            Start Guided Diagnosis
          </button>
        </div>
      )}
    </div>
  );
}

// Suggestions message component
function SuggestionsMessage({ data }: { data: SuggestionsData }) {
  return (
    <div className="space-y-3">
      {data.suggestions && data.suggestions.length > 0 ? (
        <>
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span className="font-medium text-sm">Troubleshooting Suggestions</span>
          </div>
          <ul className="space-y-2">
            {data.suggestions.map((suggestion, idx) => (
              <li key={idx} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2.5">
                <p className="font-medium text-sm capitalize">{suggestion.problem}</p>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-0.5">{suggestion.solution}</p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{suggestion.source}</p>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
          <Info className="w-4 h-4" />
          <span className="text-sm">{data.note || 'No specific suggestions found.'}</span>
        </div>
      )}

      {/* Forum Links */}
      {data.forum_solutions && data.forum_solutions.length > 0 && (
        <div className="pt-2 border-t border-gray-200 dark:border-gray-600">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1.5">Search community forums:</p>
          <div className="flex flex-wrap gap-1.5">
            {data.forum_solutions.slice(0, 3).map((forum, idx) => (
              <a
                key={idx}
                href={forum.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                {forum.source}
                <ExternalLink className="w-3 h-3" />
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Vision analysis message component
function VisionMessage({ data }: { data: VisionData }) {
  const [showComponents, setShowComponents] = useState(true);
  const [showIssues, setShowIssues] = useState(true);

  const priorityColors = {
    immediate: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    soon: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    routine: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    none: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  };

  const severityColors = {
    critical: 'bg-red-500',
    high: 'bg-orange-500',
    medium: 'bg-yellow-500',
    low: 'bg-blue-500',
  };

  return (
    <div className="space-y-4">
      {/* Header with vision icon */}
      <div className="flex items-center gap-2">
        <Eye className="w-4 h-4 text-purple-500" />
        <span className="font-medium text-sm">Image Analysis</span>
        {data.maintenance_priority && (
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${priorityColors[data.maintenance_priority as keyof typeof priorityColors] || priorityColors.none}`}>
            {data.maintenance_priority.toUpperCase()}
          </span>
        )}
      </div>

      {/* General analysis text */}
      {data.analysis && (
        <p className="text-sm text-gray-700 dark:text-gray-300">
          {data.analysis}
        </p>
      )}

      {/* Model plate info */}
      {(data.manufacturer || data.model || data.serial) && (
        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Equipment Details:</p>
          <div className="space-y-1 text-sm">
            {data.manufacturer && (
              <p><span className="font-medium">Manufacturer:</span> {data.manufacturer}</p>
            )}
            {data.model && (
              <p><span className="font-medium">Model:</span> {data.model}</p>
            )}
            {data.serial && (
              <p><span className="font-medium">Serial:</span> {data.serial}</p>
            )}
          </div>
        </div>
      )}

      {/* Identified components */}
      {data.components && data.components.length > 0 && (
        <div>
          <button
            onClick={() => setShowComponents(!showComponents)}
            className="flex items-center gap-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
          >
            {showComponents ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Components Identified ({data.components.length})
          </button>
          {showComponents && (
            <ul className="mt-2 space-y-2">
              {data.components.map((component, idx) => (
                <li key={idx} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2.5">
                  <div className="flex items-start justify-between">
                    <p className="font-medium text-sm">{component.name}</p>
                    {component.confidence !== undefined && (
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {Math.round(component.confidence * 100)}% conf
                      </span>
                    )}
                  </div>
                  {component.manufacturer && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {component.manufacturer} {component.model || ''}
                    </p>
                  )}
                  {component.condition && (
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                      Condition: {component.condition}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Detected issues */}
      {data.issues && data.issues.length > 0 && (
        <div>
          <button
            onClick={() => setShowIssues(!showIssues)}
            className="flex items-center gap-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
          >
            {showIssues ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Issues Detected ({data.issues.length})
          </button>
          {showIssues && (
            <ul className="mt-2 space-y-2">
              {data.issues.map((issue, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm">
                  <span className={`mt-1.5 w-2 h-2 rounded-full flex-none ${severityColors[issue.severity as keyof typeof severityColors] || 'bg-gray-400'}`} />
                  <div>
                    <p className="font-medium capitalize">{issue.type}</p>
                    {issue.location && (
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Location: {issue.location}
                      </p>
                    )}
                    {issue.description && (
                      <p className="text-gray-600 dark:text-gray-400 text-sm mt-0.5">
                        {issue.description}
                      </p>
                    )}
                    {issue.recommendation && (
                      <p className="text-blue-600 dark:text-blue-400 text-xs mt-1">
                        → {issue.recommendation}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Fault codes detected */}
      {data.fault_codes && data.fault_codes.length > 0 && (
        <div className="pt-2 border-t border-gray-200 dark:border-gray-600">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1.5">Fault codes detected:</p>
          <div className="flex flex-wrap gap-1.5">
            {data.fault_codes.map((code, idx) => (
              <span
                key={idx}
                className="px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded text-xs font-mono"
              >
                {code}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Notes */}
      {data.notes && (
        <p className="text-xs text-gray-500 dark:text-gray-400 italic">
          {data.notes}
        </p>
      )}
    </div>
  );
}
