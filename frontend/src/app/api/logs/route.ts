import { NextRequest, NextResponse } from "next/server";
import { getLogs } from "@/lib/store";
export async function GET(req: NextRequest) { return NextResponse.json(getLogs(parseInt(req.nextUrl.searchParams.get("since") || "0"))); }