export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
  const value = bytes / Math.pow(k, i);
  return `${value >= 10 || i === 0 ? value.toFixed(0) : value.toFixed(2)} ${sizes[i]}`;
}

/** Parse human-readable size input like "1MB", "512 KB", or raw bytes "2048". */
export function parseSizeInput(input: string): number | undefined {
  const trimmed = input.trim();
  if (!trimmed) return undefined;

  const match = trimmed.match(/^([\d.]+)\s*(b|kb|mb|gb)?$/i);
  if (!match) return undefined;

  const value = parseFloat(match[1]);
  if (isNaN(value)) return undefined;

  const unit = (match[2] || 'b').toLowerCase();
  const multipliers: Record<string, number> = { b: 1, kb: 1024, mb: 1024 ** 2, gb: 1024 ** 3 };
  return Math.floor(value * (multipliers[unit] ?? 1));
}
