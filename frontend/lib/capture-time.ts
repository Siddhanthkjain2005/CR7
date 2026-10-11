/** ISO 8601 with this device's local time and the offset at that instant. */
export function captureTimeNow(date = new Date()): string {
  const pad = (value: number, width = 2) => String(value).padStart(width, '0');
  const offset = -date.getTimezoneOffset();
  const zone = `${offset < 0 ? '-' : '+'}${pad(Math.floor(Math.abs(offset) / 60))}:${pad(Math.abs(offset) % 60)}`;
  return `${pad(date.getFullYear(), 4)}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}${zone}`;
}
