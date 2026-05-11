/** Türkçe metin + sayısal alt dizeler için sıralama */
export function cmpNullableStr(a, b) {
  const sa = (a ?? '').toString()
  const sb = (b ?? '').toString()
  return sa.localeCompare(sb, 'tr', { numeric: true, sensitivity: 'base' })
}

export function cmpNum(a, b) {
  const na = Number(a)
  const nb = Number(b)
  const fa = Number.isFinite(na)
  const fb = Number.isFinite(nb)
  if (!fa && !fb) return 0
  if (!fa) return 1
  if (!fb) return -1
  return na - nb
}

export function cmpTime(a, b) {
  const ta = a ? new Date(a).getTime() : 0
  const tb = b ? new Date(b).getTime() : 0
  const fa = Number.isFinite(ta)
  const fb = Number.isFinite(tb)
  if (!fa && !fb) return 0
  if (!fa) return 1
  if (!fb) return -1
  return ta - tb
}

export function cmpBool(a, b) {
  if (a === b) return 0
  return a ? 1 : -1
}
