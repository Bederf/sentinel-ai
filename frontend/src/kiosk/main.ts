/**
 * Kiosk Entry Point — Phase 165.
 *
 * Stateless: poll → render → repeat.
 * No component tree, no state management, no framework.
 */

import { startConnection } from "./connection";
import { renderQuiet, renderCrisis } from "./renderer";
import type { DecisionMomentPayload } from "./connection";

const root = document.getElementById("kiosk-root");

// connection holds stop() + dismiss() — wired to APPROVE button in crisis mode
const connection = startConnection(render);

function render(payload: DecisionMomentPayload | null): void {
  if (!root) return;
  if (!payload || payload.renderer_hint === "quiet") {
    root.innerHTML = renderQuiet(payload);
  } else {
    root.innerHTML = renderCrisis(payload);
    wireApproveButton();
  }
}

function wireApproveButton(): void {
  const btn = document.getElementById("kiosk-approve-btn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    btn.textContent = "Submitting\u2026";
    btn.setAttribute("disabled", "true");
    try {
      const action = btn.getAttribute("data-action") ?? "";
      const buildingId = btn.getAttribute("data-building") ?? "";
      await fetch("/api/decision/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, building_id: buildingId }),
      });
      btn.textContent = "\u2713 Approved";
      // Dismiss: suppress re-trigger for 30 minutes (building profile default)
      // Next poll within the window will render quiet even if urgency is still high
      connection.dismiss();
    } catch {
      btn.textContent = "Error \u2014 retry";
      btn.removeAttribute("disabled");
    }
  });
}

// Show loading state immediately
render(null);
