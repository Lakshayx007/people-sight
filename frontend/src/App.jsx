import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { MotionConfig } from 'motion/react';
import Layout from './components/Layout';
import { FilterProvider } from './context/FilterContext';
import { ThemeProvider } from './context/ThemeContext';
import Landing from './pages/Landing';
import Sentiment from './pages/Sentiment';
import Hiring from './pages/Hiring';
import DataQuality from './pages/DataQuality';

function Dashboards() {
  return (
    <Layout>
      <Routes>
        <Route path="/sentiment" element={<Sentiment />} />
        <Route path="/hiring" element={<Hiring />} />
        <Route path="/data-quality" element={<DataQuality />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <MotionConfig reducedMotion="user">
        <BrowserRouter>
          <FilterProvider>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/*" element={<Dashboards />} />
            </Routes>
          </FilterProvider>
        </BrowserRouter>
      </MotionConfig>
    </ThemeProvider>
  );
}
