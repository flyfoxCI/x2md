/** Returns whether an untrusted URL is an absolute HTTPS destination. */
export function isSafeHttpsUrl(value: string | undefined): value is string {
  if (!value) {
    return false;
  }
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}
