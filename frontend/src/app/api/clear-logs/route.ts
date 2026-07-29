import { NextResponse } from "next/server";
import { clearAllLogs } from "@/lib/store";
export async function POST() { clearAllLogs(); return NextResponse.json({ status: "ok" }); }