import React from 'react';

export interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className = '',
}) => {
  return (
    <div
      className={`rounded-2xl bg-white/[0.015] border border-white/[0.05] p-8 sm:p-12 text-center max-w-md mx-auto my-6 space-y-3.5 shadow-sm ${className}`}
    >
      <div className="w-12 h-12 rounded-2xl bg-white/[0.03] border border-white/[0.08] text-slate-400 flex items-center justify-center mx-auto shadow-inner">
        {icon}
      </div>
      <div className="space-y-1">
        <h3 className="text-sm font-semibold text-slate-200 tracking-tight">{title}</h3>
        <p className="text-xs text-slate-400 leading-relaxed max-w-sm mx-auto">
          {description}
        </p>
      </div>
      {action && <div className="pt-2">{action}</div>}
    </div>
  );
};
