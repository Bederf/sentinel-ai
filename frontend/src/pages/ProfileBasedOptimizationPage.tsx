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
import { TabGroup, TabList, Tab, TabPanels, TabPanel } from '@tremor/react'
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
  const [siteId, setSiteId] = useState<string>('site-002')
  const [loading, setLoading] = useState(true)

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
    <div className="h-full overflow-y-auto p-4 md:p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">Profile-Based Optimization</h1>
          <p className="text-gray-600">
            Manage optimization profiles, review recommendations, and track execution outcomes
          </p>
        </div>

        <TabGroup>
          <TabList>
            <Tab>Settings</Tab>
            <Tab>Pending Recommendations</Tab>
            <Tab>History</Tab>
          </TabList>

          <TabPanels>
            <TabPanel>
              <div className="mt-6">
                <ProfileSettings
                  siteId={siteId}
                  onProfileChange={handleProfileChange}
                />
              </div>
            </TabPanel>

            <TabPanel>
              <div className="mt-6">
                <RecommendationsDashboard siteId={siteId} />
              </div>
            </TabPanel>

            <TabPanel>
              <div className="mt-6">
                <RecommendationHistory siteId={siteId} />
              </div>
            </TabPanel>
          </TabPanels>
        </TabGroup>
      </div>
    </div>
  )
}
