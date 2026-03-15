import { BrowserRouter, Route, Routes } from 'react-router';
import { AppShell } from './components/layout/AppShell';
import { BlocksdProvider } from './hooks/useBlocksd';
import Dashboard from './pages/Dashboard';
import DeviceDetail from './pages/DeviceDetail';

export default function App() {
  return (
    <BlocksdProvider>
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/device/:uid" element={<DeviceDetail />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
    </BlocksdProvider>
  );
}
