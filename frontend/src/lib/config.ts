const DEFAULT_API_BASE_URL = "";
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
  if (candidate.trim() === "") return "";
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new ApiConfigurationError("The API base URL must be a valid HTTP URL or empty for same-origin requests.");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new ApiConfigurationError("The API base URL must use HTTP or HTTPS.");
  }
  const normalizedHostname = parsed.hostname.toLowerCase().replace(/^\[|\]$/g, "");
  const currentHost = typeof window !== "undefined" ? window.location.hostname.toLowerCase() : "";
  if (!LOOPBACK_HOSTS.has(normalizedHostname) && normalizedHostname !== currentHost) {
    throw new ApiConfigurationError("The API URL must be loopback or the same origin as this application.");
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
