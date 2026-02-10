"""Floor definition input component."""

import { Trash2 } from "lucide-react";
import React, { useState } from "react";

export interface FloorDef {
  level: string;
  height: number;
  width: number;
  depth: number;
  label: string;
}

export interface FloorInputProps {
  floor: FloorDef;
  availableLevels: string[];
  onUpdate: (updatedFloor: FloorDef) => void;
  onRemove?: () => void;
  showRemoveButton?: boolean;
  floorIndex: number;
}

/**Form inputs for a single floor definition."""
export function FloorInput({
  floor,
  availableLevels,
  onUpdate,
  onRemove,
  showRemoveButton = false,
  floorIndex,
}: FloorInputProps) {
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validateField = (field: string, value: any) => {
    const newErrors = { ...errors };

    if (field === "level") {
      if (!value) {
        newErrors["level"] = "Floor level required";
      } else {
        delete newErrors["level"];
      }
    }

    if (field === "height") {
      const num = Number(value);
      if (isNaN(num) || num < 2 || num > 20) {
        newErrors["height"] = "Height must be 2-20 meters";
      } else {
        delete newErrors["height"];
      }
    }

    if (field === "width") {
      const num = Number(value);
      if (isNaN(num) || num < 5 || num > 1000) {
        newErrors["width"] = "Width must be 5-1000 meters";
      } else {
        delete newErrors["width"];
      }
    }

    if (field === "depth") {
      const num = Number(value);
      if (isNaN(num) || num < 5 || num > 1000) {
        newErrors["depth"] = "Depth must be 5-1000 meters";
      } else {
        delete newErrors["depth"];
      }
    }

    if (field === "label") {
      if (!value || value.trim() === "") {
        newErrors["label"] = "Label required";
      } else {
        delete newErrors["label"];
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleChange = (field: string, value: any) => {
    validateField(field, value);

    const updated = { ...floor };
    if (field === "height" || field === "width" || field === "depth") {
      updated[field] = Number(value) || 0;
    } else {
      updated[field] = value;
    }
    onUpdate(updated);
  };

  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
      <div className="flex items-center justify-between mb-4">
        <h4 className="font-medium text-gray-900">Floor {floorIndex + 1}</h4>
        {showRemoveButton && onRemove && (
          <button
            onClick={onRemove}
            className="p-2 text-red-600 hover:bg-red-50 rounded transition-colors"
            title="Remove floor"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="space-y-4">
        {/* Level selector */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Level *
          </label>
          <select
            value={floor.level}
            onChange={(e) => handleChange("level", e.target.value)}
            className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              errors.level
                ? "border-red-300 bg-red-50"
                : "border-gray-300 bg-white"
            }`}
          >
            <option value="">Select level...</option>
            {availableLevels.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
          {errors.level && (
            <p className="text-red-600 text-xs mt-1">{errors.level}</p>
          )}
        </div>

        {/* Dimensions grid */}
        <div className="grid grid-cols-3 gap-3">
          {/* Height */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Height (m) *
            </label>
            <input
              type="number"
              value={floor.height || ""}
              onChange={(e) => handleChange("height", e.target.value)}
              placeholder="4.0"
              min="2"
              max="20"
              step="0.5"
              className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.height
                  ? "border-red-300 bg-red-50"
                  : "border-gray-300 bg-white"
              }`}
            />
            {errors.height && (
              <p className="text-red-600 text-xs mt-1">{errors.height}</p>
            )}
          </div>

          {/* Width */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Width (m) *
            </label>
            <input
              type="number"
              value={floor.width || ""}
              onChange={(e) => handleChange("width", e.target.value)}
              placeholder="50"
              min="5"
              max="1000"
              step="1"
              className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.width
                  ? "border-red-300 bg-red-50"
                  : "border-gray-300 bg-white"
              }`}
            />
            {errors.width && (
              <p className="text-red-600 text-xs mt-1">{errors.width}</p>
            )}
          </div>

          {/* Depth */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Depth (m) *
            </label>
            <input
              type="number"
              value={floor.depth || ""}
              onChange={(e) => handleChange("depth", e.target.value)}
              placeholder="40"
              min="5"
              max="1000"
              step="1"
              className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.depth
                  ? "border-red-300 bg-red-50"
                  : "border-gray-300 bg-white"
              }`}
            />
            {errors.depth && (
              <p className="text-red-600 text-xs mt-1">{errors.depth}</p>
            )}
          </div>
        </div>

        {/* Label */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Label / Purpose *
          </label>
          <input
            type="text"
            value={floor.label}
            onChange={(e) => handleChange("label", e.target.value)}
            placeholder="e.g., Ground Floor - Open Plan"
            className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              errors.label
                ? "border-red-300 bg-red-50"
                : "border-gray-300 bg-white"
            }`}
          />
          {errors.label && (
            <p className="text-red-600 text-xs mt-1">{errors.label}</p>
          )}
        </div>

        {/* Helpful text */}
        <div className="text-xs text-gray-500 bg-blue-50 p-2 rounded border border-blue-100">
          💡 Typical office floor: 4m height, 50m width, 40m depth
        </div>
      </div>
    </div>
  );
}
