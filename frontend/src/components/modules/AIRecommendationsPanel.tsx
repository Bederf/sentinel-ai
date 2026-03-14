/**
 * AI Recommendations Panel - Unified View
 *
 * Aggregates and displays AI recommendations from all active modules.
 * Shows cross-system recommendations when multiple modules are active.
 */

import { useState } from 'react';
import { Card, Title, Text, Badge, Flex, Button, Select, SelectItem } from '@tremor/react';
import { useModules, useCriticalRecommendations, useCrossSystemRecommendations } from '../../contexts/ModuleHooks';
import { PRIORITY_COLORS, MODULE_COLORS } from '../../lib/moduleRegistry';
import type { AIRecommendation, ModuleType } from '../../lib/moduleRegistry';

interface AIRecommendationsPanelProps {
  compact?: boolean;
  maxItems?: number;
  moduleFilter?: ModuleType;
}

export function AIRecommendationsPanel({
  compact = false,
  maxItems = 10,
  moduleFilter,
}: AIRecommendationsPanelProps) {
  const {
    recommendations,
    activeModules,
    acknowledgeRecommendation,
    resolveRecommendation,
  } = useModules();

  const criticalRecs = useCriticalRecommendations();
  const crossSystemRecs = useCrossSystemRecommendations();

  const [filter, setFilter] = useState<'all' | 'critical' | 'cross_system' | ModuleType>('all');

  // Filter recommendations
  let filteredRecs = recommendations.filter(r => !r.resolved);

  if (moduleFilter) {
    filteredRecs = filteredRecs.filter(
      r => r.source_module === moduleFilter || r.related_modules.includes(moduleFilter)
    );
  } else if (filter === 'critical') {
    filteredRecs = criticalRecs;
  } else if (filter === 'cross_system') {
    filteredRecs = crossSystemRecs;
  } else if (filter !== 'all') {
    filteredRecs = filteredRecs.filter(r => r.source_module === filter);
  }

  // Limit items
  const displayRecs = filteredRecs.slice(0, maxItems);

  if (compact) {
    return (
      <Card decoration="top" decorationColor={criticalRecs.length > 0 ? 'red' : 'blue'}>
        <Flex justifyContent="between" alignItems="center">
          <div>
            <Text className="text-sm font-medium">AI Recommendations</Text>
            <Text className="text-2xl font-bold">{filteredRecs.length}</Text>
            <Text className="text-xs text-gray-400 italic">AI-generated</Text>
          </div>
          {criticalRecs.length > 0 && (
            <Badge color="red" size="lg">{criticalRecs.length} Critical</Badge>
          )}
          {crossSystemRecs.length > 0 && (
            <Badge color="purple" size="lg">{crossSystemRecs.length} Cross-System</Badge>
          )}
        </Flex>
        {displayRecs.length > 0 && (
          <div className="mt-3 space-y-2">
            {displayRecs.slice(0, 3).map(rec => (
              <div
                key={rec.recommendation_id}
                className={`p-2 rounded text-sm ${
                  rec.priority === 'critical' ? 'bg-red-50' :
                  rec.priority === 'high' ? 'bg-amber-50' :
                  'bg-gray-50'
                }`}
              >
                <Text className="font-medium truncate">{rec.title}</Text>
              </div>
            ))}
          </div>
        )}
      </Card>
    );
  }

  return (
    <Card>
      <Flex justifyContent="between" alignItems="start">
        <div>
          <Title>AI Recommendations</Title>
          <Text className="text-xs text-gray-500">
            {activeModules.length} module(s) active
          </Text>
          <Text className="text-xs text-gray-400 mt-0.5 italic">
            AI-generated recommendations &middot; Review before acting
          </Text>
        </div>
        <div className="flex gap-2">
          {criticalRecs.length > 0 && (
            <Badge color="red" size="lg">{criticalRecs.length} Critical</Badge>
          )}
          {crossSystemRecs.length > 0 && (
            <Badge color="purple">{crossSystemRecs.length} Cross-System</Badge>
          )}
        </div>
      </Flex>

      {/* Filter */}
      {!moduleFilter && (
        <div className="mt-4">
          <Select
            value={filter}
            onValueChange={(v: any) => setFilter(v)}
            placeholder="Filter recommendations"
          >
            <SelectItem value="all">All Recommendations</SelectItem>
            <SelectItem value="critical">Critical Only</SelectItem>
            <SelectItem value="cross_system">Cross-System Only</SelectItem>
            {activeModules.map(m => (
              <SelectItem key={m.module_type} value={m.module_type}>
                {m.module_type.toUpperCase()} Module
              </SelectItem>
            ))}
          </Select>
        </div>
      )}

      {/* Recommendations List */}
      <div className="mt-4 space-y-3">
        {displayRecs.length === 0 ? (
          <Text className="text-gray-500 text-center py-4">
            No active recommendations
          </Text>
        ) : (
          displayRecs.map(rec => (
            <RecommendationCard
              key={rec.recommendation_id}
              recommendation={rec}
              onAcknowledge={() => acknowledgeRecommendation(rec.recommendation_id)}
              onResolve={() => resolveRecommendation(rec.recommendation_id)}
            />
          ))
        )}
      </div>

      {filteredRecs.length > maxItems && (
        <Text className="text-center text-gray-500 mt-4 text-sm">
          +{filteredRecs.length - maxItems} more recommendations
        </Text>
      )}
    </Card>
  );
}

interface RecommendationCardProps {
  recommendation: AIRecommendation;
  onAcknowledge: () => void;
  onResolve: () => void;
}

function RecommendationCard({ recommendation, onAcknowledge, onResolve }: RecommendationCardProps) {
  const priorityStyles = {
    critical: 'border-red-500 bg-red-50',
    high: 'border-amber-500 bg-amber-50',
    medium: 'border-blue-500 bg-blue-50',
    low: 'border-gray-300 bg-gray-50',
  };

  return (
    <div
      className={`p-3 rounded-lg border-l-4 ${priorityStyles[recommendation.priority]}`}
    >
      <Flex justifyContent="between" alignItems="start">
        <div className="flex-1">
          <Flex alignItems="center" className="gap-2 mb-1">
            <Badge color={recommendation.source === 'health_alert' ? 'orange' : recommendation.source === 'ai_optimizer' ? 'sky' : 'sky'} size="xs">
              {recommendation.source === 'health_alert' ? 'Health Alert'
                : recommendation.source === 'ai_optimizer' ? 'AI Optimization'
                : recommendation.source === 'financial_roi' ? 'ROI'
                : 'AI'}
            </Badge>
            <Badge color={MODULE_COLORS[recommendation.source_module] || 'gray'} size="xs">
              {recommendation.source_module.toUpperCase()}
            </Badge>
            <Badge color={PRIORITY_COLORS[recommendation.priority]} size="xs">
              {recommendation.priority}
            </Badge>
            {recommendation.recommendation_type === 'cross_system' && (
              <Badge color="purple" size="xs">Cross-System</Badge>
            )}
            {recommendation.auto_actionable && (
              <Badge color="green" size="xs">Auto</Badge>
            )}
          </Flex>
          <Text className="font-medium">{recommendation.title}</Text>
          <Text className="text-xs text-gray-600 mt-1">{recommendation.description}</Text>

          {/* Related modules */}
          {recommendation.related_modules.length > 0 && (
            <div className="flex gap-1 mt-2">
              <Text className="text-xs text-gray-500">Related:</Text>
              {recommendation.related_modules.map(m => (
                <Badge key={m} color={MODULE_COLORS[m] || 'gray'} size="xs">
                  {m}
                </Badge>
              ))}
            </div>
          )}

          {/* Confidence */}
          <Text className="text-xs text-gray-400 mt-1">
            Confidence: {((recommendation.confidence ?? 0) * 100).toFixed(0)}%
          </Text>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-1 ml-2">
          {!recommendation.acknowledged && (
            <Button size="xs" variant="secondary" onClick={onAcknowledge}>
              Ack
            </Button>
          )}
          <Button size="xs" variant="primary" color="green" onClick={onResolve}>
            Resolve
          </Button>
        </div>
      </Flex>

      {/* Timestamp */}
      <Text className="text-xs text-gray-400 mt-2">
        {new Date(recommendation.timestamp).toLocaleString()}
      </Text>
    </div>
  );
}

export default AIRecommendationsPanel;
