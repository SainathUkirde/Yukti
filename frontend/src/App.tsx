/* src/App.tsx — Root app with routing */
import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Dashboard from '@/components/dashboard/Dashboard'
import AuditPage from '@/pages/AuditPage'
import RodLifePage from '@/pages/RodLifePage'
import FieldPlannerPage from '@/pages/FieldPlannerPage'
import CalibrationPage from '@/pages/CalibrationPage'
import CarbonPage from '@/pages/CarbonPage'
import HandoverPage from '@/pages/HandoverPage'
import { NavBar } from '@/components/ui/NavBar'
import { useStore } from '@/store/useStore'
import { wellsApi } from '@/api/wells'
import { useFleetStream } from '@/hooks/useFleetStream'

function AppInner() {
  const { setAllWells, selectWell, allWells, selectedWellId } = useStore()
  useFleetStream()

  // Initial load of well list
  useEffect(() => {
    wellsApi.list().then((res) => {
      setAllWells(res.wells)
      if (res.wells.length > 0 && !selectedWellId) {
        selectWell(res.wells[0].well_id)
      }
    }).catch(console.error)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-select first well when fleet loads
  useEffect(() => {
    if (allWells.length > 0 && !selectedWellId) {
      selectWell(allWells[0].well_id)
    }
  }, [allWells, selectedWellId, selectWell])

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-bg">
      {/* Global nav bar — 32px, sits above all pages */}
      <NavBar />

      {/* Page content */}
      <div className="flex-1 overflow-auto min-h-0">
        <Routes>
          <Route path="/"          element={<Dashboard />} />
          <Route path="/audit"     element={<AuditPage />} />
          <Route path="/rod-life"  element={<RodLifePage />} />
          <Route path="/field"     element={<FieldPlannerPage />} />
          <Route path="/calibrate" element={<CalibrationPage />} />
          <Route path="/carbon"    element={<CarbonPage />} />
          <Route path="/handover"  element={<HandoverPage />} />
          <Route path="*"          element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppInner />
    </BrowserRouter>
  )
}
