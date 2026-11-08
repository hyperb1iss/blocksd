import { BrowserRouter, Route, Routes } from 'react-router';
import { Studio } from './components/Studio';
import { BlocksdProvider } from './hooks/useBlocksd';

export default function App() {
  return (
    <BlocksdProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Studio />} />
          <Route path="/device/:serial" element={<Studio />} />
          <Route path="/presets" element={<Studio />} />
          <Route path="*" element={<Studio />} />
        </Routes>
      </BrowserRouter>
    </BlocksdProvider>
  );
}
