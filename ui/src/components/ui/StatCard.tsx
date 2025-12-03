import React from 'react';
import { motion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  trend?: string;
  trendUp?: boolean;
  color?: 'blue' | 'purple' | 'green' | 'yellow' | 'red';
  className?: string;
  delay?: number;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  icon: Icon,
  trend,
  trendUp,
  color = 'blue',
  className = '',
  delay = 0
}) => {
  const colorMap = {
    blue: 'text-neon-blue border-neon-blue/20 bg-neon-blue/5',
    purple: 'text-neon-purple border-neon-purple/20 bg-neon-purple/5',
    green: 'text-neon-green border-neon-green/20 bg-neon-green/5',
    yellow: 'text-neon-yellow border-neon-yellow/20 bg-neon-yellow/5',
    red: 'text-neon-red border-neon-red/20 bg-neon-red/5',
  };

  const iconColorMap = {
    blue: 'text-neon-blue',
    purple: 'text-neon-purple',
    green: 'text-neon-green',
    yellow: 'text-neon-yellow',
    red: 'text-neon-red',
  };

  const bgMap = {
    blue: 'bg-blue-500',
    purple: 'bg-purple-500',
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay }}
      className={`glass-card rounded-xl p-6 relative overflow-hidden group ${className}`}
    >
      {/* Background Gradient Blob */}
      <div className={`absolute -right-6 -top-6 w-24 h-24 rounded-full blur-3xl opacity-20 group-hover:opacity-40 transition-opacity duration-500 ${bgMap[color]}`} />
      
      <div className="flex items-start justify-between relative z-10">
        <div>
          <p className="text-gray-400 text-sm font-medium mb-1 tracking-wide uppercase">{title}</p>
          <h3 className="text-3xl font-bold font-display text-white tracking-tight group-hover:scale-105 transition-transform duration-300 origin-left">
            {value}
          </h3>
        </div>
        <div className={`p-3 rounded-lg ${colorMap[color]} backdrop-blur-md shadow-lg group-hover:rotate-12 transition-transform duration-300`}>
          <Icon className={`w-6 h-6 ${iconColorMap[color]}`} />
        </div>
      </div>
      
      {trend && (
        <div className="mt-4 flex items-center gap-2 text-sm relative z-10">
          <span className={`${trendUp ? 'text-neon-green' : 'text-neon-red'} font-medium flex items-center gap-1`}>
            {trendUp ? '↑' : '↓'} {trend}
          </span>
          <span className="text-gray-500">vs last hour</span>
        </div>
      )}
    </motion.div>
  );
};
