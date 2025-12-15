import { useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Server, 
  Shield, 
  Brain, 
  Settings, 
  ChevronLeft,
  ChevronRight,
  Activity,
  LayoutGrid,
  Bell,
  Layers,
  Network,
  HeartPulse
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface DashboardLayoutProps {
  children?: React.ReactNode;
  header?: React.ReactNode;
  outletContext?: any;
}

export function DashboardLayout({ children, header, outletContext }: DashboardLayoutProps) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const location = useLocation();

  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);

  const navItems = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard },
    { name: 'Infrastructure', path: '/infrastructure', icon: Server },
    { name: 'Observability', path: '/observability', icon: Activity },
    { name: 'SNMP', path: '/snmp', icon: Network },
    { name: 'Dashboards', path: '/dashboards', icon: LayoutGrid },
    { name: 'Alerts', path: '/alerts', icon: Bell },
    { name: 'Recording Rules', path: '/recording-rules', icon: Layers },
    { name: 'Security', path: '/security', icon: Shield },
    { name: 'Analysis', path: '/analysis', icon: Brain },
    { name: 'System Health', path: '/system-health', icon: HeartPulse },
  ];


  return (
    <div className="min-h-screen bg-deep text-white flex overflow-hidden">
        {/* Background Mesh Gradient (Global) */}
        <div className="fixed inset-0 bg-grid-pattern opacity-20 pointer-events-none z-0" />

      {/* Sidebar */}
      <motion.aside 
        initial={false}
        animate={{ width: isSidebarOpen ? 240 : 70 }}
        className="glass-card-intense border-r border-white/10 z-30 flex flex-col relative transition-all duration-300 ease-in-out"
      >
        {/* Logo Area */}
        <div className="h-16 flex items-center justify-center border-b border-white/10 overflow-hidden relative">
          <div className={`flex items-center gap-3 ${isSidebarOpen ? 'px-6 w-full' : 'px-0 justify-center'}`}>
            <div className="relative flex-shrink-0">
               <div className="w-8 h-8 rounded-lg flex items-center justify-center shadow-neon-blue/20">
                  <span className="font-bold text-white text-lg font-display">Xcr9</span>
               </div>
            </div>
            <AnimatePresence mode="wait">
            {isSidebarOpen && (
              <motion.span 
                key="logo-text"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="font-bold font-display tracking-tight text-lg bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent truncate"
              >
                AncientReport
              </motion.span>
            )}
            </AnimatePresence>
          </div>
        </div>

        {/* Toggle Button */}
        <button 
            onClick={toggleSidebar}
            className="absolute -right-3 top-20 bg-deep border border-white/10 rounded-full p-1 text-gray-400 hover:text-white hover:border-neon-blue transition-colors z-50"
        >
            {isSidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
        </button>

        {/* Navigation */}
        <nav className="flex-1 py-6 px-3 space-y-2 overflow-y-auto overflow-x-hidden scrollbar-hide">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            const Icon = item.icon;
            
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) => `
                  relative group flex items-center gap-3 px-3 py-3 rounded-xl transition-all duration-200
                  ${isActive 
                    ? 'bg-neon-blue/10 text-neon-blue shadow-[0_0_15px_rgba(0,243,255,0.1)]' 
                    : 'text-gray-400 hover:bg-white/5 hover:text-white'
                  }
                `}
              >
                {isActive && (
                    <motion.div
                        layoutId="activeTab"
                        className="absolute inset-0 border border-neon-blue/30 rounded-xl"
                        transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    />
                )}
                <Icon size={20} className={`flex-shrink-0 ${isActive ? 'text-neon-blue' : 'group-hover:text-neon-blue transition-colors'}`} />
                
                <AnimatePresence mode="wait">
                {isSidebarOpen && (
                    <motion.span
                        key="nav-text"
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -10 }}
                        className="font-medium truncate"
                    >
                        {item.name}
                    </motion.span>
                )}
                </AnimatePresence>
                
                {!isSidebarOpen && (
                    <div className="absolute left-full ml-4 px-2 py-1 bg-gray-900 border border-white/10 rounded-md text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
                        {item.name}
                    </div>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Bottom Actions */}
        <div className="p-3 border-t border-white/10">
          <NavLink
            to="/settings"
            className={({ isActive }) => `
              flex items-center gap-3 px-3 py-3 rounded-xl transition-all duration-200
              ${isActive 
                ? 'bg-neon-purple/10 text-neon-purple' 
                : 'text-gray-400 hover:bg-white/5 hover:text-white'
              }
            `}
          >
            <Settings size={20} className="flex-shrink-0" />
            <AnimatePresence mode="wait">
            {isSidebarOpen && (
                <motion.span
                    key="settings-text"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="font-medium truncate"
                >
                    Settings
                </motion.span>
            )}
            </AnimatePresence>
          </NavLink>
        </div>
      </motion.aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-transparent relative z-10">
        {header}
        <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent p-6 overflow-x-hidden">
            <Outlet context={outletContext} />
        </div>
      </div>
    </div>
  );
}
