import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'

// Suppress errors from third-party scripts/extensions
const originalError = window.onerror
window.onerror = (message, source, lineno, colno, error) => {
  // Ignore errors from browser extensions or third-party scripts
  if (source && (
    source.includes('standalone.js') ||
    source.includes('extension://') ||
    source.includes('moz-extension://') ||
    source.includes('chrome-extension://') ||
    source.includes('safari-extension://')
  )) {
    console.warn('Suppressed error from extension/third-party script:', message, source)
    return true // Suppress the error
  }
  // Call original error handler if it exists
  if (originalError) {
    return originalError(message, source, lineno, colno, error)
  }
  return false
}

// Also catch unhandled promise rejections from extensions
const originalUnhandledRejection = window.onunhandledrejection
window.onunhandledrejection = (event) => {
  if (event.reason && typeof event.reason === 'object' && event.reason.stack) {
    const stack = event.reason.stack.toString()
    if (stack.includes('standalone.js') || 
        stack.includes('extension://') ||
        stack.includes('moz-extension://') ||
        stack.includes('chrome-extension://')) {
      console.warn('Suppressed unhandled rejection from extension:', event.reason)
      event.preventDefault()
      return
    }
  }
  if (originalUnhandledRejection) {
    originalUnhandledRejection(event)
  }
}

console.log('AncientReport UI: Initializing...')

const rootElement = document.getElementById('root')
if (!rootElement) {
  console.error('Root element not found!')
  throw new Error('Root element not found')
}

try {
  createRoot(rootElement).render(
    <StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </StrictMode>,
  )
  console.log('AncientReport UI: Rendered successfully')
} catch (error) {
  console.error('AncientReport UI: Failed to render', error)
  rootElement.innerHTML = `
    <div style="min-height: 100vh; background: #0f172a; color: white; display: flex; align-items: center; justify-content: center; padding: 2rem;">
      <div style="text-align: center;">
        <h1 style="color: #ef4444; margin-bottom: 1rem;">Failed to Load Application</h1>
        <p style="color: #94a3b8; margin-bottom: 1rem;">Please check the browser console for details.</p>
        <pre style="background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 0.5rem; overflow: auto; text-align: left;">
${error instanceof Error ? error.toString() : String(error)}
        </pre>
      </div>
    </div>
  `
}
