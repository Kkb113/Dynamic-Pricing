import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function allSourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolute = join(directory, entry.name);
    return entry.isDirectory() ? allSourceFiles(absolute) : [absolute];
  });
}

const sourceFiles = allSourceFiles(join(process.cwd(), "src"));

describe("frontend trust boundary", () => {
  it("does not persist transcripts or contain a direct provider call/key read", () => {
    const source = sourceFiles.map((file) => readFileSync(file, "utf8")).join("\n");
    expect(source).not.toMatch(/\b(localStorage|sessionStorage|indexedDB)\b/);
    expect(source).not.toMatch(/process\.env\.OPENAI_API_KEY|import\.meta\.env\.OPENAI_API_KEY/);
    expect(source).not.toMatch(/https?:\/\/api\.openai\.com/i);
    expect(source).not.toMatch(/tool_arguments|chain[-_ ]of[-_ ]thought|hidden_reasoning/i);
  });

  it("has no remote font or asset dependency", () => {
    const styles = readFileSync(join(process.cwd(), "src", "styles.css"), "utf8");
    expect(styles).not.toMatch(/@import\s+url\(/i);
    expect(styles).not.toMatch(/https?:\/\//i);
    const app = readFileSync(join(process.cwd(), "src", "App.tsx"), "utf8");
    expect(app).not.toMatch(/<iframe|<img\b|<script\b/i);
  });
});
