import React from "react";
import { describe, it, expect, vi } from "vitest";
import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { TabNav, type TabKey } from "../TabNav";

describe("TabNav", () => {
  it("renders all four tabs and marks the active one", () => {
    render(<TabNav active="overview" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: /overview/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /positions/i })).toHaveAttribute("aria-selected", "false");
    expect(screen.getAllByRole("tab")).toHaveLength(4);
  });

  it("fires onChange with the tab key when a tab is clicked", () => {
    const onChange = vi.fn();
    render(<TabNav active="overview" onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: /config/i }));
    expect(onChange).toHaveBeenCalledWith<[TabKey]>("config");
  });
});
