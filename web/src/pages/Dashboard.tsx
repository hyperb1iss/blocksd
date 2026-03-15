import { DashboardView } from '../components/dashboard/DashboardView';
import { useDevices } from '../hooks/useDevices';
import { useTopology } from '../hooks/useTopology';

export default function Dashboard() {
  const devices = useDevices();
  const { connections } = useTopology();

  return <DashboardView devices={devices} connections={connections} />;
}
