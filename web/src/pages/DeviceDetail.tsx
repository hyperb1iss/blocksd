import { Link, useParams } from 'react-router';
import { DeviceDetailView } from '../components/device/DeviceDetailView';
import { useConfig } from '../hooks/useConfig';
import { useDevices } from '../hooks/useDevices';

export default function DeviceDetail() {
  const { uid } = useParams();
  const numericUid = uid ? Number(uid) : undefined;
  const devices = useDevices();
  const device = devices.find(d => d.uid === numericUid);
  const { values, setValue } = useConfig(numericUid);

  if (!device) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-muted mb-2">Device not found</p>
          <Link to="/" className="text-cyan text-sm hover:underline">
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  return <DeviceDetailView device={device} configValues={values} onConfigChange={setValue} />;
}
