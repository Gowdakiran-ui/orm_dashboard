import { formatDM, formatDMHour } from "./dateFormat";
export function formatChartDate(dateString: string | null | undefined, includeHour: boolean = false): string {
  if (!dateString) return "N/A";
  try {
    return includeHour ? formatDMHour(dateString, "N/A") : formatDM(dateString, "N/A");
  } catch {
    return "N/A";
  }
}
