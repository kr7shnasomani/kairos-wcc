import { notFound } from "next/navigation";
import { getBrief } from "@/lib/api";
import { BriefDetail } from "@/components/brief-detail";

export default async function BriefPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { data: brief } = await getBrief(id);
  if (!brief) notFound();
  return <BriefDetail brief={brief} />;
}
