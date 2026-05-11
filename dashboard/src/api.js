const BASE = ''  // proxied by Vite dev server

async function req(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'İstek başarısız')
  }
  return res.json()
}

// Dashboard
export const getDashboardStats = () => req('/dashboard/stats')
export const getCargoDashboard = () => req('/dashboard/cargo')

// Orders
export const getOrders = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return req(`/orders/${q ? '?' + q : ''}`)
}
export const getOrder = (id) => req(`/orders/${id}`)
export const updateOrderStatus = (id, body) =>
  req(`/orders/${id}/status`, { method: 'PUT', body: JSON.stringify(body) })
export const createOrder = (body) =>
  req('/orders/', { method: 'POST', body: JSON.stringify(body) })

// Products
export const getProducts = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return req(`/products/${q ? '?' + q : ''}`)
}
export const updateStock = (id, body) =>
  req(`/products/${id}/stock`, { method: 'PATCH', body: JSON.stringify(body) })
export const getStockMovements = (id, limit = 50) =>
  req(`/products/${id}/movements?limit=${limit}`)

// Tickets
export const getTickets = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return req(`/tickets/${q ? '?' + q : ''}`)
}
export const getTicket = (id) => req(`/tickets/${id}`)
export const updateTicketStatus = (id, status) =>
  req(`/tickets/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) })
export const createTicketManual = (body) =>
  req('/tickets/', { method: 'POST', body: JSON.stringify(body) })
export const getTicketStats = () => req('/tickets/stats/summary')

// Reports
export const getReports = () => req('/reports/')
export const getReport = (id) => req(`/reports/${id}`)
export const generateReport = () => req('/reports/generate', { method: 'POST' })
export const getTodayReport = () => req('/reports/latest/today')

// Notifications
export const getNotifications = () => req('/api/v1/notifications')
