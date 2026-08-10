import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { ToastProvider } from './components/ui'
import { router } from './router'
import './styles/global.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider>
  </StrictMode>,
)
