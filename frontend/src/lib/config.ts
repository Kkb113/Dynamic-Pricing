const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

export class ApiConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigurationError";
  }
}

function configuredApiBase(): string {
  const candidate = import.meta.env.VITE_API_BASE_URL;
  return typeof candidate === "string" && candidate.trim() !== "" ? candidate.trim() : DEFAULT_API_BASE_URL;
}

export function resolveApiBaseUrl(candidate = configuredApiBase()): string {
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new ApiConfigurationError("The API base URL must be a valid loopback HTTP URL.");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new ApiConfigurationError("The API base URL must use HTTP or HTTPS.");
  }
  const normalizedHostname = parsed.hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (!LOOPBACK_HOSTS.has(normalizedHostname)) {
    throw new ApiConfigurationError("This local application only permits a loopback API base URL.");
  }
  if (parsed.username || parsed.password) {
    throw new ApiConfigurationError("Credentials are not permitted in the API base URL.");
  }
  parsed.hash = "";
  parsed.search = "";
  return parsed.toString().replace(/\/$/, "");
}

export const API_BASE_URL = resolveApiBaseUrl();
export { DEFAULT_API_BASE_URL };
