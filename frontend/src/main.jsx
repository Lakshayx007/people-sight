import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';
import { registerAllThemes } from './themes/themeConfig.js';

// Register ECharts themes before React renders (Onco-Sight pattern)
registerAllThemes();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
