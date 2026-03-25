import { useCallback, useEffect, useState } from "react";
import { useHealthThresholds } from "../../hooks/useHealthThresholds";
import { useRiskThresholds } from "../../hooks/useRiskThresholds";
import { useModules } from "../../contexts/ModuleHooks";
import { useBuildingsList } from "../../hooks/useBuildingsList";
import { AUTH_EXPIRED_EVENT } from "../../lib/api";
import { setStoredSelectedSite } from "../../lib/siteSelection";
import {
  BASE_PACK_LOCKED_MODULES,
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
  canManageFeatureAccess: boolean,
  isDemoUser: boolean,
  settingsPageUnlocked: boolean,
  onError?: (error: string) => void,
  onSaveSuccess?: (durationMs: number) => void
) {
  const [mlTrainingEnabled, setMlTrainingEnabled] = useState(false);
  const [mlTrainingLoading, setMlTrainingLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("sentinel_token");
    if (!token) {
      setMlTrainingLoading(false);
      return;
    }

    fetch("/api/settings/ml-training", { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data) setMlTrainingEnabled(!!data.enabled);
      })
      .catch(() => {})
      .finally(() => setMlTrainingLoading(false));
  }, []);

  const handleMlTrainingToggle = useCallback(async () => {
    if (isDemoUser && !settingsPageUnlocked) {
      onError?.("Settings page is locked. Click 'Unlock to Edit' at the top to make changes.");
      return;
    }
    if (!canManageFeatureAccess && !isDemoUser) {
      onError?.("Only admins can change ML training settings.");
      return;
    }

    const token = localStorage.getItem("sentinel_token");
    if (!token) return;

    const newValue = !mlTrainingEnabled;
    setMlTrainingLoading(true);
    try {
      const response = await fetch("/api/settings/ml-training", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
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
    canManageFeatureAccess,
    isDemoUser,
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
  canManageFeatureAccess,
  deactivateModule,
  isDemoUser,
  isModuleActive,
  onError,
  settingsPageUnlocked,
  showSaveSuccess,
}: {
  activateModule: ReturnType<typeof useModules>["activateModule"];
  canManageFeatureAccess: boolean;
  deactivateModule: ReturnType<typeof useModules>["deactivateModule"];
  isDemoUser: boolean;
  isModuleActive: ReturnType<typeof useModules>["isModuleActive"];
  onError?: (error: string) => void;
  settingsPageUnlocked: boolean;
  showSaveSuccess: (durationMs: number) => void;
}) {
  const [togglingCardId, setTogglingCardId] = useState<string | null>(null);

  const handleFeatureToggle = useCallback(async (card: FeatureToggleCard) => {
    if (isDemoUser && !settingsPageUnlocked) {
      onError?.("Settings page is locked. Click 'Unlock to Edit' at the top to make changes.");
      return;
    }
    if (!canManageFeatureAccess && !isDemoUser) {
      onError?.("Only admins can change feature access.");
      return;
    }

    const currentlyActive = isModuleActive(card.moduleType);
    const locked = currentlyActive && BASE_PACK_LOCKED_MODULES.includes(card.moduleType);
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
    canManageFeatureAccess,
    deactivateModule,
    isDemoUser,
    isModuleActive,
    onError,
    settingsPageUnlocked,
    showSaveSuccess,
  ]);

  return { handleFeatureToggle, togglingCardId };
}

export function useSettingsController({ siteId, onError }: UseSettingsControllerParams) {
  const {
    thresholds: healthThresholds,
    loading: healthThresholdLoading,
    error: healthThresholdError,
    updateThresholds: updateHealthThresholds,
  } = useHealthThresholds();
  const {
    thresholds: riskThresholds,
    loading: riskThresholdLoading,
    error: riskThresholdError,
    updateThresholds: updateRiskThresholds,
  } = useRiskThresholds();
  const { data: buildings = [] } = useBuildingsList();
  const { isModuleActive, activateModule, deactivateModule, setSite: setModuleSite } = useModules();

  const currentUser = getStoredSentinelUser();
  const currentUserEmail = currentUser.email || "";
  const currentUserRole = currentUser.role || "auditor";
  const hasSessionToken = !!localStorage.getItem("sentinel_token");
  const demoUserEmails = ["grant@grantdemo.co.za", "bederf@protonmail.com", "bederf@gmail.com"];

  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(siteId || null);
  const [settingsPageUnlocked, setSettingsPageUnlocked] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const { saveSuccess, showSaveSuccess } = useSaveSuccessState();

  const isDemoUser = !!(currentUserEmail && demoUserEmails.includes(currentUserEmail.toLowerCase()));
  const canManageFeatureAccess = currentUserRole === "admin";
  const readOnly = !!(isDemoUser && !settingsPageUnlocked);
  const canToggleModules = canManageFeatureAccess || (isDemoUser && settingsPageUnlocked);
  const loading = healthThresholdLoading || riskThresholdLoading;

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
  }, [buildings, selectedSiteId, setModuleSite]);

  useEffect(() => {
    if (currentUserEmail && !hasSessionToken) {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
  }, [currentUserEmail, hasSessionToken]);

  const { handleMlTrainingToggle, mlTrainingEnabled, mlTrainingLoading } = useMlTrainingSettings(
    canManageFeatureAccess,
    isDemoUser,
    settingsPageUnlocked,
    onError,
    showSaveSuccess
  );
  const { handleFeatureToggle, togglingCardId } = useFeatureToggleActions({
    activateModule,
    canManageFeatureAccess,
    deactivateModule,
    isDemoUser,
    isModuleActive,
    onError,
    settingsPageUnlocked,
    showSaveSuccess,
  });

  const handleSuccess = useCallback(() => {
    showSaveSuccess(3000);
  }, [showSaveSuccess]);

  const handleSaveThresholds = useCallback(async (newThresholds: {
    healthy: number;
    warning: number;
    critical: number;
  }) => {
    const success = await updateHealthThresholds(newThresholds);
    if (success) {
      showSaveSuccess(3000);
      return;
    }
    onError?.("Failed to update thresholds");
  }, [onError, showSaveSuccess, updateHealthThresholds]);

  const handleSaveRiskThresholds = useCallback(async (newThresholds: {
    medium: number;
    high: number;
    critical: number;
  }) => {
    const success = await updateRiskThresholds(newThresholds);
    if (success) {
      showSaveSuccess(3000);
      return;
    }
    onError?.("Failed to update risk thresholds");
  }, [onError, showSaveSuccess, updateRiskThresholds]);

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
    handleFeatureToggle,
    handleMlTrainingToggle,
    handleSaveRiskThresholds,
    handleSaveThresholds,
    handleSiteChange,
    handleSuccess,
    hasSessionToken,
    healthThresholdError,
    healthThresholds,
    isDemoUser,
    isModuleActive,
    loading,
    mlTrainingEnabled,
    mlTrainingLoading,
    readOnly,
    riskThresholdError,
    riskThresholds,
    saveSuccess,
    selectedSiteId,
    settingsPageUnlocked,
    setSettingsPageUnlocked,
    setShowPasswordModal,
    showPasswordModal,
    togglingCardId,
  };
}
