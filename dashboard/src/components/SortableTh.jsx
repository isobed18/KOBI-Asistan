export default function SortableTh({ columnKey, sortKey, sortDir, onSort, align, children }) {
  const active = columnKey === sortKey
  return (
    <th
      role="columnheader"
      scope="col"
      className={`th-sortable${active ? ' th-sort-active' : ''}`}
      onClick={() => onSort(columnKey)}
      style={align ? { textAlign: align } : undefined}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
    >
      {children}
      <span className="th-sort-hint" aria-hidden>
        {active ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ' ↕'}
      </span>
    </th>
  )
}
