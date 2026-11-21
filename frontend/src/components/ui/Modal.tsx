import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { IconButton } from './IconButton';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  showCloseButton?: boolean;
}

const maxWidthMap = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
};

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  maxWidth = 'md',
  showCloseButton = true,
}) => {
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-[#040508]/80 backdrop-blur-md transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Dialog Surface */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        className={`relative w-full ${maxWidthMap[maxWidth]} rounded-2xl bg-[#0d0f17] border border-white/[0.09] shadow-modal-elevation overflow-hidden z-10 flex flex-col max-h-[90vh]`}
      >
        {/* Modal Header */}
        {(title || showCloseButton) && (
          <div className="flex items-center justify-between p-4 sm:p-5 border-b border-white/[0.06] flex-shrink-0">
            <div>
              {typeof title === 'string' ? (
                <h2 className="text-sm sm:text-base font-semibold text-white tracking-tight">
                  {title}
                </h2>
              ) : (
                title
              )}
              {subtitle && (
                <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{subtitle}</p>
              )}
            </div>
            {showCloseButton && (
              <IconButton
                icon={<X className="w-4 h-4" />}
                label="Close dialog"
                variant="ghost"
                size="sm"
                onClick={onClose}
              />
            )}
          </div>
        )}

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 scrollbar-thin">
          {children}
        </div>
      </div>
    </div>
  );
};

