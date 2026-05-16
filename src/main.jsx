import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

const app = <App />
const isElectron = Boolean(window?.process?.versions?.electron)

ReactDOM.createRoot(document.getElementById('root')).render(
    isElectron ? app : <React.StrictMode>{app}</React.StrictMode>,
)
