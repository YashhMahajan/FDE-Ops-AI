"use client";

import { useEffect } from "react";
import { PageHead } from "@/components/ui";

/** A page that fails shows this message, not a blank screen. The other pages continue to work. */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <>
      <PageHead title="This page did not load" lede="The demo data for this page has a problem. Try again. If the problem continues, export the demo data again." />
      <p>
        <button type="button" className="button" onClick={reset}>
          Try again
        </button>
      </p>
      {error.digest && <p className="mono muted">reference {error.digest}</p>}
    </>
  );
}
