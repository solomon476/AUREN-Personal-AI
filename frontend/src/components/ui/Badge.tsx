import React from 'react';

export type BadgeVariant = 'champagne' | 'neutral' | 'success' | 'warning' | 'error' | 'info';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: 'xs' | 'sm';
  dot?: boolean;
  fontMono?: boolean;
}

const variantStyles: Record<BadgeVariant, { bg: string; dotColor: string }> = {
  champagne: {
    bg: 'bg-champagne-500/10 text-champagne-300 border-champagne-500/30',
    dotColor: 'bg-champagne-400 shadow-[0_0_8px_rgba(215,186,131,0.5)]',
  },
  neutral: {
    bg: 'bg-white/[0.04] text-slate-300 border-white/[0.08]',
    dotColor: 'bg-slate-400',
  },
  success: {
    bg: 'bg-emerald-950/60 text-emerald-300 border-emerald-800/40',
    dotColor: 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]',
  },
  warning: {
    bg: 'bg-amber-950/60 text-amber-300 border-amber-800/40',
    dotColor: 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.5)]',
  },
  error: {
    bg: 'bg-rose-950/60 text-rose-300 border-rose-800/40',
    dotColor: 'bg-rose-400 shadow-[0_0_8px_rgba(244,63,94,0.5)]',
  },
  info: {
    bg: 'bg-sky-950/60 text-sky-300 border-sky-800/40',
    dotColor: 'bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.5)]',
  },
};

export const Badge: React.FC<BadgeProps> = ({
  variant = 'neutral',
  size = 'xs',
  dot = false,
  fontMono = false,
  className = '',
  children,
  ...props
}) => {
  const { bg, dotColor } = variantStyles[variant];
  const sizeStyle = size === 'xs' ? 'text-[10px] px-2 py-0.5' : 'text-xs px-2.5 py-1';

  return (
    <span
      className={`inline-flex items-center space-x-1.5 rounded-lg border font-medium select-none ${
        fontMono ? 'font-mono' : ''
      } ${bg} ${sizeStyle} ${className}`}
      {...props}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor}`} />}
      <span>{children}</span>
    </span>
  );
};
