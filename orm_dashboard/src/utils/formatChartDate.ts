export function formatChartDate(dateString: string | null | undefined, includeHour: boolean = false): string {
  if (!dateString) return "N/A";
  try {
    const options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
    if (includeHour) {
      options.hour = "2-digit";
    }
    return new Date(dateString).toLocaleDateString(undefined, options);
  } catch {
    return "N/A";
  }
}
