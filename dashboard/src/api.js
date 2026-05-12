const BASE = ''  // proxied by Vite dev server

async function req(path, options = {}) {
  const token = localStorage.getItem('kobi_token')
  const res = await fetch(BASE + path, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
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
export const patchCargoShipment = (orderId, body) =>
  req(`/dashboard/cargo/shipment/${orderId}`, { method: 'PATCH', body: JSON.stringify(body) })
export const createCargoShipment = (body) =>
  req('/dashboard/cargo/shipment', { method: 'POST', body: JSON.stringify(body) })
export const deleteCargoShipment = (orderId) =>
  req(`/dashboard/cargo/shipment/${orderId}`, { method: 'DELETE' })

// Orders — GET /orders/ returns { items, total }
export const getOrders = (params = {}) => {
  const q = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== '')),
  ).toString()
  return req(`/orders/${q ? '?' + q : ''}`)
}
export const getOrderStatusCounts = () => req('/orders/status-counts')
export const getOrder = (id) => req(`/orders/${id}`)
export const updateOrderStatus = (id, body) =>
  req(`/orders/${id}/status`, { method: 'PUT', body: JSON.stringify(body) })
export const patchOrder = (id, body) =>
  req(`/orders/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
export const deleteOrder = (id) => req(`/orders/${id}`, { method: 'DELETE' })
export const createOrder = (body) =>
  req('/orders/', { method: 'POST', body: JSON.stringify(body) })

// Products
export const getProducts = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return req(`/products/${q ? '?' + q : ''}`)
}
export const createProduct = (body) =>
  req('/products/', { method: 'POST', body: JSON.stringify(body) })
export const updateStock = (id, body) =>
  req(`/products/${id}/stock`, { method: 'PATCH', body: JSON.stringify(body) })
export const patchProduct = (id, body) =>
  req(`/products/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
export const deleteProduct = (id) =>
  req(`/products/${id}`, { method: 'DELETE' })
export const getStockMovements = (id, limit = 50) =>
  req(`/products/${id}/movements?limit=${limit}`)

// Tickets
export const getTickets = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return req(`/tickets/${q ? '?' + q : ''}`)
}
export const getTicket = (id) => req(`/tickets/${id}`)
export const updateTicketStatus = (id, status, resolution = undefined) =>
  req(`/tickets/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({
      status,
      ...(resolution != null && resolution !== '' ? { resolution } : {}),
    }),
  })
export const createTicketManual = (body) =>
  req('/tickets/', { method: 'POST', body: JSON.stringify(body) })
export const getTicketStats = () => req('/tickets/stats/summary')

// Reports
export const getReports = () => req('/reports/')
export const getReport = (id) => req(`/reports/${id}`)
export const generateReport = () => req('/reports/generate', { method: 'POST' })
export const getTodayReport = () => req('/reports/latest/today')

// Admin Chat
export const adminChat = (mesaj, session_id) =>
  req('/api/v1/admin/chat', { method: 'POST', body: JSON.stringify({ mesaj, session_id }) })
export const confirmAdminPending = (onay_token, session_id) =>
  req('/api/v1/admin/pending/confirm', {
    method: 'POST',
    body: JSON.stringify({ onay_token, session_id }),
  })
export const clearAdminSession = (session_id) =>
  req(`/api/v1/admin/chat/${session_id}`, { method: 'DELETE' })

// Notifications
export const getNotifications = () => req('/api/v1/notifications')
export const markNotificationRead = (id) =>
  req(`/api/v1/notifications/${id}/read`, { method: 'POST' })

// Dashboard extras
export const getSalesChart = (days = 14) =>
  req(`/dashboard/sales-chart?days=${encodeURIComponent(days)}`)
export const generateAiTasks = () => req('/dashboard/ai-tasks', { method: 'POST' })
export const getAnalytics = () => req('/dashboard/analytics')
