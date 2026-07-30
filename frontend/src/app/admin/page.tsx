"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import Sidebar from "@/components/Sidebar";

interface WingData { name: string; used_days: number; target_days: number; clicks: number; }
interface PiState { active_wing: string | null; wings: Record<string, WingData>; reset_day: number; emergency_stop: boolean; firmware_version: string; uptime_seconds: number; cpu_temp: number; disk_free_mb: number; last_sync: string; boot_count: number; last_shutdown_reason: string; locked: boolean; pending_start: boolean; }
interface PiEvent { id: number; ts: string; level: string; msg: string; }

export default function AdminDashboard() {
  const router = useRouter();
  const [piState, setPiState] = useState<PiState | null>(null);
  const [events, setEvents] = useState<PiEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [respLabel, setRespLabel] = useState("Waiting...");
  const [respBody, setRespBody] = useState("Pi will auto-connect when firmware is running.");
  const [respOk, setRespOk] = useState(true);
  const [cmdLoading, setCmdLoading] = useState<string | null>(null);
  const [lcd1, setLcd1] = useState("");
  const [lcd2, setLcd2] = useState("");
  const [lcdTime, setLcdTime] = useState("10");
  const [eventSince, setEventSince] = useState(0);
  const eventsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (localStorage.getItem("role") !== "society_admin") { router.push("/login"); return; }
  }, [router]);

  const societyId = typeof window !== "undefined" ? (JSON.parse(localStorage.getItem("token") || "{}").society_id || "") : "";

  const fetchPiState = useCallback(async () => {
    if (!societyId) return;
    try {
      const res = await api.get("/api/admin/pi-state?society_id=" + societyId);
      if (res.data.connected) { setPiState(res.data); }
    } catch {}
  }, [societyId]);

  const fetchEvents = useCallback(async () => {
    if (!societyId) return;
    try {
      const res = await api.get("/api/admin/pi-events?society_id=" + societyId + "&since=" + eventSince);
      if (res.data.events.length > 0) {
        setEvents((prev) => [...prev, ...res.data.events]);
        setEventSince(res.data.next);
      }
    } catch {}
  }, [societyId, eventSince]);

  useEffect(() => { fetchPiState(); fetchEvents(); setLoading(false); }, [fetchPiState, fetchEvents]);
  useEffect(() => { const i = setInterval(fetchPiState, 5000); return () => clearInterval(i); }, [fetchPiState]);
  useEffect(() => { const i = setInterval(fetchEvents, 3000); return () => clearInterval(i); }, [fetchEvents]);
  useEffect(() => { if (eventsEndRef.current) { eventsEndRef.current.scrollTop = eventsEndRef.current.scrollHeight; } }, [events]);

  const sendCmd = async (command: string, wing: string = "", label: string = "") => {
    if (!societyId) return;
    setCmdLoading(command);
    setRespLabel(label || command);
    setRespBody("Queuing command...");
    setRespOk(true);
    try {
      const res = await api.post("/api/admin/pi-command", { society_id: societyId, command, wing });
      if (res.data.success) {
        setRespBody("Command queued. Pi will execute within 30s.");
        setRespOk(true);
        setTimeout(fetchPiState, 5000);
      } else {
        setRespBody("Failed: " + (res.data.message || "Unknown error"));
        setRespOk(false);
      }
    } catch (e: any) {
      setRespBody("Error: " + (e.message || "Network error"));
      setRespOk(false);
    }
    setCmdLoading(null);
  };

  const wings = piState ? Object.entries(piState.wings) : [];
  const activeWing = piState?.active_wing || null;
  const isOnline = piState && (Date.now() - new Date(piState.last_sync).getTime()) < 360000;
  const uptime = piState ? Math.floor(piState.uptime_seconds / 3600) + "h " + Math.floor((piState.uptime_seconds % 3600) / 60) + "m" : "--";

  if (loading) return <div className="flex h-screen items-center justify-center text-gray-500">Loading...</div>;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar role="society_admin" />
      <main className="flex-1 overflow-y-auto p-6" style={{ background: "#0a0e17" }}>
        {/* Status Bar */}
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-white">Pi Control</h1>
            <p className="text-xs text-gray-500">Real-time electricity management</p>
          </div>
          <div className={"flex items-center gap-2 px-4 py-2 rounded-full text-xs font-semibold " + (isOnline ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30" : "bg-red-500/15 text-red-400 border border-red-500/30")}>
            <span className={"w-2 h-2 rounded-full " + (isOnline ? "bg-emerald-400 animate-pulse" : "bg-red-400")} />
            {isOnline ? "Online" : "Offline"} {piState && "| FW " + piState.firmware_version}
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 mb-4">
          {[
            { label: "Active Wing", value: activeWing || "--", color: "text-cyan-400" },
            { label: "Total Wings", value: String(wings.length), color: "text-emerald-400" },
            { label: "Reset Day", value: piState ? piState.reset_day + "th" : "--", color: "text-amber-400" },
            { label: "CPU Temp", value: piState ? piState.cpu_temp + "\u00B0C" : "--", color: piState && piState.cpu_temp > 70 ? "text-red-400" : "text-purple-400" },
            { label: "Uptime", value: uptime, color: "text-blue-400" },
            { label: "Boots", value: piState ? String(piState.boot_count) : "--", color: "text-orange-400" },
          ].map((s) => (
            <div key={s.label} className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
              <div className="text-[9px] text-gray-500 uppercase tracking-wider">{s.label}</div>
              <div className={"text-sm font-bold mt-0.5 " + s.color}>{s.value}</div>
            </div>
          ))}
        </div>

        {/* Emergency Banner */}
        {piState?.emergency_stop && (
          <div className="bg-red-500/20 border border-red-500/50 rounded-xl p-4 mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-2xl">\u26A0\uFE0F</span>
              <div>
                <div className="text-red-400 font-bold text-sm">EMERGENCY STOP ACTIVE</div>
                <div className="text-red-400/60 text-xs">All relays are off. System locked.</div>
              </div>
            </div>
            <button onClick={() => sendCmd("restart")} disabled={cmdLoading === "restart"} className="px-4 py-2 bg-emerald-500 text-black font-bold text-xs rounded-lg disabled:opacity-40">RESTART SYSTEM</button>
          </div>
        )}

        {!piState && (
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-8 mb-4 text-center">
            <div className="text-4xl mb-3 opacity-30">\uD83D\uDCE1</div>
            <div className="text-gray-400 font-semibold mb-2">Waiting for Pi Connection</div>
            <div className="text-gray-600 text-xs max-w-md mx-auto">Make sure your Pi firmware is running and the SERVER_PUSH_URL points to: <code className="text-cyan-500">https://ems-backend-j3k5.onrender.com/api/pi/sync</code></div>
            <div className="text-gray-600 text-xs mt-2">Also set SOCIETY_ID to match your society ID in the database.</div>
          </div>
        )}

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          {/* Wing Cards */}
          <div className="bg-gray-900/80 border border-gray-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 bg-gray-800/50 flex items-center justify-between">
              <h2 className="text-xs font-semibold text-gray-300">\uD83D\uDD27 Wings</h2>
              <button onClick={fetchPiState} className="text-[10px] text-gray-500 hover:text-cyan-400">\u21BB Refresh</button>
            </div>
            <div className="p-4 space-y-2 max-h-[500px] overflow-y-auto">
              {wings.length === 0 && <div className="text-gray-600 text-xs text-center py-8">No wing data</div>}
              {wings.map(([id, w]) => {
                const isActive = activeWing === id;
                const pct = w.target_days > 0 ? Math.min(100, Math.round((w.used_days / w.target_days) * 100)) : 0;
                const barColor = pct > 80 ? "bg-red-500" : pct > 50 ? "bg-amber-500" : "bg-emerald-500";
                const textColor = pct > 80 ? "text-red-400" : pct > 50 ? "text-amber-400" : "text-emerald-400";
                return (
                  <div key={id} className={"rounded-lg p-3 border transition-all " + (isActive ? "border-emerald-500/40 bg-emerald-500/5" : "border-gray-800 bg-gray-900/50")}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xl font-black text-cyan-400 font-mono">{id}</span>
                        <span className="text-sm font-semibold text-gray-200">{w.name}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {isActive && <span className="text-[9px] px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-400 border border-cyan-500/25 font-semibold">ACTIVE</span>}
                        {pct >= 100 && <span className="text-[9px] px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/25 font-semibold">FULL</span>}
                        <span className="text-[9px] text-gray-600">{w.clicks} clicks</span>
                      </div>
                    </div>
                    <div className="flex gap-2 mb-2">
                      <button onClick={() => sendCmd("switch", id, "Switch to " + id)} disabled={cmdLoading !== null || !isOnline || piState?.emergency_stop} className="flex-1 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-black text-[10px] font-bold rounded disabled:opacity-30">SWITCH TO</button>
                      <button onClick={() => sendCmd("off_all", "", "Turn off (blocks 5m)")} disabled={cmdLoading !== null || !isOnline || !isActive || piState?.emergency_stop} className="flex-1 py-1.5 bg-red-500 hover:bg-red-600 text-white text-[10px] font-bold rounded disabled:opacity-30">TURN OFF</button>
                    </div>
                    <div className="flex justify-between text-[10px] mb-1">
                      <span className="text-gray-500">Days: {w.used_days} / {w.target_days}</span>
                      <span className={"font-bold " + textColor}>{pct}%</span>
                    </div>
                    <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div className={"h-full rounded-full transition-all duration-500 " + barColor} style={{ width: pct + "%" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Response + Controls */}
          <div className="space-y-4">
            {/* Response Viewer */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-800 bg-gray-800/50">
                <h2 className="text-xs font-semibold text-gray-300">\uD83D\uDCE1 Last Response</h2>
              </div>
              <div className="p-4">
                <div className="text-[10px] text-gray-500 mb-1">{respLabel}</div>
                <div className={"text-xs font-medium " + (respOk ? "text-gray-300" : "text-red-400")}>{respBody}</div>
              </div>
            </div>

            {/* System Controls */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-800 bg-gray-800/50">
                <h2 className="text-xs font-semibold text-gray-300">\u2699 System Controls</h2>
              </div>
              <div className="p-4 grid grid-cols-3 gap-2">
                {[
                  { label: "Force ON", cmd: "force_on", icon: "\uD83D\uDCA1", danger: false },
                  { label: "Reset Days", cmd: "reset", icon: "\uD83D\uDD04", danger: false },
                  { label: "OFF All", cmd: "off_all", icon: "\uD83D\uDDD1", danger: true },
                  { label: "E-Stop", cmd: "estop", icon: "\u26A0\uFE0F", danger: true },
                  { label: "Restart", cmd: "restart", icon: "\uD83D\uDD04", danger: false },
                  { label: "Reboot Pi", cmd: "reboot", icon: "\uD83D\uDD04", danger: true },
                ].map((b) => (
                  <button key={b.cmd} onClick={() => sendCmd(b.cmd, "", b.label)} disabled={cmdLoading !== null || !isOnline} className={"p-2 rounded-lg border text-[9px] font-semibold flex flex-col items-center gap-1 transition-all disabled:opacity-30 " + (b.danger ? "border-gray-800 text-gray-400 hover:border-red-500 hover:text-red-400 hover:bg-red-500/5" : "border-gray-800 text-gray-400 hover:border-cyan-500 hover:text-cyan-400 hover:bg-cyan-500/5")}>
                    <span className="text-base">{b.icon}</span>
                    {b.label}
                  </button>
                ))}
              </div>
            </div>

            {/* LCD Control */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-800 bg-gray-800/50">
                <h2 className="text-xs font-semibold text-gray-300">\uD83D\uDCFB LCD Display</h2>
              </div>
              <div className="p-4">
                <div className="bg-black border-2 border-gray-700 rounded-lg p-3 font-mono text-emerald-400 text-sm text-center mb-3 min-h-[44px] flex flex-col items-center justify-center" style={{ textShadow: "0 0 10px rgba(16,185,129,0.5)" }}>
                  <div>{lcd1 || "EMS READY"}</div>
                  <div>{lcd2 || ""}</div>
                </div>
                <div className="flex gap-2 mb-2">
                  <input className="flex-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-xs font-mono text-gray-200 focus:outline-none focus:border-cyan-500" placeholder="Line 1 (16ch)" maxLength={16} value={lcd1} onChange={(e) => setLcd1(e.target.value)} />
                  <input className="flex-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-xs font-mono text-gray-200 focus:outline-none focus:border-cyan-500" placeholder="Line 2 (16ch)" maxLength={16} value={lcd2} onChange={(e) => setLcd2(e.target.value)} />
                  <input type="number" className="w-14 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-xs text-center text-gray-200 focus:outline-none focus:border-cyan-500" value={lcdTime} onChange={(e) => setLcdTime(e.target.value)} min="1" max="300" />
                </div>
                <div className="flex gap-2">
                  <button onClick={() => { if (!lcd1 && !lcd2) return; sendCmd("lcd", "", "LCD: " + lcd1 + " | " + lcd2); }} disabled={cmdLoading !== null || !isOnline || (!lcd1 && !lcd2)} className="flex-1 py-1.5 bg-cyan-500 text-black text-[10px] font-bold rounded disabled:opacity-30">SEND</button>
                  <button onClick={() => { setLcd1(""); setLcd2(""); }} className="px-3 py-1.5 border border-gray-700 text-gray-500 text-[10px] rounded hover:border-red-500 hover:text-red-400">CLEAR</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Events Log */}
        <div className="bg-gray-900/80 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 bg-gray-800/50 flex items-center justify-between">
            <h2 className="text-xs font-semibold text-gray-300">\uD83D\uDCDD Pi Events</h2>
            <span className="text-[9px] text-gray-600">{events.length} events</span>
          </div>
          <div ref={eventsEndRef} className="max-h-[200px] overflow-y-auto p-2 space-y-0.5 font-mono">
            {events.length === 0 && <div className="text-gray-600 text-[10px] text-center py-4">No events yet</div>}
            {[...events].reverse().map((ev, i) => (
              <div key={ev.id + "-" + i} className={"text-[9px] px-2 py-0.5 rounded " + (ev.level === "ERROR" ? "text-red-400 bg-red-500/5" : ev.level === "WARNING" ? "text-amber-400 bg-amber-500/5" : "text-gray-500")}>
                <span className="text-gray-700">{ev.ts ? ev.ts.replace("T", " ").split(".")[0].slice(11) : "--"}</span>{" "}
                <span className="text-gray-600">[{ev.level}]</span>{" "}
                {ev.msg}
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
