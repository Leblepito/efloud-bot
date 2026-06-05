import React from "react";
import { describe, it, expect } from "vitest";
import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { KronosCard } from "../KronosCard";

describe("KronosCard Component", () => {
  it("renders nothing when kronos_comment is absent", () => {
    const trade = {
      symbol: "BTCUSDT",
    };
    const { container } = render(<KronosCard trade={trade} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders comment, band, and advisory disclaimer when kronos_comment is present", () => {
    const trade = {
      symbol: "BTCUSDT",
      kronos_comment: "Kronos predicts upward movement based on local FVG support.",
      kronos_confidence: 90,
    };

    render(<KronosCard trade={trade} />);

    // Check header/commentary title
    expect(screen.getByText("Kronos AI Forecast")).toBeInTheDocument();

    // Check band badge
    expect(screen.getByText("NARROW")).toBeInTheDocument();

    // Check commentary content
    expect(
      screen.getByText("Kronos predicts upward movement based on local FVG support.")
    ).toBeInTheDocument();

    // Check advisory warning is visible and clear
    expect(screen.getByText(/ADVISORY ONLY/)).toBeInTheDocument();
    expect(
      screen.getByText(/This analysis is post-signal commentary and did/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/influence or gate the trade execution/i)
    ).toBeInTheDocument();
  });

  it("deduces WIDE band for lower confidence", () => {
    const trade = {
      symbol: "ETHUSDT",
      kronos_comment: "High variance and mixed signal path forecast.",
      kronos_confidence: 45,
    };

    render(<KronosCard trade={trade} />);
    expect(screen.getByText("WIDE")).toBeInTheDocument();
  });
});
