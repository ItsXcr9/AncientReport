import React from 'react';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'success' | 'warning' | 'error' | 'info' | 'neutral';
  className?: string;
  pulse?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({ 
  children, 
  variant = 'neutral', 
  className = '',
  pulse = false 
}) => {
  const variants = {
    success: 'bg-green-500/10 text-neon-green border-green-500/20 shadow-[0_0_10px_rgba(10,255,104,0.2)]',
    warning: 'bg-yellow-500/10 text-neon-yellow border-yellow-500/20 shadow-[0_0_10px_rgba(255,215,0,0.2)]',
    error: 'bg-red-500/10 text-neon-red border-red-500/20 shadow-[0_0_10px_rgba(255,0,85,0.2)]',
    info: 'bg-blue-500/10 text-neon-blue border-blue-500/20 shadow-[0_0_10px_rgba(0,243,255,0.2)]',
    neutral: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
  };

  return (
    <span className={`
      inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border backdrop-blur-sm
      ${variants[variant]}
      ${pulse ? 'animate-pulse-glow' : ''}
      ${className}
    `}>
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
            variant === 'success' ? 'bg-green-400' :
            variant === 'warning' ? 'bg-yellow-400' :
            variant === 'error' ? 'bg-red-400' :
            variant === 'info' ? 'bg-blue-400' : 'bg-gray-400'
          }`}></span>
          <span className={`relative inline-flex rounded-full h-2 w-2 ${
            variant === 'success' ? 'bg-green-500' :
            variant === 'warning' ? 'bg-yellow-500' :
            variant === 'error' ? 'bg-red-500' :
            variant === 'info' ? 'bg-blue-500' : 'bg-gray-500'
          }`}></span>
        </span>
      )}
      {children}
    </span>
  );
};
