import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import ProtectedRoute from './components/ProtectedRoute'
import Login      from './pages/Login'
import Register   from './pages/Register'
import Chat          from './pages/Chat'
import Documents     from './pages/Documents'
import Admin         from './pages/Admin'
import Observability from './pages/Observability'

export default function App() {
  return (
    <BrowserRouter>
      <AnimatePresence mode="wait">
        <Routes>
          <Route path="/login"    element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/"          element={<Navigate to="/chat" replace />} />
            <Route path="/chat"      element={<Chat />} />
            <Route path="/documents"     element={<Documents />} />
            <Route path="/admin"         element={<Admin />} />
            <Route path="/observability" element={<Observability />} />
          </Route>
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AnimatePresence>
    </BrowserRouter>
  )
}
