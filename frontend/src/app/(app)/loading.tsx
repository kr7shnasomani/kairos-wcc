import { PageSkeleton } from "@/components/skeleton";

// Shown while any (app) route segment fetches on navigation. Server pages suspend here;
// client pages render their own in-component state.
export default function Loading() {
  return <PageSkeleton />;
}
