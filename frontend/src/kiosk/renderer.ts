/**
 * Kiosk Renderer — Phase 165.
 *
 * Pure functions: payload → SVG string.
 * No DOM manipulation — returns markup for root element innerHTML.
 */

import type { DecisionMomentPayload } from "./connection";
import { buildDecisionSurface } from "../lib/decisionSurface";

const SVG_W = 400;
const SVG_H = 600;
const FLOOR_GAP = 4;

/** Quiet mode: System Heartbeat — one rect per floor. */
export function renderQuiet(payload: DecisionMomentPayload | null): string {
  const now = new Date().toLocaleTimeString();

  if (!payload) {
    return `
      <div class="flex flex-col items-center justify-center h-screen gap-4">
        <div class="text-gray-500 text-sm tracking-widest uppercase">System Heartbeat</div>
        <svg width="${SVG_W}" height="80" viewBox="0 0 ${SVG_W} 80">
          <rect x="10" y="10" width="${SVG_W - 20}" height="60" rx="4"
            fill="#1f2937" stroke="#374151" stroke-width="1"/>
          <text x="${SVG_W / 2}" y="45" text-anchor="middle" fill="#6b7280" font-size="14">
            All Clear — ${now}
          </text>
        </svg>
      </div>`;
  }

  const stackOrder = payload.building_metadata.floor_stack_order;
  const labels = payload.building_metadata.floor_labels;
  const incMap = payload.active_incident_map;
  const floorH = Math.max(20, Math.floor((SVG_H - stackOrder.length * FLOOR_GAP) / stackOrder.length));

  const rects = stackOrder.map((floorId, i) => {
    const y = i * (floorH + FLOOR_GAP) + 10;
    const isAffected = incMap[floorId]?.affected;
    const fill = isAffected
      ? (payload.urgency_score >= 0.85 ? "#dc2626" : "#d97706")
      : "#1e3a5f";
    const label = labels[floorId] ?? floorId;
    return `
      <rect x="10" y="${y}" width="${SVG_W - 20}" height="${floorH}" rx="4"
        fill="${fill}" stroke="${isAffected ? "#ef4444" : "#1e40af"}" stroke-width="1"/>
      <text x="24" y="${y + floorH / 2 + 5}" fill="#e5e7eb" font-size="12">${label}</text>`;
  }).join("");

  return `
    <div class="flex flex-col items-center justify-center h-screen gap-4">
      <div class="text-gray-400 text-xs tracking-widest uppercase">Building Heartbeat</div>
      <svg width="${SVG_W}" height="${SVG_H}" viewBox="0 0 ${SVG_W} ${SVG_H}">
        ${rects}
      </svg>
      <div class="text-gray-600 text-xs">Updated ${now}</div>
    </div>`;
}

/** Crisis mode: Floor Stack — high-contrast incident overlay. */
export function renderCrisis(payload: DecisionMomentPayload): string {
  const surface = buildDecisionSurface(payload);
  const stackOrder = payload.building_metadata.floor_stack_order;
  const labels = payload.building_metadata.floor_labels;
  const incMap = payload.active_incident_map;
  const hasSpatialData = payload.building_metadata.has_spatial_data;
  const floorStack = payload.building_metadata.floor_stack;
  const isSupervisedMode = surface.behavior.showApproval;

  const floorH = Math.max(40, Math.floor((SVG_H - 80 - stackOrder.length * FLOOR_GAP) / stackOrder.length));

  const rects = stackOrder.map((floorId, i) => {
    const y = i * (floorH + FLOOR_GAP) + 10;
    const isAffected = incMap[floorId]?.affected;
    const fill = isAffected ? "#7f1d1d" : "#0f172a";
    const stroke = isAffected ? "#ef4444" : "#334155";
    const strokeW = isAffected ? 2 : 1;
    const label = labels[floorId] ?? floorId;

    // Equipment dots (Tier 1 renderer — only if spatial data available)
    let dots = "";
    if (hasSpatialData) {
      const floorDef = floorStack.find((f) => f.floor_id === floorId);
      if (floorDef && floorDef.floor_width_m > 0) {
        dots = floorDef.equipment_positions
          .slice(0, 20) // cap at 20 dots per floor
          .map((ep) => {
            const dotX = 10 + ((ep.x / floorDef.floor_width_m) * (SVG_W - 20));
            const dotY = y + (ep.y / (floorDef.floor_depth_m || 1)) * floorH;
            const color = ep.type === "chiller" ? "#38bdf8"
              : ep.type === "gen" ? "#fbbf24"
              : "#94a3b8";
            return `<circle cx="${dotX.toFixed(1)}" cy="${dotY.toFixed(1)}"
              r="3" fill="${color}" opacity="0.8"/>`;
          })
          .join("");
      }
    }

    const pulse = isAffected
      ? `<animate attributeName="stroke-opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite"/>`
      : "";

    return `
      <rect x="10" y="${y}" width="${SVG_W - 20}" height="${floorH}" rx="4"
        fill="${fill}" stroke="${stroke}" stroke-width="${strokeW}">
        ${pulse}
      </rect>
      <text x="18" y="${y + 16}" fill="${isAffected ? '#fca5a5' : '#94a3b8'}"
        font-size="11" font-weight="${isAffected ? 'bold' : 'normal'}">${label}</text>
      ${dots}`;
  }).join("");

  const approveBtn = isSupervisedMode ? `
    <div class="mt-4">
      <button id="kiosk-approve-btn"
        class="px-8 py-3 bg-red-600 hover:bg-red-500 text-white font-bold rounded
               text-sm tracking-widest uppercase border border-red-400 transition-colors"
        data-action="${payload.recommended_action}"
        data-building="${payload.building_id}">
        HOLD TO APPROVE
      </button>
    </div>` : "";

  return `
    <div class="flex flex-col items-center justify-center min-h-screen gap-4 p-4">
      <div class="text-red-400 text-xs tracking-widest uppercase font-bold">&#9888; Incident Active</div>
      <svg width="${SVG_W}" height="${SVG_H - 80}" viewBox="0 0 ${SVG_W} ${SVG_H - 80}"
        class="border border-red-900 rounded">
        ${rects}
      </svg>
      <div class="max-w-xl w-full grid grid-cols-1 gap-3 text-left">
        <div class="border border-slate-800 rounded p-3 bg-slate-950/80">
          <div class="text-[10px] tracking-widest uppercase text-slate-400 mb-1">Cause</div>
          <div class="text-amber-300 text-sm leading-relaxed">${surface.cause}</div>
        </div>
        <div class="border border-slate-800 rounded p-3 bg-slate-950/80">
          <div class="text-[10px] tracking-widest uppercase text-slate-400 mb-1">Impact</div>
          <div class="text-slate-100 text-sm leading-relaxed">${surface.impact}</div>
          <div class="text-slate-400 text-xs leading-relaxed mt-2">${surface.action.tradeoff}</div>
        </div>
        <div class="border border-slate-800 rounded p-3 bg-slate-950/80">
          <div class="text-[10px] tracking-widest uppercase text-slate-400 mb-1">Time</div>
          <div class="text-slate-400 text-xs">${surface.time.label}</div>
          <div class="text-white text-xl font-bold mt-1">${surface.time.value}</div>
          <div class="text-slate-400 text-xs mt-1">${surface.time.detail}</div>
        </div>
        <div class="border border-slate-800 rounded p-3 bg-slate-950/80">
          <div class="text-[10px] tracking-widest uppercase text-slate-400 mb-1">Action</div>
          <div class="text-slate-100 text-sm leading-relaxed">${surface.action.summary}</div>
          ${!surface.behavior.showResultOnly ? `
            <div class="text-white text-sm font-semibold mt-2">${surface.action.operatorPrompt}</div>
          ` : ''}
          <div class="text-slate-400 text-xs leading-relaxed mt-2">${surface.action.expectedOutcome}</div>
          ${surface.behavior.showInstructions && surface.action.bmsGuide ? `
            <div class="text-slate-500 text-[11px] leading-relaxed mt-2">${surface.action.bmsGuide.navigationPath.join(' -> ')}</div>
          ` : ''}
          ${surface.behavior.showResultOnly ? `
            <div class="${surface.mode === 'autonomous' ? 'text-emerald-400' : 'text-slate-500'} text-[10px] uppercase tracking-widest mt-3">
              ${surface.mode === 'autonomous' ? 'SENTINEL executed — verifying' : 'Ghost mode — observe only'}
            </div>
          ` : ''}
        </div>
      </div>
      ${approveBtn}
    </div>`;
}
