import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { useCountUp } from "./motion";

afterEach(cleanup);

function Probe({ target }: { target: number }) {
  return <span data-testid="v">{useCountUp(target)}</span>;
}

describe("useCountUp", () => {
  it("commits the value when the tab is hidden", async () => {
    // requestAnimationFrame is paused in a hidden tab, so animating there left every
    // KpiCard stuck on its initial value and it never corrected — the effect only re-runs
    // when `target` changes.
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    const raf = vi.spyOn(window, "requestAnimationFrame");

    const { rerender } = render(<Probe target={0} />);
    rerender(<Probe target={13} />);

    // Deferred on a timer (rAF is paused in a hidden tab, timers still fire).
    await waitFor(() => expect(screen.getByTestId("v").textContent).toBe("13"));
    expect(raf).not.toHaveBeenCalled();
  });

  it("shows the initial target on first render without animating", () => {
    render(<Probe target={42} />);
    expect(screen.getByTestId("v").textContent).toBe("42");
  });
});
