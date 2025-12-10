
import { useOutletContext } from 'react-router-dom';
import { Activity, Brain, Database, Loader2, Zap, Clock } from 'lucide-react';
import { AIChat } from '../components/AIChat';

interface AnalysisProps {
    report: any;
    triggerAnalysis: () => void;
    isTriggering: boolean;
    cooldownRemaining: number;
    formatCooldownTime: (ms: number) => string;
}

export default function Analysis() {
    const { report, triggerAnalysis, isTriggering, cooldownRemaining, formatCooldownTime } = useOutletContext<AnalysisProps>();

  return (
    <div className="space-y-8 relative pb-20"> {/* pb-20 for AI Chat input space if needed */}
      <div className="flex items-center justify-between">
        <div>
            <h1 className="text-2xl font-bold text-white font-display tracking-tight mb-2">Deep Analysis</h1>
            <p className="text-gray-400 text-sm">AI-driven insights and Process Breakdown</p>
        </div>
        
        <button
            onClick={triggerAnalysis}
            disabled={cooldownRemaining > 0 || isTriggering}
            className={`
                px-4 py-2 rounded-lg font-medium text-sm transition-all duration-300 flex items-center gap-2
                ${cooldownRemaining > 0 || isTriggering
                ? 'bg-white/5 text-gray-500 cursor-not-allowed'
                : 'bg-neon-blue/10 text-neon-blue hover:bg-neon-blue/20 hover:shadow-[0_0_15px_rgba(0,243,255,0.3)] border border-neon-blue/20'}
            `}
        >
            {isTriggering ? (
                <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Analyzing...</span>
                </>
            ) : cooldownRemaining > 0 ? (
                <>
                <Clock className="w-4 h-4" />
                <span>{formatCooldownTime(cooldownRemaining)}</span>
                </>
            ) : (
                <>
                <Zap className="w-4 h-4" />
                <span>Trigger Analysis</span>
                </>
            )}
        </button>
      </div>

       {/* Analysis & Insights Section Logic (from App.tsx) */}
       {report ? (
        <div className="w-full mb-8">
            <section className="w-full glass-card-intense rounded-xl p-6 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-neon-blue via-neon-purple to-neon-blue opacity-50" />
            
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold font-display flex items-center gap-2 text-white">
                <Brain className="w-6 h-6 text-neon-purple" />
                Latest Report Analysis
                </h2>
            </div>

            <div className="mt-4 space-y-3">
                <h4 className="font-semibold text-base mb-3 flex items-center gap-2">
                <Activity className="w-4 h-4 text-blue-400" />
                Top Processes (Hourly Summary)
                </h4>
                {report.top_processes ? (
                <>
                    {report.top_processes.cpu && Array.isArray(report.top_processes.cpu) && report.top_processes.cpu.length > 0 && (
                    <div className="p-4 bg-gradient-to-r from-blue-500/10 to-blue-600/5 rounded-lg border border-blue-500/20">
                    <h5 className="text-sm font-medium text-blue-400 mb-3 flex items-center gap-2">
                        <Activity className="w-4 h-4" />
                        Top 3 CPU Consumers
                    </h5>
                    <div className="space-y-2">
                        {report.top_processes.cpu.map((proc: any, i: number) => (
                        <div key={i} className="p-2 bg-white/5 rounded border border-white/10">
                            <div className="flex items-center justify-between mb-1">
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-bold text-blue-400 w-6">#{i + 1}</span>
                                <span className="text-sm font-medium text-gray-200">{proc?.name || 'unknown'}</span>
                                <span className="text-xs text-gray-500">(PID: {proc?.pid || 'N/A'})</span>
                            </div>
                            <div className="text-right">
                                <span className="text-sm font-semibold text-blue-300">{(proc?.average || 0).toFixed(1)}%</span>
                                <span className="text-xs text-gray-500 ml-2">peak: {(proc?.peak || 0).toFixed(1)}%</span>
                            </div>
                            </div>
                            {proc?.command_line && (
                            <div className="ml-8 mt-1">
                                <span className="text-xs text-gray-400 font-mono break-all">{proc.command_line}</span>
                            </div>
                            )}
                        </div>
                        ))}
                    </div>
                    </div>
                )}
                
                {report.top_processes.memory && Array.isArray(report.top_processes.memory) && report.top_processes.memory.length > 0 && (
                    <div className="p-4 bg-gradient-to-r from-purple-500/10 to-purple-600/5 rounded-lg border border-purple-500/20">
                    <h5 className="text-sm font-medium text-purple-400 mb-3 flex items-center gap-2">
                        <Database className="w-4 h-4" />
                        Top 3 Memory Consumers
                    </h5>
                    <div className="space-y-2">
                        {report.top_processes.memory.map((proc: any, i: number) => (
                        <div key={i} className="p-2 bg-white/5 rounded border border-white/10">
                            <div className="flex items-center justify-between mb-1">
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-bold text-purple-400 w-6">#{i + 1}</span>
                                <span className="text-sm font-medium text-gray-200">{proc?.name || 'unknown'}</span>
                                <span className="text-xs text-gray-500">(PID: {proc?.pid || 'N/A'})</span>
                            </div>
                            <div className="text-right">
                                <span className="text-sm font-semibold text-purple-300">{(proc?.average || 0).toFixed(1)} MB</span>
                                <span className="text-xs text-gray-500 ml-2">peak: {(proc?.peak || 0).toFixed(1)} MB</span>
                            </div>
                            </div>
                            {proc?.command_line && (
                            <div className="ml-8 mt-1">
                                <span className="text-xs text-gray-400 font-mono break-all">{proc.command_line}</span>
                            </div>
                            )}
                        </div>
                        ))}
                    </div>
                    </div>
                )}
                
                {report.top_processes.disk_io && Array.isArray(report.top_processes.disk_io) && report.top_processes.disk_io.length > 0 && (
                    <div className="p-4 bg-gradient-to-r from-green-500/10 to-green-600/5 rounded-lg border border-green-500/20">
                    <h5 className="text-sm font-medium text-green-400 mb-3 flex items-center gap-2">
                        <Activity className="w-4 h-4" />
                        Top 3 Disk I/O Consumers
                    </h5>
                    <div className="space-y-2">
                        {report.top_processes.disk_io.map((proc: any, i: number) => (
                        <div key={i} className="p-2 bg-white/5 rounded border border-white/10">
                            <div className="flex items-center justify-between mb-1">
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-bold text-green-400 w-6">#{i + 1}</span>
                                <span className="text-sm font-medium text-gray-200">{proc?.name || 'unknown'}</span>
                                <span className="text-xs text-gray-500">(PID: {proc?.pid || 'N/A'})</span>
                            </div>
                            <div className="text-right">
                                <span className="text-sm font-semibold text-green-300">{(proc?.average || 0).toFixed(1)} MB</span>
                                <span className="text-xs text-gray-500 ml-2">peak: {(proc?.peak || 0).toFixed(1)} MB</span>
                            </div>
                            </div>
                            {proc?.command_line && (
                            <div className="ml-8 mt-1">
                                <span className="text-xs text-gray-400 font-mono break-all">{proc.command_line}</span>
                            </div>
                            )}
                        </div>
                        ))}
                    </div>
                    </div>
                )}

                
                {(!report.top_processes.cpu || !Array.isArray(report.top_processes.cpu) || report.top_processes.cpu.length === 0) && 
                    (!report.top_processes.memory || !Array.isArray(report.top_processes.memory) || report.top_processes.memory.length === 0) && 
                    (!report.top_processes.disk_io || !Array.isArray(report.top_processes.disk_io) || report.top_processes.disk_io.length === 0) && 
                    (!report.top_processes.network || !Array.isArray(report.top_processes.network) || report.top_processes.network.length === 0) && (
                    <div className="p-4 bg-white/5 rounded-lg border border-white/10 text-center text-gray-400 text-sm">
                    {report.top_processes ? 
                        'Top processes data exists but is empty. Process metrics may not be available for the selected time period.' :
                        'No process data available yet. Wait for the next hourly analysis.'
                    }
                    </div>
                )}
                </>
                ) : (
                <div className="p-4 bg-white/5 rounded-lg border border-white/10 text-center text-gray-400 text-sm">
                    No process data available yet. Wait for the next hourly analysis.
                </div>
                )}
            </div>

            {/* AI Recommendations */}
            {(() => {
                try {
                const recommendations = report.ai_insights?.recommendations;
                
                // Validate recommendations array
                if (!recommendations || !Array.isArray(recommendations) || recommendations.length === 0) {
                    return (
                    <div className="mt-4 p-3 bg-white/5 rounded-lg border border-white/10 text-center text-gray-400 text-sm">
                        No AI recommendations available yet.
                    </div>
                    );
                }
                
                return (
                    <div className="mt-4 space-y-2">
                    <h4 className="font-medium text-sm mb-2">AI Recommendations</h4>
                    {recommendations.slice(0, 5).map((rec: any, i: number) => {
                        try {
                        let action = '';
                        let details = '';
                        let priority = 'medium';
                        
                        if (typeof rec === 'string') {
                            action = rec;
                            details = rec;
                        } else if (typeof rec === 'object' && rec !== null) {
                            action = rec.title || rec.action || rec.name || '';
                            details = rec.description || rec.details || rec.explanation || action || '';
                            priority = (rec.priority || 'medium').toLowerCase();
                        }
                        
                        if (!action) action = `Recommendation ${i + 1}`;
                        
                        return (
                            <div key={i} className="p-3 bg-white/5 rounded-lg border border-white/10">
                            <div className="flex items-start gap-2">
                                <span className={`font-bold ${
                                priority === 'high' ? 'text-red-400' :
                                priority === 'medium' ? 'text-yellow-400' :
                                'text-blue-400'
                                }`}>#{i + 1}</span>
                                <div className="flex-1">
                                {action && <p className="text-sm font-medium text-gray-200">{action}</p>}
                                {details && details !== action && (
                                    <p className="text-xs text-gray-400 mt-1">{details}</p>
                                )}
                                </div>
                            </div>
                            </div>
                        );
                        } catch (error) {
                        return null;
                        }
                    })}
                    </div>
                );
                } catch (error) {
                return null;
                }
            })()}
            </section>
        </div>
        ) : (
        <div className="p-4 text-center text-gray-400">
            No report available yet. Click "Trigger Analysis" to generate one.
        </div>
        )}

      {/* AI Chat Interface */}
      <AIChat />
    </div>
  );
}
