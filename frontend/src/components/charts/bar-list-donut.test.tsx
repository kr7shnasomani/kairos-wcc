import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BarList } from "./bar-list";
import { Donut } from "./donut";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children, data }: { children: React.ReactNode; data: { displayValue: string }[] }) => <div data-testid="bar-chart" data-display-values={data.map((row) => row.displayValue).join(",")}>{children}</div>,
  Bar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Cell: (props: React.ComponentProps<"div">) => <div data-testid="chart-cell" {...props} />,
  LabelList: ({ dataKey }: { dataKey: string }) => <span data-testid="bar-labels" data-key={dataKey} />,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Legend: () => null,
}));

vi.mock("@/lib/motion", () => ({ useReducedMotion: () => true }));

describe("shared chart accessibility", () => {
  it("adds an explicit value label to every ranked-bar chart", () => {
    render(<BarList data={[{ label: "ISO-45001", value: 12 }, { label: "OISD-117", value: 4 }]} valueFormat={(value) => value.toFixed(1)} showPercentage />);

    expect(screen.getByTestId("bar-labels")).toHaveAttribute("data-key", "displayValue");
    expect(screen.getByTestId("bar-chart")).toHaveAttribute("data-display-values", "12.0 (75%),4.0 (25%)");
  });

  // NOTE: recharts is mocked in this file, so these assert the props Donut PASSES,
  // not what recharts renders. That distinction matters: the previous version of
  // this test asserted role="button" plus Enter/Space activation and passed here
  // while being false in a browser -- recharts overwrites every sector with
  // tabIndex="-1", so the slice can never be tabbed to. Tabbing 120 times on
  // /compliance never reached one. Keyboard users filter via the page's severity
  // control instead, which is why the button role was removed rather than fixed.
  it("calls back when a slice is clicked", () => {
    const onSliceClick = vi.fn();
    render(<Donut data={[{ label: "Critical", value: 3 }]} onSliceClick={onSliceClick} />);

    const cell = screen.getAllByTestId("chart-cell")[0];
    expect(cell).toHaveAttribute("cursor", "pointer");
    fireEvent.click(cell);

    expect(onSliceClick).toHaveBeenCalledTimes(1);
    expect(onSliceClick).toHaveBeenCalledWith({ label: "Critical", value: 3 });
  });

  it("does not claim a button role it cannot honour", () => {
    render(<Donut data={[{ label: "Critical", value: 3 }]} onSliceClick={vi.fn()} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("dims the other slices when one is active", () => {
    render(
      <Donut data={[{ label: "Critical", value: 3 }, { label: "Major", value: 9 }]} activeLabel="critical" />,
    );

    const cells = screen.getAllByTestId("chart-cell");
    expect(cells[0].getAttribute("fillopacity") ?? cells[0].getAttribute("fill-opacity")).toBe("1");
    expect(cells[1].getAttribute("fillopacity") ?? cells[1].getAttribute("fill-opacity")).toBe("0.28");
  });

  it("leaves slices non-interactive without a handler", () => {
    render(<Donut data={[{ label: "Critical", value: 3 }]} />);

    expect(screen.getAllByTestId("chart-cell")[0]).not.toHaveAttribute("cursor");
  });
});
