function withBeijingOffset(value: string): string {
  if (/([zZ]|[+-]\d{2}:\d{2})$/.test(value)) return value
  return `${value}+08:00`
}

export function toBeijingDate(value: string): Date {
  return new Date(withBeijingOffset(value))
}

export function formatBeijingTime(value: string | null | undefined): string {
  if (!value) return '-'
  return toBeijingDate(value).toLocaleString('zh-CN', {
    hour12: false,
    timeZone: 'Asia/Shanghai',
  })
}

export function formatBeijingDate(value: string | null | undefined): string {
  if (!value) return '-'
  return toBeijingDate(value).toLocaleDateString('zh-CN', {
    timeZone: 'Asia/Shanghai',
  })
}
