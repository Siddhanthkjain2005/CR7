/** Linear interpolation of an actual plotted series at time t (no smoothing, no new data). */
export function sampleAt(time: number[] | undefined, values: number[] | undefined, t: number): number | null {
  if (!time?.length || !values?.length || !Number.isFinite(t)) return null;
  if (t <= time[0]) return values[0];
  const last = time.length - 1;
  if (t >= time[last]) return values[last];
  let lo = 0, hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (time[mid] <= t) lo = mid; else hi = mid;
  }
  const span = time[hi] - time[lo];
  if (span <= 0) return values[lo];
  return values[lo] + (values[hi] - values[lo]) * ((t - time[lo]) / span);
}
