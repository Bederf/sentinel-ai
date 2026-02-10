"""Step 5: Building Structure Definition Component."""

import { Plus } from "lucide-react";
import React, { useEffect, useState } from "react";
import { FloorInput, type FloorDef } from "./FloorInput";

export interface BuildingStructure {
  name: string;
  code?: string;
  numberOfFloors: number;
  floors: FloorDef[];
}

export interface BuildingStructureStepProps {
  initialData?: BuildingStructure;
  onNext: (data: BuildingStructure) => void;
  onBack: () => void;
}

const AVAILABLE_LEVELS = [
  "B2",
  "B1",
  "G",
  "L1",
  "L2",
  "L3",
  "L4",
  "L5",
  "L10",
  "L11",
  "L12",
  "M",
  "R",
  "PH",
];

/**Step 5: Define building structure (floors and dimensions)."""
export function BuildingStructureStep({
  initialData,
  onNext,
  onBack,
}: BuildingStructureStepProps) {
  const [name, setName] = useState(initialData?.name || "");
  const [code, setCode] = useState(initialData?.code || "");
  const [numberOfFloors, setNumberOfFloors] = useState(
    initialData?.numberOfFloors || 1
  );
  const [floors, setFloors] = useState<FloorDef[]>(
    initialData?.floors || [
      {
        level: "G",
        height: 4.0,
        width: 50,
        depth: 40,
        label: "Ground Floor",
      },
    ]
  );
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Sync floor count with numberOfFloors
  useEffect(() => {
    const currentCount = floors.length;
    if (numberOfFloors > currentCount) {
      // Add floors
      const newFloors = [...floors];
      for (let i = currentCount; i < numberOfFloors; i++) {
        newFloors.push({
          level: AVAILABLE_LEVELS[i % AVAILABLE_LEVELS.length],
          height: 4.0,
          width: 50,
          depth: 40,
          label: `Floor ${i + 1}`,
        });
      }
      setFloors(newFloors);
    } else if (numberOfFloors < currentCount) {
      // Remove floors
      setFloors(floors.slice(0, numberOfFloors));
    }
  }, [numberOfFloors]);

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = "Building name required";
    }

    if (numberOfFloors < 1 || numberOfFloors > 50) {
      newErrors.numberOfFloors = "Floors must be 1-50";
    }

    const usedLevels = new Set<string>();
    floors.forEach((floor, idx) => {
      if (!floor.level) {
        newErrors[`floor_${idx}_level`] = "Level required";
      } else if (usedLevels.has(floor.level)) {
        newErrors[`floor_${idx}_level`] = "Duplicate level";
      } else {
        usedLevels.add(floor.level);
      }

      if (floor.height < 2 || floor.height > 20) {
        newErrors[`floor_${idx}_height`] = "Height 2-20m";
      }
      if (floor.width < 5 || floor.width > 1000) {
        newErrors[`floor_${idx}_width`] = "Width 5-1000m";
      }
      if (floor.depth < 5 || floor.depth > 1000) {
        newErrors[`floor_${idx}_depth`] = "Depth 5-1000m";
      }
    });

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = () => {
    if (validateForm()) {
      onNext({
        name,
        code: code || undefined,
        numberOfFloors,
        floors,
      });
    }
  };

  const handleUpdateFloor = (index: number, updatedFloor: FloorDef) => {
    const newFloors = [...floors];
    newFloors[index] = updatedFloor;
    setFloors(newFloors);
  };

  const handleRemoveFloor = (index: number) => {
    if (floors.length > 1) {
      setFloors(floors.filter((_, i) => i !== index));
      setNumberOfFloors(Math.max(1, numberOfFloors - 1));
    }
  };

  const totalArea = floors.reduce(
    (sum, f) => sum + f.width * f.depth,
    0
  );
  const availableLevels = AVAILABLE_LEVELS.filter(
    (l) => !floors.some((f) => f.level === l)
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-blue-50 border-l-4 border-blue-400 p-4 rounded">
        <p className="text-sm text-blue-700">
          <strong>Step 5:</strong> Define the building structure. Enter the
          number of floors and dimensions for each level. These will be used for
          3D visualization and equipment placement.
        </p>
      </div>

      {/* Building Info */}
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Building Name *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., Sandton City Office Tower"
            className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              errors.name
                ? "border-red-300 bg-red-50"
                : "border-gray-300 bg-white"
            }`}
          />
          {errors.name && (
            <p className="text-red-600 text-xs mt-1">{errors.name}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Building Code (Optional)
          </label>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="e.g., SANDTON-001"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Number of Floors *
          </label>
          <div className="flex items-center gap-3">
            <input
              type="number"
              value={numberOfFloors}
              onChange={(e) =>
                setNumberOfFloors(Math.min(50, Math.max(1, Number(e.target.value))))
              }
              min="1"
              max="50"
              className={`w-20 px-3 py-2 border rounded-lg text-center font-semibold focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.numberOfFloors
                  ? "border-red-300 bg-red-50"
                  : "border-gray-300 bg-white"
              }`}
            />
            <div className="text-sm text-gray-600">
              Total area: <strong>{totalArea.toFixed(0)}</strong> m²
            </div>
          </div>
          {errors.numberOfFloors && (
            <p className="text-red-600 text-xs mt-1">{errors.numberOfFloors}</p>
          )}
        </div>
      </div>

      {/* Floors */}
      <div className="space-y-4">
        <h3 className="font-semibold text-gray-900">Floor Definitions</h3>

        {floors.map((floor, idx) => (
          <FloorInput
            key={idx}
            floor={floor}
            floorIndex={idx}
            availableLevels={[floor.level, ...availableLevels]}
            onUpdate={(updated) => handleUpdateFloor(idx, updated)}
            onRemove={
              floors.length > 1 ? () => handleRemoveFloor(idx) : undefined
            }
            showRemoveButton={floors.length > 1}
          />
        ))}

        {floors.length < 50 && (
          <button
            onClick={() => {
              const nextLevel =
                availableLevels[0] || `L${floors.length + 1}`;
              setFloors([
                ...floors,
                {
                  level: nextLevel,
                  height: 4.0,
                  width: 50,
                  depth: 40,
                  label: `Floor ${floors.length + 1}`,
                },
              ]);
              setNumberOfFloors(numberOfFloors + 1);
            }}
            className="w-full py-3 border-2 border-dashed border-gray-300 rounded-lg text-gray-700 hover:border-blue-400 hover:bg-blue-50 transition-colors font-medium flex items-center justify-center gap-2"
          >
            <Plus className="h-5 w-5" />
            Add Floor
          </button>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-3 pt-4">
        <button
          onClick={onBack}
          className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition-colors"
        >
          Back
        </button>
        <button
          onClick={handleNext}
          className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          disabled={!name.trim() || Object.keys(errors).length > 0}
        >
          Place Equipment →
        </button>
      </div>
    </div>
  );
}
