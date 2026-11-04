import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { FilterProvider } from './context/FilterContext';
import { ThemeProvider } from './context/ThemeContext';
import Sentiment from './pages/Sentiment';
import Placeholder from './pages/Placeholder';

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <FilterProvider>
          <Layout>
            <Routes>
              <Route path="/" element={<Navigate to="/sentiment" replace />} />
              <Route path="/sentiment" element={<Sentiment />} />
              <Route path="/hiring" element={<Placeholder title="Hiring" phase="Phase 7" />} />
              <Route path="/data-quality" element={<Placeholder title="Data quality" phase="Phase 7" />} />
              <Route path="*" element={<Navigate to="/sentiment" replace />} />
            </Routes>
          </Layout>
        </FilterProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
