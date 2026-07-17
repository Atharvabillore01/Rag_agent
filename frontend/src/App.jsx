import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import ProtectedRoute from './components/ProtectedRoute'
import Login      from './pages/Login'
import Register   from './pages/Register'
import Chat          from './pages/Chat'
import Documents     from './pages/Documents'
import ParallelReview from './pages/ParallelReview'
import Redline       from './pages/Redline'
import Translation   from './pages/Translation'
import ListOfDates   from './pages/ListOfDates'
import Contentions   from './pages/Contentions'
import SensitiveScan from './pages/SensitiveScan'
import Drafting      from './pages/Drafting'
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
            <Route path="/review"        element={<ParallelReview />} />
            <Route path="/redline"       element={<Redline />} />
            <Route path="/translation"   element={<Translation />} />
            <Route path="/lod"           element={<ListOfDates />} />
            <Route path="/contentions"   element={<Contentions />} />
            <Route path="/sensitive"     element={<SensitiveScan />} />
            <Route path="/drafting"      element={<Drafting />} />
            <Route path="/admin"         element={<Admin />} />
            <Route path="/observability" element={<Observability />} />
          </Route>
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AnimatePresence>
    </BrowserRouter>
  )
}
