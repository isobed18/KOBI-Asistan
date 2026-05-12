export default function ListPagination({
  page,
  totalPages,
  total,
  loading,
  onPrev,
  onNext,
  className = '',
  footer = false,
}) {
  return (
    <div
      className={`orders-pagination-bar${footer ? ' orders-pagination-bar--footer' : ''} ${className}`.trim()}
      role="navigation"
      aria-label={footer ? 'Sayfa gezgini alt' : 'Sayfa gezgini'}
    >
      <button type="button" className="btn btn-ghost btn-sm" disabled={page <= 0 || loading} onClick={onPrev}>
        ← Önceki
      </button>
      <span className="orders-pagination-meta">
        Sayfa {page + 1} / {totalPages} · {total} kayıt
      </span>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        disabled={loading || (page + 1) >= totalPages}
        onClick={onNext}
      >
        Sonraki →
      </button>
    </div>
  )
}
