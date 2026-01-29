// ColumnMappingStep.tsx - Placeholder for Task 2
export function ColumnMappingStep({ formatDetection, onNext, onBack }: {
  buildingId: string;
  formatDetection: any;
  onNext: (data: any) => void;
  onBack: () => void;
}) {
  return (
    <div className="p-6 text-center text-gray-500">
      <p>Column Mapping Step - To be implemented in Task 2</p>
      <button
        onClick={() => onNext({ columnMappings: {} })}
        className="mt-4 px-4 py-2 bg-blue-500 text-white rounded"
      >
        Skip (for now)
      </button>
    </div>
  );
}
