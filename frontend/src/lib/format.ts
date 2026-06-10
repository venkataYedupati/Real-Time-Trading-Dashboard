const compactFormatter = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 1,
})

const integerFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
})

export function currency(value: number, maxFractionDigits = 2) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: maxFractionDigits,
  }).format(value)
}

export function compact(value: number) {
  return compactFormatter.format(value)
}

export function integer(value: number) {
  return integerFormatter.format(value)
}

export function percent(value: number, digits = 2) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

export function signedCurrency(value: number) {
  const formatted = currency(Math.abs(value))
  return `${value >= 0 ? '+' : '-'}${formatted}`
}
