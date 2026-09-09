export function parseApiTimestamp(timestamp: string): number {
  const value = timestamp.trim()
  // SQLite/Pydantic API timestamps are UTC even when they omit a timezone.
  // Add it only to full naive datetimes; explicit offsets keep their own instant.
  const normalized = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value)
    ? `${value.replace(' ', 'T')}Z`
    : value
  return Date.parse(normalized)
}
