/** The ISO day (YYYY-MM-DD) of a date, in UTC: frontmatter dates parse as UTC midnight. */
export function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}
