import { NextRequest, NextResponse } from "next/server";
import { getSocs, setSocs, getActive, setActive } from "@/lib/store";

export async function POST(req: NextRequest, { params }: any) {
  const action = params.action;
  const body = await req.json();
  if (action === "save") {
    const socs = getSocs();
    const { id, name, target_host, target_port, notes } = body;
    if (id) { const idx = socs.findIndex((s: any) => s.id === id); if (idx >= 0) socs[idx] = { ...socs[idx], name, target_host, target_port: parseInt(target_port) || 80, notes }; }
    else { socs.push({ id: "soc_" + Date.now(), name, target_host, target_port: parseInt(target_port) || 80, notes: notes || "", enabled: true }); }
    setSocs(socs); const cur = getActive(); if (cur && cur.id === id) setActive({ ...cur, name, target_host, target_port: parseInt(target_port) || 80, notes });
    return NextResponse.json({ status: "ok" });
  }
  if (action === "activate") { const soc = getSocs().find((s: any) => s.id === body.id); if (!soc) return NextResponse.json({ status: "error", message: "Not found" }); setActive(soc); return NextResponse.json({ status: "ok", name: soc.name }); }
  if (action === "delete") { setSocs(getSocs().filter((s: any) => s.id !== body.id)); if (getActive()?.id === body.id) setActive(null); return NextResponse.json({ status: "ok" }); }
  return NextResponse.json({ status: "error", message: "Unknown action" });
}