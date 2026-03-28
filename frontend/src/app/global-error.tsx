"use client";

/**
 * Required for App Router: ensures the internal /_global-error route is emitted
 * consistently (helps Vercel + Next.js 16 tracing). Must include <html> and <body>.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="antialiased p-8 font-sans">
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="mt-2 text-sm opacity-80">{error.message}</p>
        <button
          type="button"
          className="mt-4 rounded border border-neutral-400 px-3 py-1.5 text-sm"
          onClick={() => reset()}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
