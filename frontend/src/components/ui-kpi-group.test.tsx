import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KpiGroup } from "./ui";

describe("KpiGroup — review item 9", () => {
  it("renders the total in a region separate from the breakdown", () => {
    render(
      <KpiGroup
        total={{ label: "Registered assets", value: 10 }}
        breakdownLabel="By equipment class"
        breakdown={[
          { label: "Rotating centrifugal pump", value: 3 },
          { label: "HE-3xx series", value: 3 },
        ]}
      />,
    );
    const total = screen.getByTestId("kpi-total");
    const breakdown = screen.getByTestId("kpi-breakdown");
    expect(total).toHaveTextContent("10");
    expect(total).toHaveTextContent("Registered assets");
    expect(total).not.toHaveTextContent("By equipment class");
    expect(breakdown).toHaveTextContent("By equipment class");
    expect(breakdown).toHaveTextContent("Rotating centrifugal pump");
  });

  it("does not render figures in monospace", () => {
    render(<KpiGroup total={{ label: "Total", value: 7 }} breakdown={[{ label: "A", value: 7 }]} />);
    expect(screen.getByTestId("kpi-total").className).not.toMatch(/font-mono/);
  });

  it("truncates long breakdown labels but keeps them on hover", () => {
    render(
      <KpiGroup
        total={{ label: "Total", value: 1 }}
        breakdown={[{ label: "A very long equipment class name indeed", value: 1 }]}
      />,
    );
    expect(screen.getByTitle("A very long equipment class name indeed")).toBeInTheDocument();
  });
});
