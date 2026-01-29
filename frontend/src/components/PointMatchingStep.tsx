// PointMatchingStep.tsx - Placeholder for Task 2
export function PointMatchingStep({ columnMappings: _columnMappings, onNext, onBack: _onBack }: {
  buildingId: string;
  columnMappings: any;
  onNext: (data: any) => void;
  onBack: () => void;
}) {
  return (
    <div className="p-6 text-center text-gray-500">
      <p>Point Matching Step - To be implemented in Task 2</p>
      <button
        onClick={() => onNext({ pointMatches: [] })}
        className="mt-4 px-4 py-2 bg-blue-500 text-white rounded"
      >
        Skip (for now)
      </button>
    </div>
  );
}
