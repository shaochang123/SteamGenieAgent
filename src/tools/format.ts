const BYTES_PER_GB = 1024 * 1024 * 1024;

export function formatHours(minutes: number): string { return (Math.round((minutes / 60) * 10) / 10).toString(); }

export function formatWholeHours(minutes: number): number { return Math.round(minutes / 60); }

export function formatGigabytes(bytes: number): string { return (bytes / BYTES_PER_GB).toFixed(1); }

export function formatCny(amount: number): string { return `¥${amount.toFixed(2)}`; }

export function formatCnyCents(cents: number): string { return formatCny(cents / 100); }

export function steamStoreUrl(appid: number): string { return `https://store.steampowered.com/app/${appid}/`; }

export function steamMarketUrl(appid: number, itemName: string): string {
  return `https://steamcommunity.com/market/listings/${appid}/${encodeURIComponent(itemName)}`;
}
