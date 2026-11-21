import React from 'react';

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  variant = 'rectangular',
  width,
  height,
  className = '',
  style,
  ...props
}) => {
  const variantClass =
    variant === 'circular'
      ? 'rounded-full'
      : variant === 'text'
      ? 'rounded-md h-3.5'
      : 'rounded-xl';

  return (
    <div
      className={`bg-white/[0.05] animate-pulse border border-white/[0.03] ${variantClass} ${className}`}
      style={{
        width,
        height,
        ...style,
      }}
      {...props}
    />
  );
};

