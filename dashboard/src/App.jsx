import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Overview  from './pages/Overview.jsx'
import Orders    from './pages/Orders.jsx'
import Cargo     from './pages/Cargo.jsx'
import Inventory from './pages/Inventory.jsx'
import Tickets   from './pages/Tickets.jsx'
import Reports   from './pages/Reports.jsx'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/"          element={<Overview />}  />
        <Route path="/orders"    element={<Orders />}    />
        <Route path="/cargo"     element={<Cargo />}     />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/tickets"   element={<Tickets />}   />
        <Route path="/reports"   element={<Reports />}   />
        <Route path="*"          element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
