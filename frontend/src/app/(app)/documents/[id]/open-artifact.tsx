"use client";

import { useState } from "react";
import { getArtifactUrl } from "@/lib/api";

// The vault_url is Supabase's /object/authenticated/ endpoint — a plain <a> click
// can't send the required Authorization header (400). So fetch a short-lived signed
// URL (authenticated) and open THAT, where the token rides in the query string.
export function OpenArtifactButton({ documentId }: { documentId: string }) {
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function open() {
    setStatus("loading");
    const url = await getArtifactUrl(documentId);
    if (url) {
      setStatus("idle");
      window.open(url, "_blank", "noopener,noreferrer");
    } else {
      setStatus("error");
    }
  }

  return (
    <button
      type="button"
      onClick={open}
      disabled={status === "loading"}
      className="font-medium text-accent transition-opacity hover:underline disabled:opacity-60"
    >
      {status === "loading" ? "Opening…" : status === "error" ? "Unavailable — retry" : "Open artifact →"}
    </button>
  );
}
