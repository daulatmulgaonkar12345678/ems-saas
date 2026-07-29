import { NextResponse } from "next/server";
import { getSocs, getActive } from "@/lib/store";

export async function GET() {
  return NextResponse.json({ societies: getSocs(), active_id: getActive()?.id || null });
}
