"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import Sidebar from "@/components/Sidebar";

export default function AdminDashboard() {
  const [piData, setPiData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [responseText, setResponseText] = useState("Click a button to send a command to the device.");
  const router = useRouter();

  useEffect(() => {
    if (localStorage.getItem("role") !== "society_admin") return router.push("/login");
    const fetchInterval = setInterval(async () => {
      try { const res = await api.get("/api/admin/dashboard"); setPiData(res.data); setLoading(false); }
      catch(e) { setLoading(false); }
    }, 5000);
    return () => clearInterval(fetchInterval);
  }, []);

  const sendCommand = async (path: string) => {
    setResponseText("Sending " + path + "...");
    try {
      const res = await api.post("/api/admin/control", { path });
      setResponseText(JSON.stringify(res.data, null, 2));
    } catch (e: any) { setResponseText("Error: " + (e.message || "Failed")); }
  };

  const wings = piData ? Object.entries(piData).filter(([key]) => !key.startsWith("system_") && typeof piData[key] === "object").map(([key, val]: [string, Record<string, any>]) => ({ id: key, ...val })) : [];
  const activeWing = piData?.system_active_wing || null;

  if (loading) return <div className="flex items-center justify-center h-screen bg-gray-950 text-gray-500 text-lg">Connecting to device...</div>;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar role="society_admin" />
      <main className="flex-1 overflow-y-auto p-6 bg-gray-950">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
          <StatCard label="Active Wing" value={activeWing || "-"} color="cyan" />
          <StatCard label="Total Wings" value={wings.length.toString()} color="purple" />
          <StatCard label="Connection" value="Online" color="green" />
          <StatCard label="Switches Today" value="2" color="yellow" />
          <StatCard label="Uptime" value="7h 12m" color="blue" />
          <StatCard label="Alerts" value="0" color="orange" />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 space-y-6">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-5 flex items-center gap-2">📡 Pi Control</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {wings.map((wing) => {
                  const pct = wing.target_days > 0 ? Math.min(100, Math.round((wing.used_days / wing.target_days) * 100)) : 0;
                  const barColor = pct > 80 ? "bg-red-500" : pct > 50 ? "bg-yellow-500" : "bg-green-500";
                  const isActive = wing.id === activeWing;
                  return (
                    <div key={wing.id} className={`p-5 rounded-2xl border-2 transition-all hover:scale-[1.01] ${isActive ? "border-cyan-500/50 bg-cyan-500/5 shadow-lg shadow-cyan-500/10" : "border-gray-800/50 bg-gray-800/20"}`}>
                      <div className="flex justify-between items-start mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20"><span className="text-lg font-black text-white">{wing.id}</span></div>
                          <div>
                            <span className="text-white font-bold text-base">{wing.name}</span>
                            <div className="flex gap-2 mt-1">
                              <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${wing.meter_toggle === "ON" ? "bg-green-500/20 text-green-400" : "bg-gray-600/50 text-gray-400"}`}>{wing.meter_toggle || "OFF"}</span>
                              {isActive && <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400 flex items-center gap-1">★ ACTIVE</span>}
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 mb-3">
                        <span className="text-gray-400 text-sm">Days Used</span>
                        <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden"><div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${pct}%` }}></div></div>
                        <span className="text-sm font-bold ml-2">{wing.used_days} / {wing.target_days}d</span>
                        <span className={`ml-auto text-sm font-black ${pct > 80 ? "text-red-400" : pct > 50 ? "text-yellow-400" : "text-green-400"}`}>{pct}%</span>
                      </div>
                      <div className="flex gap-2 mt-4">
                        <button onClick={() => sendCommand("/control/switch/" + wing.id)} disabled={isActive} className="flex-1 py-2.5 bg-green-500 hover:bg-green-600 text-white text-xs font-bold rounded-xl disabled:opacity-30 transition-all shadow-lg shadow-green-500/20 hover:shadow-green-500/40">SWITCH TO</button>
                        <button onClick={() => sendCommand("/control/off/" + wing.id)} disabled={!isActive} className="flex-1 py-2.5 bg-red-500 hover:bg-red-600 text-white text-xs font-bold rounded-xl disabled:opacity-30 transition-all shadow-lg shadow-red-500/20 hover:shadow-red-500/40">TURN OFF</button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-5 flex items-center gap-2">⚙️ System Controls</h2>
              <div className="grid grid-cols-3 gap-3">
                <button onClick={() => sendCommand("/status")} className="p-3 bg-gray-800/50 hover:bg-gray-700 rounded-xl text-gray-300 text-xs font-semibold flex flex-col items-center gap-1 hover:border-cyan-500/50 hover:text-cyan-400 transition-all"><span className="text-xl">🟢</span> Status</button>
                <button onClick={() => sendCommand("/control/force_on")} className="p-3 bg-gray-800/50 hover:bg-gray-700 rounded-xl text-gray-300 text-xs font-semibold flex flex-col items-center gap-1 hover:border-cyan-500/50 hover:text-cyan-400 transition-all"><span className="text-xl">💡</span> Force ON</button>
                <button onClick={() => sendCommand("/control/reset")} className="p-3 bg-gray-800/50 hover:bg-gray-700 rounded-xl text-yellow-400 text-xs font-semibold flex flex-col items-center gap-1 hover:border-yellow-500/50 transition-all"><span className="text-xl">🔄</span> Reset Days</button>
                <button onClick={() => sendCommand("/control/off_all")} className="p-3 bg-gray-800/50 hover:bg-red-900/30 rounded-xl text-red-400 text-xs font-semibold flex flex-col items-center gap-1 transition-all"><span className="text-xl">🗑</span> OFF All</button>
                <button onClick={() => sendCommand("/control/estop")} className="p-3 bg-red-900/30 hover:bg-red-900/50 rounded-xl text-red-400 text-xs font-semibold flex flex-col items-center gap-1 transition-all"><span className="text-xl">⚠️</span> E-Stop</button>
                <button onClick={() => sendCommand("/control/reboot_device")} className="p-3 bg-gray-800/50 hover:bg-gray-700 rounded-xl text-gray-300 text-xs font-semibold flex flex-col items-center gap-1 hover:border-cyan-500/50 hover:text-cyan-400 transition-all"><span className="text-xl">🔄</span> Reboot Pi</button>
              </div>
            </div>
          </div>
          <div className="space-y-6">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-5">💬 Device Response</h2>
              <div className="bg-black/60 rounded-xl p-4 font-mono text-xs text-green-400 min-h-[250px] whitespace-pre-wrap overflow-auto border border-green-500/30">{responseText}</div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  const colors: any = { cyan: "text-cyan-400", green: "text-green-400", red: "text-red-400", yellow: "text-yellow-400", purple: "text-purple-400", blue: "text-blue-400", orange: "text-orange-400" };
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 hover:border-gray-700 transition-colors">
      <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-xl font-black ${colors[color] || "text-white"}`}>{value}</p>
    </div>
  );
}