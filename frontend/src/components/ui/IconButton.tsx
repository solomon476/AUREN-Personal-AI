import React from 'react';

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon: React.ReactNode;
  label: string;
  variant?: 'primary' | 'secondary' | 'ghost' | 'destructive';
  size?: 'xs' | 'sm' | 'md';
}

const variantStyles = {
  primary:
    'bg-[#d7ba83] hover:bg-[#e6d4b0] text-[#07080c] shadow-sm hover:shadow-[0_0_16px_rgba(215,186,131,0.25)] border border-[#e6d4b0]/40',
  secondary:
    'bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 hover:text-white border border-white/[0.08] hover:border-white/[0.14] shadow-sm',
  ghost:
    'bg-transparent hover:bg-white/[0.05] text-slate-400 hover:text-white border border-transparent',
  destructive:
    'bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 hover:text-rose-100 border border-rose-800/40 hover:border-rose-700/60',
};

const sizeStyles = {
  xs: 'p-1.5 rounded-lg touch-target sm:min-w-0 sm:min-h-0',
  sm: 'p-2 rounded-xl touch-target',
  md: 'p-2.5 rounded-xl touch-target',
};

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    {
      icon,
      label,
      variant = 'secondary',
      size = 'sm',
      disabled,
      className = '',
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        aria-label={label}
        title={label}
        disabled={disabled}
        className={`inline-flex items-center justify-center transition-all duration-150 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-champagne-400/50 disabled:opacity-40 disabled:cursor-not-allowed ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
        {...props}
      >
        {icon}
      </button>
    );
  }
);

IconButton.displayName = 'IconButton';

