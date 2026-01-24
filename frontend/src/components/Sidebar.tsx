/**
 * Sidebar Navigation Component
 *
 * Features:
 * - Two navigation items: Chat, Dashboard
 * - Lucide icons for each item
 * - Collapsible on mobile (hamburger menu)
 * - Active view highlighting
 * - Professional blue/gray FM theme
 */

import { useState } from "react";
import { MessageSquare, LayoutDashboard, Menu, X } from "lucide-react";

export type View = "dashboard" | "chat";

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
}

interface NavItem {
  id: View;
  label: string;
  icon: typeof MessageSquare;
}

const navItems: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "chat", label: "Chat", icon: MessageSquare },
];

export function Sidebar({ currentView, onViewChange }: SidebarProps) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  const handleNavClick = (view: View) => {
    onViewChange(view);
    setIsMobileOpen(false); // Close mobile menu after selection
  };

  return (
    <>
      {/* Mobile hamburger button */}
      <button
        onClick={() => setIsMobileOpen(!isMobileOpen)}
        className="md:hidden fixed top-4 left-4 z-50 p-2 bg-white rounded-lg shadow-md border border-gray-200 hover:bg-gray-50 transition-colors"
        aria-label={isMobileOpen ? "Close menu" : "Open menu"}
      >
        {isMobileOpen ? (
          <X className="h-5 w-5 text-gray-600" />
        ) : (
          <Menu className="h-5 w-5 text-gray-600" />
        )}
      </button>

      {/* Mobile overlay */}
      {isMobileOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/30 z-30"
          onClick={() => setIsMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed md:relative inset-y-0 left-0 z-40
          w-64 md:w-20 lg:w-64
          bg-white border-r border-gray-200
          transform transition-transform duration-200 ease-in-out
          ${isMobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
          flex flex-col
        `}
      >
        {/* Logo area - hidden on mobile when header is visible */}
        <div className="flex-none h-[73px] flex items-center justify-center border-b border-gray-200 md:block hidden">
          <div className="flex items-center gap-2 px-4">
            <div className="w-8 h-8 bg-bidvest-blue-600 rounded-lg flex items-center justify-center">
              <LayoutDashboard className="h-5 w-5 text-white" />
            </div>
            <span className="font-semibold text-gray-900 hidden lg:block">BMS</span>
          </div>
        </div>

        {/* Navigation items */}
        <nav className="flex-1 p-4 space-y-2 mt-16 md:mt-0" role="navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentView === item.id;

            return (
              <button
                key={item.id}
                onClick={() => handleNavClick(item.id)}
                className={`
                  w-full flex items-center gap-3 px-4 py-3 rounded-lg
                  transition-all duration-150 ease-in-out
                  ${
                    isActive
                      ? "bg-bidvest-blue-50 text-bidvest-blue-700 border border-bidvest-blue-200"
                      : "text-gray-600 hover:bg-gray-50 hover:text-gray-900 border border-transparent"
                  }
                `}
                aria-current={isActive ? "page" : undefined}
              >
                <Icon
                  className={`h-5 w-5 flex-shrink-0 ${
                    isActive ? "text-bidvest-blue-600" : "text-gray-400"
                  }`}
                />
                <span className="font-medium md:hidden lg:block">{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="flex-none p-4 border-t border-gray-200">
          <div className="text-xs text-gray-400 text-center md:hidden lg:block">
            FM Assistant v1.0
          </div>
        </div>
      </aside>
    </>
  );
}

export default Sidebar;
