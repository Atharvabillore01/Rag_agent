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
import CrossExam     from './pages/CrossExam'
import PlaybookReview from './pages/PlaybookReview'
import Drafting      from './pages/Drafting'
import Admin         from './pages/Admin'
import Observability from './pages/Observability'
import PlatformConsole from './pages/PlatformConsole'
import PlatformLogin  from './pages/PlatformLogin'
import ClinicHome     from './pages/ClinicHome'

export default function App() {
  return (
    <BrowserRouter>
      <AnimatePresence mode="wait">
        <Routes>
          <Route path="/login"    element={<Login />} />
          <Route path="/platform/login" element={<PlatformLogin />} />
          <Route path="/register" element={<Register />} />
          {/* Full-screen clinic area (its own gate + layout, no document sidebar) */}
          <Route path="/clinic" element={<ClinicHome />} />
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
            <Route path="/cross-exam"    element={<CrossExam />} />
            <Route path="/playbook"      element={<PlaybookReview />} />
            <Route path="/drafting"      element={<Drafting />} />
            <Route path="/admin"         element={<Admin />} />
            <Route path="/observability" element={<Observability />} />
            <Route path="/platform"      element={<PlatformConsole />} />
          </Route>
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AnimatePresence>
    </BrowserRouter>
  )
}
