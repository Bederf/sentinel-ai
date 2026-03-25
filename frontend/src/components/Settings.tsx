import { memo } from "react";
import type { View } from "../lib/navigation";
import { SettingsPageView } from "./settings/SettingsPageView";
import { useSettingsController } from "./settings/useSettingsController";

interface SettingsProps {
  siteId?: string;
  onError?: (error: string) => void;
  onNavigate?: (view: View) => void;
}

export const Settings = memo(function Settings({ siteId, onError, onNavigate }: SettingsProps) {
  const controller = useSettingsController({ siteId, onError });
  return <SettingsPageView controller={controller} onError={onError} onNavigate={onNavigate} />;
});

export default Settings;
