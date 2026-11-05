import { createRoot } from 'react-dom/client';
import './styles/tokens.css';
import './styles/base.css';
import './styles/shell.css';
import './styles/components.css';
import './styles/pages.css';
import { App } from './App';
import { ToastProvider } from './components/ui/Toast';
import { ThemeProvider, applyStoredAppearance } from './state/ThemeProvider';

applyStoredAppearance();
if (!window.location.hash) {
  window.history.replaceState(null, '', '#overview');
}

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Missing #root');

createRoot(rootElement).render(
  <ThemeProvider>
    <ToastProvider>
      <App />
    </ToastProvider>
  </ThemeProvider>,
);
