import React from 'react';
import { Loader2 } from 'lucide-react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive' | 'outline';
export type ButtonSize = 'xs' | 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  fullWidth?: boolean;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    'bg-[#d7ba83] hover:bg-[#e6d4b0] text-[#07080c] font-semibold shadow-sm hover:shadow-[0_0_16px_rgba(215,186,131,0.25)] border border-[#e6d4b0]/40 active:scale-[0.98]',
  secondary:
    'bg-white/[0.04] hover:bg-white/[0.08] text-slate-200 hover:text-white border border-white/[0.08] hover:border-white/[0.14] shadow-sm active:scale-[0.98]',
  ghost:
    'bg-transparent hover:bg-white/[0.05] text-slate-300 hover:text-white border border-transparent',
  destructive:
    'bg-rose-950/60 hover:bg-rose-900/70 text-rose-300 hover:text-rose-100 border border-rose-800/50 hover:border-rose-700/60 shadow-sm active:scale-[0.98]',
  outline:
    'bg-transparent hover:bg-[#d7ba83]/10 text-champagne-300 hover:text-champagne-200 border border-champagne-500/40 hover:border-champagne-400 active:scale-[0.98]',
};

const sizeStyles: Record<ButtonSize, string> = {
  xs: 'text-[11px] px-2.5 py-1 rounded-lg gap-1.5 min-h-[30px]',
  sm: 'text-xs px-3.5 py-1.5 rounded-xl gap-2 min-h-[36px]',
  md: 'text-xs sm:text-sm px-4 py-2 rounded-xl gap-2 min-h-[42px]',
  lg: 'text-sm px-5 py-2.5 rounded-xl gap-2.5 min-h-[48px]',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'secondary',
      size = 'sm',
      isLoading = false,
      leftIcon,
      rightIcon,
      fullWidth = false,
      disabled,
      className = '',
      children,
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={`inline-flex items-center justify-center font-medium transition-all duration-150 select-none cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-champagne-400/50 disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none ${
          variantStyles[variant]
        } ${sizeStyles[size]} ${fullWidth ? 'w-full' : ''} ${className}`}
        {...props}
      >
        {isLoading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-current" />
        ) : (
          leftIcon && <span className="flex-shrink-0 flex items-center">{leftIcon}</span>
        )}
        <span>{children}</span>
        {!isLoading && rightIcon && (
          <span className="flex-shrink-0 flex items-center">{rightIcon}</span>
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';
