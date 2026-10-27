export const localDate = (date = new Date()) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

export const validDate = (value: string) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(year, month - 1, day);
  return parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day;
};

export const observedTime = (value: string | null | undefined) => {
  if (!value) return 'Time unavailable';
  // Legacy SQLite observations are UTC without an offset. Preserve an existing
  // offset rather than appending a second Z and creating an invalid date.
  const normalized = value.replace(' ', 'T');
  const date = new Date(/[zZ]$|[+-]\d{2}:\d{2}$/.test(normalized) ? normalized : normalized + 'Z');
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : date.toLocaleString();
};
