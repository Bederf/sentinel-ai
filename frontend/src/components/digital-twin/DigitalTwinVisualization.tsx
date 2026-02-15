// @ts-nocheck
/**
 * DIGITAL TWIN VISUALIZATION
 * ───────────────────────────
 * 3D Interactive building visualization with equipment monitoring
 * Integrates real-time equipment data from SENTINEL BMS
 */

import React, { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { devicesApi, equipmentApi } from '@/lib/api';
import type { Device, Equipment } from '@/lib/api';

interface EquipmentData {
  id: string;
  name: string;
  code: string;
  type: string;
  floor: number;
  x: number;
  z: number;
  status: 'online' | 'warning' | 'fault' | 'offline';
  readings: Record<string, number | boolean | string>;
  alerts: Array<{
    id: string;
    severity: 'critical' | 'warning' | 'info';
    text: string;
    time: string;
    ack: boolean;
  }>;
  maintenance?: {
    last_service?: string;
    next_service?: string;
  };
}

interface DetailedEquipment extends EquipmentData {
  // Extended for detail panel
}

const TYPE_COLORS: Record<string, string> = {
  ahu: '#2E86AB',
  vav: '#3AAFDE',
  fcu: '#6366F1',
  mcc: '#E8913A',
  db: '#F59E0B',
  ups: '#D97706',
  dali: '#FBBF24',
  sensor: '#10B981',
  solar: '#F97316',
  bess: '#22C55E',
  chiller: '#0EA5E9',
  pump: '#06B6D4',
  fire_panel: '#DC2626',
  cctv: '#6B7280',
  access: '#7C3AED',
};

const STATUS_COLORS: Record<string, string> = {
  online: '#22C55E',
  warning: '#F59E0B',
  offline: '#6B7280',
  fault: '#EF4444',
};

const FLOOR_NAMES = ['Ground Floor', 'First Floor', 'Second Floor', 'Third Floor', 'Roof'];

const LABELS: Record<string, string> = {
  supply_temp: 'Supply Temp',
  return_temp: 'Return Temp',
  fan_speed: 'Fan Speed',
  filter_dp: 'Filter ΔP',
  damper: 'Damper',
  zone_temp: 'Zone Temp',
  setpoint: 'Setpoint',
  airflow: 'Airflow',
  reheat: 'Reheat',
  voltage_r: 'Voltage R',
  voltage_s: 'Voltage S',
  voltage_t: 'Voltage T',
  current: 'Current',
  pf: 'Power Factor',
  kw: 'Power',
  total_kw: 'Total Power',
  kwh_today: 'Energy Today',
  max_demand: 'Max Demand',
  temp: 'Temperature',
  humidity: 'Humidity',
  co2: 'CO₂',
  lux: 'Illuminance',
  watts: 'Power',
  dim_level: 'Dim Level',
  luminaires: 'Luminaires',
  faults: 'Faults',
  occupancy: 'Occupancy',
  soc: 'State of Charge',
  power_kw: 'Power',
  voltage: 'Battery Voltage',
  cycles: 'Cycles',
  generation_kw: 'Generation',
  capacity_kwp: 'Capacity',
  today_kwh: 'Today',
  irradiance: 'Irradiance',
  inverter_temp: 'Inverter Temp',
  efficiency: 'Efficiency',
  chw_supply: 'CHW Supply',
  chw_return: 'CHW Return',
  load_pct: 'Load',
  cop: 'COP',
  runtime_hrs: 'Runtime',
  speed_hz: 'Speed',
  flow_lps: 'Flow',
  head_kpa: 'Head',
  vibration_mm: 'Vibration',
  cameras_online: 'Cameras Online',
  cameras_total: 'Total Cameras',
  storage_pct: 'Storage Used',
  recording: 'Recording',
  events_today: 'Events Today',
  door_state: 'Door State',
  last_access: 'Last Access',
  zones_ok: 'Zones OK',
  zones_total: 'Total Zones',
  last_test: 'Last Test',
  battery: 'Battery',
  battery_pct: 'Battery',
  input_v: 'Input V',
  output_v: 'Output V',
  runtime_min: 'Runtime',
};

const UNITS: Record<string, string> = {
  supply_temp: '°C',
  return_temp: '°C',
  fan_speed: '%',
  filter_dp: ' Pa',
  damper: '%',
  zone_temp: '°C',
  setpoint: '°C',
  airflow: '%',
  reheat: '%',
  voltage_r: ' V',
  voltage_s: ' V',
  voltage_t: ' V',
  current: ' A',
  kw: ' kW',
  total_kw: ' kW',
  kwh_today: ' kWh',
  max_demand: ' kW',
  temp: '°C',
  humidity: '%',
  co2: ' ppm',
  lux: ' lx',
  watts: ' W',
  dim_level: '%',
  soc: '%',
  power_kw: ' kW',
  voltage: ' V',
  generation_kw: ' kW',
  capacity_kwp: ' kWp',
  today_kwh: ' kWh',
  irradiance: ' W/m²',
  inverter_temp: '°C',
  efficiency: '%',
  chw_supply: '°C',
  chw_return: '°C',
  load_pct: '%',
  runtime_hrs: ' hrs',
  speed_hz: ' Hz',
  flow_lps: ' L/s',
  head_kpa: ' kPa',
  vibration_mm: ' mm/s',
  storage_pct: '%',
  battery: '%',
  battery_pct: '%',
  input_v: ' V',
  output_v: ' V',
  runtime_min: ' min',
};

export const DigitalTwinVisualization: React.FC<{ siteId?: string }> = ({ siteId = 'site-002' }) => {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [selectedEquipment, setSelectedEquipment] = useState<DetailedEquipment | null>(null);
  const [activeFloors, setActiveFloors] = useState<number[]>([0, 1, 2, 3, 4]);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'live' | 'alerts' | 'maintenance'>('live');

  // Fetch equipment data
  const { data: equipment } = useQuery({
    queryKey: ['equipment', siteId],
    queryFn: () => equipmentApi.getAllBySite(siteId),
  });

  // Fetch device readings
  const { data: devices } = useQuery({
    queryKey: ['devices', siteId],
    queryFn: () => devicesApi.getDevicesBySite(siteId),
  });

  // Initialize Three.js scene
  useEffect(() => {
    if (!canvasRef.current || typeof window === 'undefined' || !(window as any).THREE) {
      return;
    }

    const THREE = (window as any).THREE;
    const container = canvasRef.current;
    const W = container.clientWidth;
    const H = container.clientHeight;

    // Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x060e18);
    scene.fog = new THREE.FogExp2(0x060e18, 0.012);

    const camera = new THREE.PerspectiveCamera(50, W / H, 0.1, 200);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;

    container.appendChild(renderer.domElement);

    // Lighting
    scene.add(new THREE.AmbientLight(0x334455, 0.6));
    const dir = new THREE.DirectionalLight(0xffffff, 0.8);
    dir.position.set(10, 20, 10);
    dir.castShadow = true;
    scene.add(dir);
    scene.add(new THREE.PointLight(0x00ff41, 0.15, 60));
    scene.add(new THREE.GridHelper(50, 50, 0x0a1a0a, 0x061006));

    // Building parameters
    const FLOOR_H = 3.5;
    const FLOOR_W = 12;
    const FLOOR_D = 8;

    // Build floors
    const floorGroups: THREE.Group[] = [];
    const equipMeshes: THREE.Mesh[] = [];

    for (let f = 0; f < 5; f++) {
      const group = new THREE.Group();
      group.position.y = f * FLOOR_H;

      const slabGeo = new THREE.BoxGeometry(FLOOR_W, 0.12, FLOOR_D);
      const slab = new THREE.Mesh(slabGeo, new THREE.MeshPhongMaterial({
        color: 0x0f2640,
        transparent: true,
        opacity: 0.5,
      }));
      slab.receiveShadow = true;
      group.add(slab);

      group.add(new THREE.LineSegments(
        new THREE.EdgesGeometry(slabGeo),
        new THREE.LineBasicMaterial({ color: 0x00ff41, transparent: true, opacity: 0.2 })
      ));

      const wallH = FLOOR_H - 0.3;
      const wallEdge = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(FLOOR_W, wallH, FLOOR_D)),
        new THREE.LineBasicMaterial({ color: 0x0a3a0a, transparent: true, opacity: 0.15 })
      );
      wallEdge.position.y = wallH / 2 + 0.06;
      group.add(wallEdge);

      scene.add(group);
      floorGroups.push(group);
    }

    // Camera setup
    let sph = { theta: Math.PI / 4, phi: Math.PI / 3.5, radius: 32 };
    const lookY = (5 * FLOOR_H) / 2;

    const updateCam = () => {
      camera.position.x = sph.radius * Math.sin(sph.phi) * Math.sin(sph.theta);
      camera.position.y = sph.radius * Math.cos(sph.phi) + (lookY * 0.3);
      camera.position.z = sph.radius * Math.sin(sph.phi) * Math.cos(sph.theta);
      camera.lookAt(0, lookY, 0);
    };

    updateCam();

    // Mouse controls
    let isDragging = false;
    let prevMouse = { x: 0, y: 0 };

    renderer.domElement.addEventListener('mousedown', (e) => {
      isDragging = true;
      prevMouse = { x: e.clientX, y: e.clientY };
    });

    renderer.domElement.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      sph.theta -= (e.clientX - prevMouse.x) * 0.008;
      sph.phi = Math.max(0.25, Math.min(Math.PI / 2 - 0.05, sph.phi + (e.clientY - prevMouse.y) * 0.008));
      prevMouse = { x: e.clientX, y: e.clientY };
      updateCam();
    });

    renderer.domElement.addEventListener('mouseup', () => {
      isDragging = false;
    });

    renderer.domElement.addEventListener('mouseleave', () => {
      isDragging = false;
    });

    renderer.domElement.addEventListener('wheel', (e) => {
      sph.radius = Math.max(10, Math.min(60, sph.radius + e.deltaY * 0.03));
      updateCam();
    });

    // Animation loop
    let time = 0;
    const animate = () => {
      requestAnimationFrame(animate);
      time += 0.016;

      scene.traverse((o: any) => {
        if (o.userData?.pulse) {
          const s = 1 + Math.sin(time * 4) * 0.3;
          o.scale.set(s, s, s);
          o.material.opacity = 0.08 + Math.sin(time * 4) * 0.06;
        }
      });

      renderer.render(scene, camera);
    };

    animate();

    // Cleanup
    return () => {
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, [equipment, devices]);

  return (
    <div className="w-full space-y-6">
      <div className="text-center mb-8">
        <p className="font-mono text-xs tracking-widest text-emerald-400 mb-2 opacity-70">[ LIVE DEMO ]</p>
        <h2 className="font-display text-2xl font-bold text-slate-100">Interactive Digital Twin</h2>
      </div>

      <div
        ref={canvasRef}
        className="relative w-full h-[70vh] min-h-[500px] max-h-[700px] rounded border border-emerald-500/10 overflow-hidden bg-slate-950"
        style={{
          boxShadow: '0 0 60px rgba(0, 255, 65, 0.04), 0 20px 80px rgba(0, 0, 0, 0.5)',
        }}
      >
        <div className="absolute top-3 left-3 z-10 bg-slate-950/90 border border-emerald-500/10 rounded px-3 py-2 font-mono">
          <div className="text-xs font-semibold tracking-widest text-emerald-400 uppercase">Floors</div>
          <div className="mt-2 space-y-1 text-xs">
            {FLOOR_NAMES.map((name, i) => (
              <button
                key={i}
                className={`block w-full text-left px-2 py-1 rounded transition-all ${
                  activeFloors.includes(i)
                    ? 'bg-blue-600/20 text-blue-300 border border-blue-500/30'
                    : 'text-slate-400 hover:text-slate-300'
                }`}
                onClick={() => {
                  setActiveFloors(prev =>
                    prev.includes(i)
                      ? prev.filter(f => f !== i)
                      : [...prev, i]
                  );
                }}
              >
                {name}
              </button>
            ))}
          </div>
        </div>

        <div className="absolute bottom-3 left-3 right-3 font-mono text-xs text-slate-500">
          <span className="font-semibold text-slate-300">Drag</span> Rotate ·{' '}
          <span className="font-semibold text-slate-300">Scroll</span> Zoom ·{' '}
          <span className="font-semibold text-slate-300">Click</span> Inspect
        </div>

        {selectedEquipment && (
          <div className="absolute top-3 right-3 w-80 bg-slate-950/97 border border-emerald-500/10 rounded overflow-hidden z-20 max-h-[calc(100%-24px)] flex flex-col font-mono text-sm">
            <div className="px-4 py-3 border-b border-emerald-500/6">
              <div className="text-xs font-semibold tracking-wider text-emerald-400 uppercase opacity-70">
                {selectedEquipment.type}
              </div>
              <div className="font-display text-base font-bold text-slate-100 mt-1">
                {selectedEquipment.name}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {selectedEquipment.code} · {FLOOR_NAMES[selectedEquipment.floor]}
              </div>
              <div className="flex items-center gap-2 mt-2 text-xs px-2 py-1 rounded w-fit"
                style={{
                  background: `${STATUS_COLORS[selectedEquipment.status]}12`,
                  border: `1px solid ${STATUS_COLORS[selectedEquipment.status]}25`,
                }}>
                <div
                  className="w-1.5 h-1.5 rounded-full"
                  style={{
                    background: STATUS_COLORS[selectedEquipment.status],
                    boxShadow: `0 0 6px ${STATUS_COLORS[selectedEquipment.status]}`,
                  }}
                />
                <span style={{ color: STATUS_COLORS[selectedEquipment.status] }}>
                  {selectedEquipment.status.toUpperCase()}
                </span>
              </div>
            </div>

            <div className="flex border-b border-emerald-500/4">
              {(['live', 'alerts', 'maintenance'] as const).map(tab => (
                <button
                  key={tab}
                  className={`flex-1 px-3 py-2 text-xs uppercase tracking-wider font-semibold transition-all border-b-2 ${
                    activeTab === tab
                      ? 'text-blue-400 border-blue-500'
                      : 'text-slate-500 border-transparent hover:text-slate-400'
                  }`}
                  onClick={() => setActiveTab(tab)}
                >
                  {tab}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-auto px-4 py-3 space-y-2 text-xs">
              {activeTab === 'live' && selectedEquipment.readings && (
                <div className="space-y-2">
                  {Object.entries(selectedEquipment.readings).map(([k, v]) => {
                    const label = LABELS[k] || k;
                    const unit = UNITS[k] || '';
                    const display = typeof v === 'boolean' ? (v ? '●' : '○') : typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(1)) : v;
                    return (
                      <div key={k} className="flex justify-between">
                        <span className="text-slate-400">{label}</span>
                        <span className="text-slate-100 font-semibold">
                          {display}{unit}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {activeTab === 'alerts' && (
                <div className="space-y-2">
                  {selectedEquipment.alerts && selectedEquipment.alerts.length > 0 ? (
                    selectedEquipment.alerts.map(alert => (
                      <div
                        key={alert.id}
                        className="p-2 rounded text-xs"
                        style={{
                          background: alert.severity === 'critical' ? 'rgba(239, 68, 68, 0.08)' : alert.severity === 'warning' ? 'rgba(245, 158, 11, 0.08)' : 'rgba(46, 134, 171, 0.05)',
                          border: alert.severity === 'critical' ? '1px solid rgba(239, 68, 68, 0.2)' : alert.severity === 'warning' ? '1px solid rgba(245, 158, 11, 0.15)' : '1px solid rgba(46, 134, 171, 0.1)',
                        }}
                      >
                        <div className="flex justify-between mb-1">
                          <span className="font-semibold uppercase" style={{
                            color: alert.severity === 'critical' ? '#EF4444' : alert.severity === 'warning' ? '#F59E0B' : '#2E86AB'
                          }}>
                            {alert.severity}
                          </span>
                          <span className="text-slate-500">{alert.time}</span>
                        </div>
                        <p className="text-slate-300 leading-relaxed">{alert.text}</p>
                      </div>
                    ))
                  ) : (
                    <div className="text-center text-slate-500 py-4">✓ No active alerts</div>
                  )}
                </div>
              )}

              {activeTab === 'maintenance' && (
                <div className="space-y-2">
                  {selectedEquipment.maintenance ? (
                    <>
                      {Object.entries(selectedEquipment.maintenance).map(([k, v]) => (
                        <div key={k} className="flex justify-between">
                          <span className="text-slate-400">{k.replace(/_/g, ' ')}</span>
                          <span className="text-slate-100">{v}</span>
                        </div>
                      ))}
                      <button className="w-full mt-3 px-3 py-2 bg-emerald-500/10 border border-emerald-500/20 rounded text-emerald-400 hover:bg-emerald-500/20 transition-all text-xs font-semibold">
                        📋 Raise Work Order
                      </button>
                    </>
                  ) : (
                    <div className="text-center text-slate-500 py-4">No maintenance records</div>
                  )}
                </div>
              )}
            </div>

            <button
              className="absolute top-3 right-3 text-slate-500 hover:text-slate-300 text-lg"
              onClick={() => setSelectedEquipment(null)}
            >
              ✕
            </button>
          </div>
        )}
      </div>

      <div className="text-center text-xs text-slate-500 font-mono">
        Equipment visualization powered by Three.js | Real-time data from SENTINEL BMS
      </div>
    </div>
  );
};

export default DigitalTwinVisualization;
