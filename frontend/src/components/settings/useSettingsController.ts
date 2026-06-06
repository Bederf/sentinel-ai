import { useCallback, useEffect, useState } from "react";
import { useSiteThresholds } from "../../hooks/useHealthThresholds";
import { useModules } from "../../contexts/ModuleHooks";
import { useBuildingsList } from "../../hooks/useBuildingsList";
import { setStoredSelectedSite } from "../../lib/siteSelection";
import { authorizedFetch, getAccessToken } from "@/lib/api";
import {
  type FeatureToggleCard,
} from "./settingsCatalog";

interface UseSettingsControllerParams {
  siteId?: string;
  onError?: (error: string) => void;
}

interface SentinelUser {
  email?: string;
  role?: string;
}

interface SaveSuccessState {
  saveSuccess: boolean;
  showSaveSuccess: (durationMs: number) => void;
}

function getStoredSentinelUser(): SentinelUser {
  try {
    const raw = localStorage.getItem("sentinel_user");
    if (!raw) return {};
    return JSON.parse(raw) as SentinelUser;
  } catch {
    return {};
  }
}

function useSaveSuccessState(): SaveSuccessState {
  const [saveSuccess, setSaveSuccess] = useState(false);

  const showSaveSuccess = useCallback((durationMs: number) => {
    setSaveSuccess(true);
    window.setTimeout(() => setSaveSuccess(false), durationMs);
  }, []);

  return { saveSuccess, showSaveSuccess };
}

function useMlTrainingSettings(
  isAdmin: boolean,
  settingsPageUnlocked: boolean,
  onError?: (error: string) => void,
  onSaveSuccess?: (durationMs: number) => void
) {
  const [mlTrainingEnabled, setMlTrainingEnabled] = useState(false);
  const [mlTrainingLoading, setMlTrainingLoading] = useState(true);

  useEffect(() => {
    authorizedFetch("/api/settings/ml-training")
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data) setMlTrainingEnabled(!!data.enabled);
      })
      .catch(() => {})
      .finally(() => setMlTrainingLoading(false));
  }, []);

  const handleMlTrainingToggle = useCallback(async () => {
    if (!isAdmin && !settingsPageUnlocked) {
      onError?.("Settings page is locked. Click 'Unlock to Edit' at the top to make changes.");
      return;
    }
    if (!isAdmin) {
      onError?.("Only admins can change ML training settings.");
      return;
    }

    const newValue = !mlTrainingEnabled;
    setMlTrainingLoading(true);
    try {
      const response = await authorizedFetch("/api/settings/ml-training", {
        method: "PUT",
        body: JSON.stringify({ enabled: newValue }),
      });
      if (!response.ok) throw new Error("Failed to update ML training setting");
      setMlTrainingEnabled(newValue);
      onSaveSuccess?.(2000);
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "Failed to update ML training setting");
    } finally {
      setMlTrainingLoading(false);
    }
  }, [
    isAdmin,
    mlTrainingEnabled,
    onError,
    onSaveSuccess,
    settingsPageUnlocked,
  ]);

  return {
    handleMlTrainingToggle,
    mlTrainingEnabled,
    mlTrainingLoading,
  };
}

function useFeatureToggleActions({
  activateModule,
  canManageFeatureAccess: _canManageFeatureAccess,
  deactivateModule,
  isAdmin,
  isMandatory,
  isModuleActive,
  onError,
  settingsPageUnlocked,
  showSaveSuccess,
}: {
  activateModule: ReturnType<typeof useModules>["activateModule"];
  canManageFeatureAccess: boolean;
  deactivateModule: ReturnType<typeof useModules>["deactivateModule"];
  isAdmin: boolean;
  isMandatory: ReturnType<typeof useModules>["isMandatory"];
  isModuleActive: ReturnType<typeof useModules>["isModuleActive"];
  onError?: (error: string) => void;
  settingsPageUnlocked: boolean;
  showSaveSuccess: (durationMs: number) => void;
}) {
  const [togglingCardId, setTogglingCardId] = useState<string | null>(null);

  const handleFeatureToggle = useCallback(async (card: FeatureToggleCard) => {
    if (!isAdmin && !settingsPageUnlocked) {
      onError?.("Settings page is locked. Click 'Unlock to Edit' at the top to make changes.");
      return;
    }
    if (!isAdmin) {
      onError?.("Only admins can change feature access.");
      return;
    }

    const currentlyActive = isModuleActive(card.moduleType);
    const locked = currentlyActive && isMandatory(card.moduleType);
    if (locked) return;

    setTogglingCardId(card.id);
    try {
      if (currentlyActive) {
        await deactivateModule(card.moduleType);
      } else {
        await activateModule(card.moduleType);
      }
      showSaveSuccess(2000);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update feature toggle";
      onError?.(message);
    } finally {
      setTogglingCardId(null);
    }
  }, [
    activateModule,
    isAdmin,
    deactivateModule,
    isMandatory,
    isModuleActive,
    onError,
    settingsPageUnlocked,
    showSaveSuccess,
  ]);

  return { handleFeatureToggle, togglingCardId };
}

export function useSettingsController({ siteId, onError }: UseSettingsControllerParams) {
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(siteId || null);
  const {
    thresholds: siteThresholds,
    loading: siteThresholdLoading,
    error: siteThresholdError,
    updateSiteThresholds,
  } = useSiteThresholds(selectedSiteId ?? undefined);
  const { data: buildings = [] } = useBuildingsList();
  const { availableModules, isModuleActive, isMandatory, activateModule, deactivateModule, setSite: setModuleSite } = useModules();

  const currentUser = getStoredSentinelUser();
  const currentUserRole = currentUser.role || "auditor";
  const currentUserEmail = currentUser.email || "";
  const hasSessionToken = !!getAccessToken();

  const [settingsPageUnlocked, setSettingsPageUnlocked] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const { saveSuccess, showSaveSuccess } = useSaveSuccessState();

  const canManageFeatureAccess = currentUserRole === "admin";
  const readOnly = currentUserRole !== "admin" && !settingsPageUnlocked;
  const canToggleModules = currentUserRole === "admin";
  const [sitePhase, setSitePhase] = useState<string | null>(null);
  const loading = siteThresholdLoading;

  useEffect(() => {
    if (siteId && siteId !== selectedSiteId) {
      const syncHandle = window.setTimeout(() => setSelectedSiteId(siteId), 0);
      return () => window.clearTimeout(syncHandle);
    }
    return undefined;
  }, [siteId, selectedSiteId]);

  useEffect(() => {
    if (!selectedSiteId) return;
    const selectedSiteName = buildings.find((building) => building.id === selectedSiteId)?.name || selectedSiteId;
    setModuleSite(selectedSiteId, selectedSiteName);
    // Fetch site phase for control toggle gating
    import('@/lib/api').then(({ api }) =>
      api.getSiteMode(selectedSiteId).then((r: any) =>
        setSitePhase((r as any).current_stage || null)
      ).catch(() => {})
    ).catch(() => {});
  }, [buildings, selectedSiteId, setModuleSite]);

  const { handleMlTrainingToggle, mlTrainingEnabled, mlTrainingLoading } = useMlTrainingSettings(
    currentUserRole === "admin",
    settingsPageUnlocked,
    onError,
    showSaveSuccess
  );
  const { handleFeatureToggle, togglingCardId } = useFeatureToggleActions({
    activateModule,
    canManageFeatureAccess,
    deactivateModule,
    isAdmin: currentUserRole === "admin",
    isMandatory,
    isModuleActive,
    onError,
    settingsPageUnlocked,
    showSaveSuccess,
  });

  const handleSuccess = useCallback(() => {
    showSaveSuccess(3000);
  }, [showSaveSuccess]);

  const handleSaveSiteThresholds = useCallback(async (thresholds: {
    health: { healthy: number; warning: number; critical: number };
    risk: { medium: number; high: number; critical: number };
  }) => {
    const success = await updateSiteThresholds(thresholds);
    if (success) {
      showSaveSuccess(3000);
      return;
    }
    onError?.("Failed to update thresholds");
  }, [onError, showSaveSuccess, updateSiteThresholds]);

  const handleSiteChange = useCallback((nextSiteId: string | null) => {
    if (!nextSiteId) return;
    setSelectedSiteId(nextSiteId);
    setStoredSelectedSite(nextSiteId);
  }, [setSelectedSiteId]);

  return {
    buildings,
    canManageFeatureAccess,
    canToggleModules,
    currentUserEmail,
    currentUserRole,
    handleFeatureToggle,
    handleMlTrainingToggle,
    handleSaveSiteThresholds,
    handleSiteChange,
    handleSuccess,
    hasSessionToken,
    availableModules,
    siteThresholdError,
    siteThresholds,
    isModuleActive,
    loading,
    mlTrainingEnabled,
    mlTrainingLoading,
    readOnly,
    saveSuccess,
    selectedSiteId,
    settingsPageUnlocked,
    setSettingsPageUnlocked,
    setShowPasswordModal,
    showPasswordModal,
    togglingCardId,
    canToggleControl: sitePhase === "supervised" || sitePhase === "auto",
  };
}
