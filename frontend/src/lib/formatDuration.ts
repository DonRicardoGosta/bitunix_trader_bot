/** Másodpercből olvasható magyar időtartam. */
export function formatDurationSec(sec: number | null | undefined): string {
  if (sec == null || sec < 0) return "—";
  if (sec < 60) return `${sec} mp`;
  const minutes = Math.floor(sec / 60);
  if (minutes < 60) return `${minutes} perc`;
  const hours = Math.floor(minutes / 60);
  const remMin = minutes % 60;
  if (hours < 48) {
    return remMin > 0 ? `${hours} óra ${remMin} perc` : `${hours} óra`;
  }
  const days = Math.floor(hours / 24);
  const remH = hours % 24;
  if (remH === 0 && remMin === 0) return `${days} nap`;
  if (remMin === 0) return `${days} nap ${remH} óra`;
  return `${days} nap ${remH} óra ${remMin} perc`;
}
