import React from 'react';
import { createRoot } from 'react-dom/client';

function App() {
  return (
    <main>
      <h1>AIoT platform ready</h1>
      <p data-testid="smoke-status">frontend smoke ok</p>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
