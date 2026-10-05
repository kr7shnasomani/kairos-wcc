import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataTable } from "./ui";

type Row = { id: string; name: string; n: number };
const rows: Row[] = [
  { id: "a", name: "Alpha", n: 2 },
  { id: "b", name: "Beta", n: 1 },
];
const keyFn = (r: Row) => r.id;

describe("DataTable — review items 7 and 10", () => {
  it("marks only the active column with aria-sort", () => {
    render(
      <DataTable
        rows={rows}
        keyFn={keyFn}
        columns={[
          { key: "name", label: "Name", sortable: true },
          { key: "n", label: "Count", sortable: true, align: "right" },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /count/i }));
    expect(screen.getByRole("columnheader", { name: /count/i })).toHaveAttribute("aria-sort", "ascending");
    expect(screen.getByRole("columnheader", { name: /name/i })).not.toHaveAttribute("aria-sort");
  });

  it("shows a directional caret only on the sorted column", () => {
    const { container } = render(
      <DataTable
        rows={rows}
        keyFn={keyFn}
        columns={[
          { key: "name", label: "Name", sortable: true },
          { key: "n", label: "Count", sortable: true },
        ]}
      />,
    );
    // Nothing sorted yet: no column may claim a direction.
    expect(container.querySelectorAll('[data-sort-dir]')).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: /count/i }));
    expect(container.querySelectorAll('[data-sort-dir]')).toHaveLength(1);
  });

  it("right-aligns an aligned column in both header and cell", () => {
    const { container } = render(
      <DataTable rows={rows} keyFn={keyFn} columns={[{ key: "n", label: "Count", align: "right" }]} />,
    );
    expect(screen.getByRole("columnheader", { name: /count/i }).className).toMatch(/text-right/);
    expect(container.querySelector("tbody td")?.className).toMatch(/text-right/);
  });

  it("gives clickable rows a pointer cursor and calls back with the row", () => {
    let clicked: Row | null = null;
    render(
      <DataTable
        rows={rows}
        keyFn={keyFn}
        onRowClick={(r) => { clicked = r; }}
        columns={[{ key: "name", label: "Name" }]}
      />,
    );
    expect(screen.getAllByRole("row")[1].className).toMatch(/cursor-pointer/);
    fireEvent.click(screen.getByText("Alpha"));
    expect(clicked).toEqual(rows[0]);
  });
});
