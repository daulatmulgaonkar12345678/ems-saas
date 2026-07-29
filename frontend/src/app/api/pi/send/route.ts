import { NextRequest, NextResponse } from "next/server";
import { getActive, addLog } from "@/lib/store";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { method, path } = body;
    const soc = getActive();
    if (!soc) return NextResponse.json({ status: "error", error: "No active society" });
    const targetUrl = `http://${soc.target_host}:${soc.target_port}${path}`;
    const t0 = Date.now();
    const resp = await fetch(targetUrl, { method: method || "GET" });
    const elapsed = Date.now() - t0;
    const text = await resp.text();
    let bodyText = text;
    try { bodyText = JSON.stringify(JSON.parse(text), null, 2); } catch {}
    addLog(method || "GET", path, resp.ok ? "ALLOWED" : "BLOCKED", `${resp.status}->${soc.target_host}:${soc.target_port}`, resp.status);
    return NextResponse.json({ status: "ok", http_status: resp.status, body: bodyText, time_ms: elapsed, size: bodyText.length });
  } catch (e: any) {
    addLog("GET", "/", "BLOCKED", "Error:" + e.message, 502);
    return NextResponse.json({ status: "error", error: e.message });
  }
}
