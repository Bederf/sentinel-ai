import { Card } from '@tremor/react';

interface LoadingCardProps {
  height?: string;
}

export function LoadingCard({ height = "h-24" }: LoadingCardProps) {
  return (
    <Card className={`${height} animate-pulse`}>
      <div className="space-y-3">
        <div className="h-4 bg-gray-200 rounded w-3/4"></div>
        <div className="h-3 bg-gray-200 rounded w-1/2"></div>
      </div>
    </Card>
  );
}
