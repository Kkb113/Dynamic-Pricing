import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownAnswer } from "../src/components/MarkdownAnswer";

describe("MarkdownAnswer", () => {
  it("renders executive Markdown and formats machine-precision currency", () => {
    render(<MarkdownAnswer content={"## Executive recommendation\n\nExpected revenue is **$74.16585879335369** and gross profit is **$37.441696215704646**."} />);
    expect(screen.getByRole("heading", { name: "Executive recommendation" })).toBeInTheDocument();
    expect(screen.getByText("$74.17")).toBeInTheDocument();
    expect(screen.getByText("$37.44")).toBeInTheDocument();
    expect(screen.queryByText(/74\.165858/)).not.toBeInTheDocument();
  });

  it("replaces internal phase terminology with business labels", () => {
    render(<MarkdownAnswer content={"Compare **Phase6 Model-Optimal Price** with **Phase7 Final Recommended Price**."} />);
    expect(screen.getByText("Model recommendation")).toBeInTheDocument();
    expect(screen.getByText("Final recommendation")).toBeInTheDocument();
    expect(screen.queryByText(/Phase[67]/)).not.toBeInTheDocument();
  });

  it("translates raw identifiers and implementation language", () => {
    render(<MarkdownAnswer content={"Dynamic pricing result for PDL000000000029917 uses CHANNEL | Email for PRO000001 at STO000005."} />);
    expect(screen.getByText(/pricing strategy result/i)).toBeInTheDocument();
    expect(screen.getByText(/Email channel/i)).toBeInTheDocument();
    expect(screen.queryByText(/PDL\d+|PRO\d+|STO\d+|CHANNEL\s*\|/i)).not.toBeInTheDocument();
  });
});
