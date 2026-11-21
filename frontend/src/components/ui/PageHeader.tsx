import React from 'react';

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  tag?: string;
  actions?: React.ReactNode;
  className?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  icon,
  tag,
  actions,
  className = '',
}) => {
  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-center justify-between pb-4 sm:pb-6 border-b border-white/[0.06] gap-3 sm:gap-4 ${className}`}
    >
      <div className="space-y-1">
        <div className="flex items-center space-x-2.5">
          {icon && (
            <div className="p-2 rounded-xl bg-champagne-500/10 border border-champagne-500/20 text-champagne-300 flex-shrink-0 shadow-sm">
              {icon}
            </div>
          )}
          <div className="flex items-center space-x-2">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
              {title}
            </h1>
            {tag && (
              <span className="hidden sm:inline-flex text-[10px] font-mono px-2 py-0.5 rounded bg-white/[0.04] text-champagne-300 border border-champagne-500/20">
                {tag}
              </span>
            )}
          </div>
        </div>
        {subtitle && (
          <p className="text-xs text-slate-400 leading-relaxed max-w-2xl sm:pl-0.5">
            {subtitle}
          </p>
        )}
      </div>

      {actions && (
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap pt-1 sm:pt-0">
          {actions}
        </div>
      )}
    </div>
  );
};

