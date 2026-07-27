import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import ReceptionDashboard from './clinic/ReceptionDashboard'
import DoctorDashboard from './clinic/DoctorDashboard'
import ManagementDashboard from './clinic/ManagementDashboard'

// Full-screen clinic area (no document sidebar). Renders the dashboard for the
// signed-in user's role; anyone without a clinic role is sent to the app home.
export default function ClinicHome() {
  const user = useAuthStore(s => s.user)
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'reception') return <ReceptionDashboard />
  if (user.role === 'doctor') return <DoctorDashboard />
  if (user.role === 'org_admin') return <ManagementDashboard />
  return <Navigate to="/chat" replace />
}
