/** Read rows are dropped before render, so a refresh cannot paint them. */
export function visibleNotices<T extends { read: boolean }>(rows: readonly T[]): T[] {
  return rows.filter((row) => !row.read);
}
