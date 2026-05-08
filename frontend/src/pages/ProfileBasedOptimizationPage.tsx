/**
 * ProfileBasedOptimizationPage - Profile Selection and Recommendation Approval Workflow
 *
 * Features:
 * - Profile selector (Asset Sweating, Comfort First, Cost Saving)
 * - Pending recommendations with approve/reject workflow
 * - Recommendation history with outcome accuracy tracking
 * - Zone overrides management
 *
 * Integrated workflow for multi-objective optimization.
 */

import { useState, useEffect } from 'react'
import { TabBar } from '../components/TabBar';
import { Settings, TrendingUp } from 'lucide-react'
import { PageLoading } from '../components/PageLoading'
import { ProfileSettings } from '../components/optimization/ProfileSettings'
import { RecommendationsDashboard } from '../components/optimization/RecommendationsDashboard'
import { RecommendationHistory } from '../components/optimization/RecommendationHistory'

interface ProfileBasedOptimizationPageProps {
  onError?: (error: string) => void
}

export const ProfileBasedOptimizationPage: React.FC<
  ProfileBasedOptimizationPageProps
> = () => {
  const [siteId, setSiteId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState("settings")

  useEffect(() => {
    // Initialize site ID from session or default
    const storedSite = sessionStorage.getItem('sentinel_selected_site')
    if (storedSite) {
      setSiteId(storedSite)
    }
    setLoading(false)
  }, [])

  const handleProfileChange = () => {
    // Profile change is handled within ProfileSettings component
  }

  if (loading) {
    return <PageLoading message="Loading optimization settings..." />
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded" style={{ background: "rgba(245, 158, 11, 0.15)" }}>
            <Settings className="h-6 w-6" style={{ color: "var(--color-sentinel-amber)" }} />
          </div>
          <div>
            <h1 className="text-3xl font-bold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Profile-Based Optimization
            </h1>
            <p style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Manage optimization profiles, review recommendations, and track execution outcomes
            </p>
          </div>
        </div>

        <TabBar
          tabs={[
            { id: "settings", label: "Settings" },
            { id: "pending", label: "Pending" },
            { id: "history", label: "History" },
          ]}
          active={activeTab}
          onChange={setActiveTab}
          accentColor="var(--color-sentinel-amber)"
          style={{ marginBottom: 16 }}
        />

        {activeTab === "settings" && (
          <div className="mt-6 space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <div className="p-2 rounded" style={{ background: "rgba(245, 158, 11, 0.15)" }}>
                <Settings className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
              </div>
              <div>
                <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Optimization Profile Settings
                </h3>
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Select profile and configure business priorities
                </span>
              </div>
            </div>
            <ProfileSettings
              siteId={siteId}
              onProfileChange={handleProfileChange}
            />
          </div>
        )}

        {activeTab === "pending" && (
          <div className="mt-6 space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
                <TrendingUp className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
              </div>
              <div>
                <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Pending Recommendations
                </h3>
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Review and approve optimization actions
                </span>
              </div>
            </div>
            <RecommendationsDashboard siteId={siteId} />
          </div>
        )}

        {activeTab === "history" && (
          <div className="mt-6 space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <div className="p-2 rounded" style={{ background: "rgba(16, 185, 129, 0.15)" }}>
                <TrendingUp className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
              </div>
              <div>
                <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Execution History
                </h3>
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Track recommendation outcomes and accuracy
                </span>
              </div>
            </div>
            <RecommendationHistory siteId={siteId} />
          </div>
        )}
      </div>
    </div>
  )
}
