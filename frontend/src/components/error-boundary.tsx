"use client";

import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui";

interface ErrorBoundaryProps {
  /** Static node, or a render-prop receiving the error and a reset callback. */
  fallback?: ReactNode | ((error: Error, reset: () => void) => ReactNode);
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** Render-error containment. Default fallback is a compact card with a Retry
 *  button that resets the boundary and re-renders the children. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const { fallback } = this.props;
    if (typeof fallback === "function") return fallback(error, this.reset);
    if (fallback !== undefined) return fallback;

    return (
      <div role="alert" className="flex flex-col items-center gap-3 rounded-xl border border-line bg-surface p-5 text-center">
        <p className="text-body font-semibold text-ink">Something went wrong</p>
        <p className="text-caption text-muted">{error.message}</p>
        <Button variant="ghost" className="h-8 px-3 text-caption" onClick={this.reset}>
          Retry
        </Button>
      </div>
    );
  }
}
