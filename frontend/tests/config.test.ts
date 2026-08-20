import { describe, expect, it } from "vitest";
import { ApiConfigurationError, DEFAULT_API_BASE_URL, resolveApiBaseUrl } from "../src/lib/config";

describe("local API boundary", () => {
  it("defaults to the loopback Phase 2 service and normalizes paths", () => {
    expect(DEFAULT_API_BASE_URL).toBe("http://127.0.0.1:8000");
    expect(resolveApiBaseUrl("http://localhost:8000/")).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl("http://[::1]:8000/path?query=ignored")).toBe("http://[::1]:8000/path");
  });

  it.each(["https://api.example.com", "http://192.168.1.2:8000", "file:///tmp/api", "http://user:pass@127.0.0.1:8000"]) (
    "rejects unsafe API base %s",
    (candidate) => expect(() => resolveApiBaseUrl(candidate)).toThrow(ApiConfigurationError),
  );
});
