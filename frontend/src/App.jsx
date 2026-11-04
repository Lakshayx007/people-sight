import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { FilterProvider } from './context/FilterContext';
import { ThemeProvider } from './context/ThemeContext';
import Sentiment from './pages/Sentiment';
import Hiring from './pages/Hiring';
import DataQuality from './pages/DataQuality';

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <FilterProvider>
          <Layout>
            <Routes>
              <Route path="/" element={<Navigate to="/sentiment" replace />} />
              <Route path="/sentiment" element={<Sentiment />} />
              <Route path="/hiring" element={<Hiring />} />
              <Route path="/data-quality" element={<DataQuality />} />
              <Route path="*" element={<Navigate to="/sentiment" replace />} />
            </Routes>
          </Layout>
        </FilterProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
