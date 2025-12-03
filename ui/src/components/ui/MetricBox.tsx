import React from 'react';
import { motion } from 'framer-motion';

interface MetricBoxProps {
  label: string;
  value: string;
  trend?: string;
  className?: string;
}

export const MetricBox: React.FC<MetricBoxProps> = ({ label, value, trend, className = '' }) => (
  <motion.div 
    whileHover={{ scale: 1.02 }}
    className={`glass-card p-4 rounded-lg border border-white/5 bg-white/5 hover:bg-white/10 transition-all duration-300 ${className}`}
  >
    <div className="text-gray-400 text-xs uppercase tracking-wider mb-1 font-medium">{label}</div>
    <div className="text-xl font-bold font-display text-white tracking-tight">{value}</div>
    {trend && <div className="text-xs text-gray-500 mt-1 font-mono">{trend}</div>}
  </motion.div>
);
