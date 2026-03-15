import { Link } from 'react-router';
import { useDevices } from '../../hooks/useDevices';
import { DeviceList } from './DeviceList';
import { StatusBar } from './StatusBar';

export function AppShell({ children }: { children: React.ReactNode }) {
  const devices = useDevices();

  return (
    <div className="flex h-screen bg-panel text-text font-mono">
      {/* Sidebar */}
      <aside className="w-64 border-r border-surface flex flex-col shrink-0">
        <Link
          to="/"
          className="block p-4 border-b border-surface hover:bg-surface/50 transition-colors"
        >
          <h1 className="text-cyan text-lg font-bold tracking-tight">blocksd</h1>
          <p className="text-[10px] text-muted mt-0.5">ROLI Blocks Manager</p>
        </Link>
        <DeviceList devices={devices} />
        <StatusBar />
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
