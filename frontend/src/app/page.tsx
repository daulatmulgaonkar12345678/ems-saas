"use client";

import { useState, useEffect, useRef } from "react";

export default function AdminDashboard() {
  const [societies, setSocieties] = useState<any[]>([]);
  const [activeSocId, setActiveSocId] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const apiKeyRef = useRef("");
  const [piData, setPiData] = useState<any>(null);
  const [formatInfo, setFormatInfo] = useState({ text: "Detecting...", color: "text-red-400" });
  const [respStatus, setRespStatus] = useState("—");
  const [respClass, setRespClass] = useState("text-slate-400");
  const [respMeta, setRespMeta] = useState("Send a command to see response");
  const [respBody, setRespBody] = useState("Click any button to send a command.");
  const [respLabel, setRespLabel] = useState("Waiting...");
  const [proxyOnline, setProxyOnline] = useState(false);
  const [stats, setStats] = useState<any>({ total_requests: 0, blocked: 0, allowed: 0, uptime_human: "00:00:00", log_count: 0, active_society: "" });
  const [allLogs, setAllLogs] = useState<any[]>([]);
  const [logFilter, setLogFilter] = useState("ALL");
  const [autoScroll, setAutoScroll] = useState(true);
  const logSinceRef = useRef(0);
  const logBoxRef = useRef<HTMLDivElement>(null);
  const [lcd1, setLcd1] = useState("");
  const [lcd2, setLcd2] = useState("");
  const [lcdTime, setLcdTime] = useState("10");
  const [calcMode, setCalcMode] = useState("units");
  const [calcTotalUnits, setCalcTotalUnits] = useState("");
  const [calcBillingDays, setCalcBillingDays] = useState("30");
  const [calcWingUnits, setCalcWingUnits] = useState<any>({});
  const [calcResultDays, setCalcResultDays] = useState<any>({});
  const [showCalcResult, setShowCalcResult] = useState(false);
  const [directDays, setDirectDays] = useState<any>({});
  const [showDaysModal, setShowDaysModal] = useState(false);
  const [resetDayInput, setResetDayInput] = useState("22");
  const [newKeyInput, setNewKeyInput] = useState("");
  const [showSocModal, setShowSocModal] = useState(false);
  const [editingSocId, setEditingSocId] = useState<string | null>(null);
  const [socForm, setSocForm] = useState({ name: "", host: "", port: "5000", notes: "" });
  const [editingWingId, setEditingWingId] = useState<string | null>(null);
  const [wingNameValue, setWingNameValue] = useState("");
  const [toast, setToast] = useState<{ msg: string; type: string } | null>(null);
  const toastTimer = useRef<any>(null);
  const sendCmdRef = useRef<any>(null);
  const piInterval = useRef<any>(null);

  const showToast = (msg: string, type: string = "") => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ msg, type });
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  };

  const getWings = (data: any) => {
    if (!data || typeof data !== "object") return [];
    return Object.entries(data)
      .filter(([key]: any) => !key.startsWith("system_") && typeof data[key] === "object")
      .map(([key, val]: any) => ({ id: key, ...val }));
  };

  const detectFormat = (data: any) => {
    if (!data) { setFormatInfo({ text: "No data", color: "text-red-400" }); return; }
    const w = getWings(data);
    if (w.length > 0) {
      const f = w[0];
      if ("display_name" in f || "disabled" in f || "relay_clicks" in f) {
        setFormatInfo({ text: "New Format (" + w.length + " wings)", color: "text-emerald-400" });
      } else {
        setFormatInfo({ text: "Old Format (" + w.length + " wings)", color: "text-amber-400" });
      }
    } else { setFormatInfo({ text: "Unknown", color: "text-red-400" }); }
  };

  const sendCommand = async (path: string, method: string = "GET") => {
    const k = apiKeyRef.current.trim();
    const fp = k ? path + (path.indexOf("?") >= 0 ? "&" : "?") + "key=" + encodeURIComponent(k) : path;
    setRespLabel(method + " " + path);
    setRespStatus("Sending..."); setRespClass("text-slate-400");
    setRespMeta("Connecting..."); setRespBody("Connecting...");
    try {
      const r = await fetch("/api/pi/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ method, path: fp }) });
      const d = await r.json();
      if (d.error) { setRespStatus("ERROR"); setRespClass("text-red-400"); setRespMeta(d.error); setRespBody("\u26A0 " + d.error); return d; }
      const c = d.http_status || 0;
      setRespClass(c < 300 ? "text-emerald-400" : c < 400 ? "text-cyan-400" : c < 500 ? "text-amber-400" : "text-red-400");
      setRespStatus(c + (c === 200 ? " OK" : c === 401 ? " Unauthorized" : c === 404 ? " Not Found" : ""));
      setRespMeta((d.size || 0) + " bytes \u2014 " + (d.time_ms || 0) + "ms");
      setRespBody(d.body || "(empty)");
      if (path.indexOf("/status") >= 0 && c === 200) { try { const p = JSON.parse(d.body); setPiData(p); detectFormat(p); } catch (ex) {} }
      return d;
    } catch (e: any) { setRespStatus("FAILED"); setRespClass("text-red-400"); setRespMeta(e.message); setRespBody("\u26A0 " + e.message); return null; }
  };
  sendCmdRef.current = sendCommand;

  const switchWing = async (id: string) => { await sendCommand("/control/switch/" + id); showToast("Switch to Wing " + id, "ok"); setTimeout(() => sendCommand("/status"), 1000); };
  const offWing = async (id: string) => { await sendCommand("/control/off/" + id); showToast("Wing " + id + " OFF", "ok"); setTimeout(() => sendCommand("/status"), 1000); };
  const toggleDisable = async (id: string) => { await sendCommand("/config/toggle_disable/" + id); showToast("Wing " + id + " toggled", "ok"); setTimeout(() => sendCommand("/status"), 1000); };
  const startRename = (id: string, name: string) => { setEditingWingId(id); setWingNameValue(name); };
  const cancelRename = () => { setEditingWingId(null); setWingNameValue(""); };
  const saveRename = async (id: string) => {
    const n = wingNameValue.trim(); if (!n) { showToast("Enter name", "er"); return; }
    await sendCommand("/config/set_display_name/" + id + "?name=" + encodeURIComponent(n));
    setEditingWingId(null); showToast('Renamed to "' + n + '"', "ok"); setTimeout(() => sendCommand("/status"), 500);
  };

  const calcUnitsFromTotal = () => {
    if (calcMode !== "units") return;
    const total = parseFloat(calcTotalUnits) || 0; const days = parseInt(calcBillingDays) || 30;
    if (total <= 0 || days <= 0) { setShowCalcResult(false); setCalcResultDays({}); return; }
    const avg = total / days; const result: any = {};
    getWings(piData).forEach((w: any) => { const u = parseFloat(calcWingUnits[w.id] || 5) || 0; result[w.id] = u > 0 ? Math.max(1, Math.floor(u / avg)) : 0; });
    setCalcResultDays(result); setShowCalcResult(true);
  };

  const applyCalc = async () => {
    if (calcMode === "units") {
      if (!Object.keys(calcResultDays).length) { showToast("Calculate first", "er"); return; }
      let p = "?total_units=" + (parseFloat(calcTotalUnits) || 0) + "&total_days=" + (parseInt(calcBillingDays) || 30);
      for (const k in calcResultDays) p += "&" + k + "=" + calcResultDays[k];
      await sendCommand("/config/set_monthly_quota" + p); showToast("Units applied", "ok");
    } else {
      if (!piData) { showToast("No Pi data", "er"); return; }
      let p = ""; getWings(piData).forEach((w: any) => { p += "&" + w.id + "=" + (directDays[w.id] || 0); });
      await sendCommand("/config/days" + p); showToast("Days updated", "ok");
    }
    setTimeout(() => sendCommand("/status"), 1000);
  };

  const sendLcd = async () => { if (!lcd1 && !lcd2) { showToast("Enter text", "er"); return; } await sendCommand("/lcd/display?l1=" + encodeURIComponent(lcd1) + "&l2=" + encodeURIComponent(lcd2) + "&t=" + (lcdTime || 10)); showToast("LCD sent", "ok"); };
  const clearLcd = async () => { setLcd1(""); setLcd2(""); await sendCommand("/lcd/display?l1=&l2=&t=1"); showToast("LCD cleared", "ok"); };
  const handleSetResetDay = async () => { await sendCommand("/config/set_reset_day?day=" + resetDayInput); showToast("Reset day set to " + resetDayInput, "ok"); };
  const handleSetNewKey = async () => { if (newKeyInput.length < 10) { showToast("Min 10 chars", "er"); return; } await sendCommand("/config/set_key?new_key=" + encodeURIComponent(newKeyInput)); showToast("API key changed", "ok"); };

  const openAddSoc = () => { setEditingSocId(null); setSocForm({ name: "", host: "", port: "5000", notes: "" }); setShowSocModal(true); };
  const openEditSoc = async (id: string) => {
    if (!id) { showToast("Select first", "er"); return; }
    try { const r = await fetch("/api/societies"); const d = await r.json(); const s = d.societies.find((x: any) => x.id === id); if (!s) return; setEditingSocId(id); setSocForm({ name: s.name, host: s.target_host, port: String(s.target_port), notes: s.notes || "" }); setShowSocModal(true); } catch (e) {}
  };
  const saveSoc = async () => {
    let h = socForm.host.trim();
    if (h.startsWith("https://")) h = h.substring(8); else if (h.startsWith("http://")) h = h.substring(7);
    h = h.replace(/\/+$/, "");
    if (!socForm.name.trim() || !h) { showToast("Name + host required", "er"); return; }
    try {
      const r = await fetch("/api/societies/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: editingSocId, name: socForm.name.trim(), target_host: h, target_port: parseInt(socForm.port) || 80, notes: socForm.notes.trim() }) });
      const d = await r.json(); if (d.status === "ok") { setShowSocModal(false); showToast(editingSocId ? "Updated" : "Added", "ok"); loadSocieties(); } else { showToast(d.message, "er"); }
    } catch (e) { showToast("Failed", "er"); }
  };
  const deleteSoc = async () => {
    const id = activeSocId; if (!id) { showToast("Select first", "er"); return; }
    if (!confirm("Delete this society?")) return;
    try { await fetch("/api/societies/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }); showToast("Deleted", "ok"); loadSocieties(); } catch (e) {}
  };
  const activateSoc = async (id: string) => {
    if (!id) return;
    try { const r = await fetch("/api/societies/activate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }); const d = await r.json(); if (d.status === "ok") { showToast("Activated: " + d.name, "ok"); loadSocieties(); sendCommand("/status"); } else { showToast(d.message, "er"); } } catch (e) {}
  };

  const openDaysModal = () => {
    if (!piData) { showToast("No Pi data", "er"); return; }
    const dd: any = {}; getWings(piData).forEach((w: any) => { dd[w.id] = w.target_days || 0; }); setDirectDays(dd); setShowDaysModal(true);
  };
  const applyDaysModal = async () => {
    let p = ""; getWings(piData).forEach((w: any) => { p += "&" + w.id + "=" + (directDays[w.id] || 0); });
    await sendCommand("/config/days" + p); setShowDaysModal(false); showToast("Days updated", "ok"); setTimeout(() => sendCommand("/status"), 1000);
  };

  const loadSocieties = async () => { try { const r = await fetch("/api/societies"); const d = await r.json(); setSocieties(d.societies || []); setActiveSocId(d.active_id || null); } catch (e) {} };
  const loadStats = async () => { try { const r = await fetch("/api/stats"); const d = await r.json(); setStats(d); setProxyOnline(d.proxy_running || false); } catch (e) {} };
  const loadLogs = async () => { try { const r = await fetch("/api/logs?since=" + logSinceRef.current); const d = await r.json(); if (d.logs && d.logs.length > 0) { setAllLogs((p: any) => [...p, ...d.logs]); logSinceRef.current = d.next; } } catch (e) {} };
  const clearLogs = async () => { try { await fetch("/api/clear-logs", { method: "POST" }); setAllLogs([]); logSinceRef.current = 0; showToast("Cleared", "ok"); } catch (e) {} };

  useEffect(() => { const s = localStorage.getItem("ak"); if (s) setApiKey(s); }, []);
  useEffect(() => { apiKeyRef.current = apiKey; if (apiKey) localStorage.setItem("ak", apiKey); }, [apiKey]);
  useEffect(() => { if (autoScroll && logBoxRef.current) logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight; }, [allLogs, logFilter, autoScroll]);

  useEffect(() => {
    loadSocieties(); loadStats(); loadLogs();
    const sI = setInterval(loadStats, 2000);
    const lI = setInterval(loadLogs, 1500);
    const cI = setInterval(loadSocieties, 10000);
    const refreshPi = async () => {
      const r = await sendCmdRef.current("/status");
      if (r && r.http_status === 200 && r.body && !r.error) {
        if (piInterval.current && piInterval.current._slow) { clearInterval(piInterval.current); piInterval.current = setInterval(refreshPi, 5000); piInterval.current._slow = false; }
      } else {
        if (piInterval.current && !piInterval.current._slow) { clearInterval(piInterval.current); piInterval.current = setInterval(refreshPi, 30000); piInterval.current._slow = true; }
      }
    };
    setTimeout(() => refreshPi(), 1500);
    piInterval.current = setInterval(refreshPi, 5000);
    return () => { clearInterval(sI); clearInterval(lI); clearInterval(cI); if (piInterval.current) clearInterval(piInterval.current); };
  }, []);

  const wings = getWings(piData);
  const activeWing = piData?.system_active_wing || "";
  const filteredLogs = allLogs.filter((l: any) => {
    if (logFilter === "ALL") return true;
    if (logFilter === "ALLOWED" || logFilter === "BLOCKED") return (l.action || "") === logFilter;
    return (l.method || "") === logFilter;
  });

  const sysButtons = [
    { label: "Status", icon: "\uD83D\uDFE2", path: "/status", danger: false, warn: false },
    { label: "Logs", icon: "\uD83D\uDCC4", path: "/logs", danger: false, warn: false },
    { label: "Force ON", icon: "\uD83D\uDCA1", path: "/control/force_on", danger: false, warn: false },
    { label: "Reset Days", icon: "\uD83D\uDD04", path: "/control/reset", danger: false, warn: true },
    { label: "OFF All", icon: "\uD83D\uDDD1", path: "/control/off_all", danger: true, warn: false },
    { label: "E-Stop", icon: "\u26A0\uFE0F", path: "/control/estop", danger: true, warn: false },
    { label: "Restart", icon: "\uD83D\uDD04", path: "/control/restart_system", danger: false, warn: true },
    { label: "Reboot Pi", icon: "\uD83D\uDD04", path: "/control/reboot_device", danger: true, warn: false },
    { label: "Set Days", icon: "\uD83D\uDCC5", path: "modal:days", danger: false, warn: false },
  ];

  return (
    <div className="min-h-screen bg-[#0a0e17] text-slate-200 relative">
      <div className="fixed inset-0 -z-10 pointer-events-none" style={{ background: "radial-gradient(ellipse at 20% 50%, rgba(6,182,212,0.06) 0%, transparent 50%), radial-gradient(ellipse at 80% 20%, rgba(139,92,246,0.04) 0%, transparent 50%)" }} />
      <div className="relative z-10 max-w-[1500px] mx-auto p-3.5">

        {/* HEADER */}
        <header className="flex items-center justify-between p-3 px-5 bg-gray-900 border border-[#1e2d4a] rounded-xl mb-3 flex-wrap gap-2.5">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 bg-gradient-to-br from-cyan-400 to-violet-500 rounded-lg flex items-center justify-center text-white font-black text-base">P</div>
            <div><h1 className="text-[15px] font-bold leading-tight">EMS Proxy Dashboard</h1><span className="text-[9px] text-slate-500 tracking-[0.1em] uppercase">v2.0.2</span></div>
          </div>
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold ${proxyOnline ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${proxyOnline ? "bg-emerald-400 animate-pulse" : "bg-red-400"}`} />
            {proxyOnline ? "Online \u2014 " + stats.active_society : "Offline"}
          </div>
        </header>

        {/* TOOLBAR */}
        <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-900 border border-[#1e2d4a] rounded-xl mb-3 flex-wrap">
          <label className="text-[10px] text-slate-500 uppercase tracking-wider">Society:</label>
          <select className="px-2.5 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-[11px] min-w-[170px] focus:outline-none focus:border-cyan-400" value={activeSocId || ""} onChange={(e) => activateSoc(e.target.value)}>
            <option value="">-- Select --</option>
            {societies.map((s: any) => (<option key={s.id} value={s.id}>{s.name} ({s.target_host}:{s.target_port})</option>))}
          </select>
          <button onClick={openAddSoc} className="px-3 py-1.5 rounded-md border border-cyan-400/50 bg-cyan-400/10 text-cyan-400 text-[10px] font-semibold cursor-pointer hover:bg-cyan-400/20 transition-colors">+ Add</button>
          <button onClick={() => openEditSoc(activeSocId || "")} className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-[10px] cursor-pointer hover:border-cyan-400/50 hover:text-cyan-400 transition-colors">Edit</button>
          <button onClick={deleteSoc} className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-[10px] cursor-pointer hover:border-red-400/50 hover:text-red-400 transition-colors">Del</button>
          <div className="flex-1" />
          <label className="text-[10px] text-slate-500 uppercase tracking-wider">API Key:</label>
          <input type="text" className="px-2.5 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-[10px] font-mono w-[220px] focus:outline-none focus:border-cyan-400 placeholder:text-slate-600" placeholder="your_api_key_here" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
          <span className="text-[9px] text-slate-500">Proxy: <strong className="text-cyan-400">127.0.0.1:8888</strong></span>
        </div>

        {/* MAIN GRID */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-3">

          {/* LEFT — Pi Control */}
          <div className="bg-gray-900 border border-[#1e2d4a] rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#1e2d4a] bg-[#1a2236]">
              <h2 className="text-xs font-semibold flex items-center gap-1.5">{"\uD83D\uDCE1"} Pi Control</h2>
              <div className="flex items-center gap-1.5">
                <span className={`text-[9px] ${formatInfo.color}`}>{formatInfo.text}</span>
                <button onClick={() => sendCommand("/status")} className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-[10px] cursor-pointer hover:border-cyan-400/50 hover:text-cyan-400 transition-colors">{"\u21BB"} Refresh</button>
              </div>
            </div>
            <div className="p-3.5 max-h-[calc(100vh-170px)] overflow-y-auto" style={{ scrollbarWidth: "thin", scrollbarColor: "#1e2d4a transparent" }}>

              {/* Wing Cards */}
              <div className="flex flex-col gap-2 mb-3.5">
                {wings.length === 0 ? (
                  <div className="py-8 text-center text-slate-500 text-xs"><div className="text-3xl mb-1.5 opacity-30">{"\uD83C\uDFD7"}</div>Waiting for Pi...</div>
                ) : wings.map((w: any) => {
                  const isA = activeWing === w.id;
                  const isO = (w.meter_toggle || "").toUpperCase() === "ON";
                  const isF = w.used_days >= w.target_days;
                  const isD = w.disabled === true;
                  const uD = w.used_days || 0; const tD = w.target_days || 0;
                  const pc = tD > 0 ? Math.min(100, Math.round((uD / tD) * 100)) : 0;
                  const barC = pc > 80 ? "bg-red-400" : pc > 50 ? "bg-amber-400" : "bg-emerald-400";
                  const txtC = pc > 80 ? "text-red-400" : pc > 50 ? "text-amber-400" : "text-emerald-400";
                  const isNew = "display_name" in w;
                  const dn = w.display_name || w.name || "Wing " + w.id;
                  const isEditing = editingWingId === w.id;
                  return (
                    <div key={w.id} className={`bg-[#1a2236] border rounded-[10px] p-3 relative overflow-hidden transition-colors ${isA ? "border-emerald-500/40" : "border-[#1e2d4a] hover:border-slate-600"} ${isD ? "opacity-50" : ""}`}>
                      <div className={`absolute top-0 left-0 bottom-0 w-1 transition-all ${isA ? "bg-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.5)]" : isD ? "bg-red-400" : "bg-slate-500"}`} />
                      <div className="flex items-center justify-between mb-2 flex-wrap gap-1.5">
                        <div className="flex items-center gap-2">
                          <span className="text-[22px] font-black text-cyan-400 font-mono min-w-[26px]">{w.id}</span>
                          <div className="flex flex-col gap-0.5">
                            {isEditing ? (
                              <div className="flex items-center gap-1">
                                <input className="px-1.5 py-0.5 rounded border border-cyan-400 bg-[#0a0e17] text-slate-200 text-[13px] w-[170px] focus:outline-none focus:shadow-[0_0_0_2px_rgba(34,211,238,0.3)]" value={wingNameValue} onChange={(e) => setWingNameValue(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") saveRename(w.id); if (e.key === "Escape") cancelRename(); }} autoFocus />
                                <button onClick={() => saveRename(w.id)} className="text-[9px] px-1.5 py-0.5 border border-[#1e2d4a] bg-gray-900 text-emerald-400 cursor-pointer hover:border-emerald-400 transition-colors">{"\u2713"} Save</button>
                              </div>
                            ) : <span className="text-sm font-bold">{dn}</span>}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-wrap">
                          {isO ? <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 font-semibold">ON</span> : <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-slate-500/15 text-slate-400 font-semibold">OFF</span>}
                          {isF && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 font-semibold">FULL</span>}
                          {isD && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 font-semibold">DISABLED</span>}
                          {isA && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-400 font-semibold">{"\u2605"} ACTIVE</span>}
                        </div>
                      </div>
                      <div className="flex gap-1.5 items-center flex-wrap mb-2">
                        <button onClick={() => switchWing(w.id)} disabled={isA && !isD} className="px-4 py-1.5 text-[11px] font-extrabold rounded-md border-none cursor-pointer transition-all bg-emerald-500 text-white hover:bg-emerald-600 hover:shadow-[0_0_12px_rgba(16,185,129,0.4)] disabled:opacity-35 disabled:cursor-not-allowed disabled:shadow-none">SWITCH TO</button>
                        <button onClick={() => offWing(w.id)} disabled={!isA || isD} className="px-4 py-1.5 text-[11px] font-extrabold rounded-md border-none cursor-pointer transition-all bg-red-500 text-white hover:bg-red-600 hover:shadow-[0_0_12px_rgba(239,68,68,0.4)] disabled:opacity-35 disabled:cursor-not-allowed disabled:shadow-none">TURN OFF</button>
                        {isNew && (<>
                          <button onClick={() => toggleDisable(w.id)} className="px-2 py-1 rounded border border-[#1e2d4a] bg-gray-900 text-slate-400 text-[9px] cursor-pointer hover:border-red-400 hover:text-red-400 transition-colors">{isD ? "\u2713 En" : "\u2717 Dis"}</button>
                          {!isEditing && <button onClick={() => startRename(w.id, dn)} className="px-2 py-1 rounded border border-[#1e2d4a] bg-gray-900 text-slate-400 text-[9px] cursor-pointer hover:border-violet-400 hover:text-violet-400 transition-colors">{"\u270E"}</button>}
                        </>)}
                      </div>
                      <div className="flex gap-3.5 flex-wrap">
                        <div><div className="text-[8px] text-slate-500 uppercase tracking-wider">Used</div><div className="text-xs font-bold text-cyan-400">{uD}d</div></div>
                        <div><div className="text-[8px] text-slate-500 uppercase tracking-wider">Target</div><div className="text-xs font-bold text-amber-400">{tD}d</div></div>
                        <div><div className="text-[8px] text-slate-500 uppercase tracking-wider">Usage</div><div className={`text-xs font-bold ${txtC}`}>{pc}%</div></div>
                        {"relay_clicks" in w && <div><div className="text-[8px] text-slate-500 uppercase tracking-wider">Clicks</div><div className="text-xs font-bold text-slate-500">{w.relay_clicks}</div></div>}
                      </div>
                      <div className="w-full h-1.5 bg-[#0a0e17] rounded-full mt-1.5 overflow-hidden"><div className={`h-full rounded-full transition-all duration-300 ${barC}`} style={{ width: pc + "%" }} /></div>
                    </div>
                  );
                })}
              </div>

              {/* Calculator */}
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 pb-1.5 border-b border-[#1e2d4a] mt-2">{"\u2699"} Unit to Days Calculator</div>
              <div className="bg-[#0a0e17] border border-[#1e2d4a] rounded-lg p-3 mb-3.5">
                <div className="flex items-center gap-2 mb-2.5 flex-wrap">
                  <span className="text-[11px] text-slate-500 min-w-[50px]">Mode:</span>
                  <select className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs min-w-[200px] cursor-pointer focus:outline-none focus:border-cyan-400" value={calcMode} onChange={(e) => { setCalcMode(e.target.value); setShowCalcResult(false); setCalcResultDays({}); }}>
                    <option value="units">{"\u26A1"} Send as: Units (Recommended)</option>
                    <option value="days">{"\uD83D\uDE04"} Send as: Direct Days</option>
                  </select>
                </div>
                {calcMode === "units" ? (<>
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span className="text-[11px] text-slate-500 min-w-[150px]">Total Monthly Units:</span>
                    <input type="number" className="px-2.5 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-[13px] font-bold w-[140px] text-center focus:outline-none focus:border-cyan-400" placeholder="e.g. 150" value={calcTotalUnits} onChange={(e) => setCalcTotalUnits(e.target.value)} />
                  </div>
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span className="text-[11px] text-slate-500 min-w-[150px]">Billing Cycle (days):</span>
                    <input type="number" className="px-2.5 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-[13px] font-bold w-[100px] text-center focus:outline-none focus:border-cyan-400" min={1} max={365} value={calcBillingDays} onChange={(e) => setCalcBillingDays(e.target.value)} />
                  </div>
                  {wings.map((w: any) => (
                    <div key={w.id} className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <span className="text-[11px] text-slate-500 min-w-[150px]">Wing {w.id} monthly units:</span>
                      <input type="number" className="px-2.5 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-[13px] font-bold w-[100px] text-center focus:outline-none focus:border-cyan-400" min={0} step={0.5} value={calcWingUnits[w.id] || 5} onChange={(e) => setCalcWingUnits((p: any) => ({ ...p, [w.id]: e.target.value }))} />
                    </div>
                  ))}
                  <button onClick={calcUnitsFromTotal} className="w-full mt-2 px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-[10px] cursor-pointer hover:border-cyan-400/50 hover:text-cyan-400 transition-colors">Calculate</button>
                </>) : (<>
                  {wings.map((w: any) => (
                    <div key={w.id} className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <span className="text-[11px] text-slate-500 min-w-[150px]">Wing {w.id} (cur: {w.target_days || 0}d):</span>
                      <input type="number" className="px-2.5 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-[13px] font-bold w-[100px] text-center focus:outline-none focus:border-cyan-400" min={0} max={365} value={(directDays[w.id] ?? w.target_days) || 0} onChange={(e) => setDirectDays((p: any) => ({ ...p, [w.id]: e.target.value }))} />
                    </div>
                  ))}
                </>)}
                {showCalcResult && calcMode === "units" && (
                  <div className="mt-2.5 p-2.5 bg-[#1a2236] border border-[#1e2d4a] rounded-lg">
                    <div className="text-[13px] font-extrabold text-amber-400 text-center my-1.5 py-1.5 bg-amber-400/10 rounded-md">Daily Average: {((parseFloat(calcTotalUnits) || 0) / (parseInt(calcBillingDays) || 30)).toFixed(2)} units/day</div>
                    {Object.entries(calcResultDays).map(([k, v]: any) => (
                      <div key={k} className="flex items-center justify-between py-0.5 text-[11px]">
                        <span className="text-slate-500">Wing {k}</span>
                        <span className="font-bold text-cyan-400 font-mono">{v} days</span>
                        <span className="text-slate-500 text-[10px] font-mono">{calcWingUnits[k] || 5} / {((parseFloat(calcTotalUnits) || 0) / (parseInt(calcBillingDays) || 30)).toFixed(2)}</span>
                      </div>
                    ))}
                    <button onClick={applyCalc} className="w-full mt-2.5 py-2 rounded-md border-none bg-gradient-to-r from-cyan-400 to-cyan-600 text-white text-xs font-bold cursor-pointer hover:shadow-[0_0_15px_rgba(34,211,238,0.3)] hover:-translate-y-px transition-all">{"\u25B2"} Apply to Pi (Monthly Quota)</button>
                  </div>
                )}
                {calcMode === "days" && (
                  <div className="mt-2.5 p-2.5 bg-[#1a2236] border border-[#1e2d4a] rounded-lg">
                    <div className="text-[13px] font-extrabold text-amber-400 text-center my-1.5 py-1.5 bg-amber-400/10 rounded-md">Direct days mode</div>
                    <button onClick={applyCalc} className="w-full mt-1 py-2 rounded-md border-none bg-gradient-to-r from-cyan-400 to-cyan-600 text-white text-xs font-bold cursor-pointer hover:shadow-[0_0_15px_rgba(34,211,238,0.3)] hover:-translate-y-px transition-all">{"\u25B6"} Apply Days to Pi</button>
                  </div>
                )}
              </div>

              {/* LCD */}
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 pb-1.5 border-b border-[#1e2d4a] mt-2">{"\uD83D\uDDA5"} LCD Display</div>
              <div className="bg-[#0d1117] border-2 border-[#1e2d4a] rounded-lg p-3 font-mono text-base text-emerald-400 min-h-[44px] mb-2 text-center tracking-[3px] whitespace-pre-wrap" style={{ textShadow: "0 0 10px rgba(16,185,129,0.5)" }}>{(lcd1 || "").padEnd(16)}{"\n"}{(lcd2 || "").padEnd(16)}</div>
              <div className="flex gap-1.5 mb-1.5">
                <input className="flex-1 px-2.5 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs font-mono focus:outline-none focus:border-cyan-400 placeholder:text-slate-600" placeholder="Line 1 (16ch)" maxLength={16} value={lcd1} onChange={(e) => setLcd1(e.target.value)} />
                <input className="flex-1 px-2.5 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs font-mono focus:outline-none focus:border-cyan-400 placeholder:text-slate-600" placeholder="Line 2 (16ch)" maxLength={16} value={lcd2} onChange={(e) => setLcd2(e.target.value)} />
                <input type="number" className="w-[50px] text-center px-2 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs font-mono focus:outline-none focus:border-cyan-400" min={1} max={300} value={lcdTime} onChange={(e) => setLcdTime(e.target.value)} />
              </div>
              <div className="flex gap-1.5 mb-3.5">
                <button onClick={sendLcd} className="px-3.5 py-1.5 rounded-md border-none bg-cyan-400 text-black text-[11px] font-bold cursor-pointer hover:bg-cyan-500 transition-colors">{"\u25B6"} Send</button>
                <button onClick={clearLcd} className="px-2.5 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-400 text-[11px] cursor-pointer hover:border-red-400 hover:text-red-400 transition-colors">Clear</button>
              </div>

              {/* System */}
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 pb-1.5 border-b border-[#1e2d4a] mt-2">{"\u2699"} System</div>
              <div className="grid grid-cols-3 gap-1.5 mb-3.5">
                {sysButtons.map((btn) => (
                  <button key={btn.label} onClick={() => btn.path === "modal:days" ? openDaysModal() : sendCommand(btn.path)} className={`py-2 px-1 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-[9px] font-semibold cursor-pointer transition-all flex flex-col items-center gap-1 hover:-translate-y-px ${btn.danger ? "hover:border-red-400/50 hover:bg-red-900/20 hover:text-red-400" : btn.warn ? "hover:border-amber-400/50 hover:bg-amber-400/10 hover:text-amber-400" : "hover:border-cyan-400/50 hover:bg-cyan-400/5 hover:text-cyan-400"}`}>
                    <span className="text-base">{btn.icon}</span>{btn.label}
                  </button>
                ))}
              </div>

              {/* Config */}
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 pb-1.5 border-b border-[#1e2d4a] mt-2">{"\u2699"} Config</div>
              <div className="flex gap-2 flex-wrap">
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-slate-500 font-semibold">Reset Day:</span>
                  <input type="number" className="w-[50px] text-center px-2 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs font-mono focus:outline-none focus:border-cyan-400" min={1} max={28} value={resetDayInput} onChange={(e) => setResetDayInput(e.target.value)} />
                  <button onClick={handleSetResetDay} className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-[10px] cursor-pointer hover:border-cyan-400/50 hover:text-cyan-400 transition-colors">Set</button>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-slate-500 font-semibold">New Key:</span>
                  <input type="text" className="w-[110px] px-2 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-[9px] font-mono focus:outline-none focus:border-cyan-400 placeholder:text-slate-600" placeholder="min 10 chars" value={newKeyInput} onChange={(e) => setNewKeyInput(e.target.value)} />
                  <button onClick={handleSetNewKey} className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-[10px] cursor-pointer hover:border-cyan-400/50 hover:text-cyan-400 transition-colors">Set</button>
                </div>
              </div>
            </div>
          </div>

          {/* RIGHT — Pi Response */}
          <div className="bg-gray-900 border border-[#1e2d4a] rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#1e2d4a] bg-[#1a2236]">
              <h2 className="text-xs font-semibold">{"\uD83D\uDCAC"} Pi Response</h2>
              <span className="text-[9px] text-slate-500">{respLabel}</span>
            </div>
            <div className="p-3.5">
              <div className={`font-bold text-sm mb-1 ${respClass}`}>{respStatus}</div>
              <div className="text-[10px] text-slate-500 mb-2">{respMeta}</div>
              <div className="bg-[#0d1117] border border-[#1e2d4a] rounded-lg p-3 max-h-[480px] overflow-auto font-mono text-[10px] leading-relaxed whitespace-pre-wrap break-all" style={{ scrollbarWidth: "thin", scrollbarColor: "#1e2d4a transparent" }}>{respBody}</div>
            </div>
          </div>
        </div>

        {/* STATS ROW */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-3">
          {[
            { label: "Total", value: stats.total_requests, color: "text-cyan-400", accent: "after:bg-cyan-400" },
            { label: "Allowed", value: stats.allowed, color: "text-emerald-400", accent: "after:bg-emerald-400" },
            { label: "Blocked", value: stats.blocked, color: "text-red-400", accent: "after:bg-red-400" },
            { label: "Uptime", value: stats.uptime_human || "00:00:00", color: "text-amber-400", accent: "after:bg-amber-400", small: true },
            { label: "Logs", value: stats.log_count, color: "text-violet-400", accent: "after:bg-violet-400" },
            { label: "Society", value: stats.active_society || "None", color: "text-orange-400", accent: "after:bg-orange-400", small: true },
          ].map((s) => (
            <div key={s.label} className={`bg-gray-900 border border-[#1e2d4a] rounded-lg p-2.5 relative overflow-hidden hover:-translate-y-px transition-transform after:content-[''] after:absolute after:top-0 after:left-0 after:right-0 after:h-0.5 ${s.accent}`}>
              <div className="text-[8px] text-slate-500 uppercase tracking-wider mb-0.5">{s.label}</div>
              <div className={`font-extrabold leading-tight ${s.color} ${s.small ? "text-[11px]" : "text-lg"}`}>{s.value}</div>
            </div>
          ))}
        </div>

        {/* LOG PANEL */}
        <div className="bg-gray-900 border border-[#1e2d4a] rounded-xl overflow-hidden mb-3">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#1e2d4a] bg-[#1a2236]">
            <h2 className="text-xs font-semibold">{"\u25B6"} Live Request Log</h2>
            <div className="flex gap-1.5">
              <button onClick={() => setAutoScroll(!autoScroll)} className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-[10px] cursor-pointer hover:border-cyan-400/50 hover:text-cyan-400 transition-colors">Auto-Scroll: {autoScroll ? "ON" : "OFF"}</button>
              <button onClick={clearLogs} className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-[10px] cursor-pointer hover:border-red-400/50 hover:text-red-400 transition-colors">Clear</button>
            </div>
          </div>
          <div className="flex gap-1 px-4 py-1.5 border-b border-[#1e2d4a] flex-wrap">
            {["ALL", "ALLOWED", "BLOCKED", "GET", "POST"].map((f) => (
              <button key={f} onClick={() => setLogFilter(f)} className={`px-2 py-0.5 rounded-full border text-[9px] cursor-pointer transition-all ${logFilter === f ? "border-cyan-400 text-cyan-400 bg-cyan-400/10" : "border-[#1e2d4a] text-slate-500 hover:border-cyan-400/50 hover:text-cyan-400"}`}>{f}</button>
            ))}
          </div>
          <div ref={logBoxRef} className="max-h-[180px] overflow-y-auto" style={{ scrollbarWidth: "thin", scrollbarColor: "#1e2d4a transparent" }}>
            {filteredLogs.length === 0 ? (
              <div className="py-6 text-center text-slate-500 text-[10px]"><div className="text-2xl mb-1 opacity-30">{"\uD83D\uDD0A"}</div>Waiting...</div>
            ) : filteredLogs.map((l: any, i: number) => {
              const t = l.timestamp ? l.timestamp.replace("T", " ").split(".")[0] : "--";
              const m = l.method || "GET"; const a = l.action || "ALLOWED";
              return (
                <div key={l.id ?? i} className="grid grid-cols-[95px_42px_1fr_58px_45px_1fr] items-center px-4 py-0.5 border-b border-[#1e2d4a]/40 text-[9px] font-mono gap-1 hover:bg-cyan-400/[0.03]">
                  <span className="text-slate-500">{t}</span>
                  <span className={`font-bold text-center uppercase text-[8px] px-1 py-px rounded ${m === "GET" ? "bg-emerald-500/15 text-emerald-400" : "bg-cyan-500/15 text-cyan-400"}`}>{m}</span>
                  <span className="text-slate-200 truncate">{l.url || "--"}</span>
                  <span className={`font-bold text-center px-1 py-px rounded text-[8px] ${a === "ALLOWED" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>{a}</span>
                  <span className="text-slate-500 text-center">{l.status_code || "-"}</span>
                  <span className="text-slate-500 truncate">{l.detail || ""}</span>
                </div>
              );
            })}
          </div>
        </div>

        <footer className="text-center py-3 text-slate-500 text-[9px]">EMS Dashboard V2.0.2</footer>
      </div>

      {/* SOCIETY MODAL */}
      {showSocModal && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center" onClick={(e) => { if (e.target === e.currentTarget) setShowSocModal(false); }}>
          <div className="bg-gray-900 border border-[#1e2d4a] rounded-2xl p-5 w-[90%] max-w-[380px]">
            <h3 className="text-[15px] font-bold mb-3.5">{editingSocId ? "Edit Society" : "Add Society"}</h3>
            <div className="mb-3"><label className="block text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Name</label><input className="w-full px-2.5 py-2 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs focus:outline-none focus:border-cyan-400 placeholder:text-slate-600" placeholder="e.g. Prestine" value={socForm.name} onChange={(e) => setSocForm({ ...socForm, name: e.target.value })} /></div>
            <div className="mb-3"><label className="block text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Host / IP</label><input className="w-full px-2.5 py-2 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs focus:outline-none focus:border-cyan-400 placeholder:text-slate-600" placeholder="e.g. 100.122.132.57" value={socForm.host} onChange={(e) => setSocForm({ ...socForm, host: e.target.value })} /><div className="text-[9px] text-cyan-400 mt-0.5">No http://</div></div>
            <div className="flex gap-2 mb-3">
              <div className="flex-1"><label className="block text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Port</label><input type="number" className="w-full px-2.5 py-2 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs focus:outline-none focus:border-cyan-400" value={socForm.port} onChange={(e) => setSocForm({ ...socForm, port: e.target.value })} /></div>
              <div className="flex-1"><label className="block text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Notes</label><input className="w-full px-2.5 py-2 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs focus:outline-none focus:border-cyan-400 placeholder:text-slate-600" placeholder="Optional" value={socForm.notes} onChange={(e) => setSocForm({ ...socForm, notes: e.target.value })} /></div>
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowSocModal(false)} className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-xs cursor-pointer hover:border-cyan-400/50 hover:text-cyan-400 transition-colors">Cancel</button>
              <button onClick={saveSoc} className="px-3 py-1.5 rounded-md border border-cyan-400/50 bg-cyan-400/10 text-cyan-400 text-xs font-semibold cursor-pointer hover:bg-cyan-400/20 transition-colors">Save</button>
            </div>
          </div>
        </div>
      )}

      {/* DAYS MODAL */}
      {showDaysModal && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center" onClick={(e) => { if (e.target === e.currentTarget) setShowDaysModal(false); }}>
          <div className="bg-gray-900 border border-[#1e2d4a] rounded-2xl p-5 w-[90%] max-w-[380px]">
            <h3 className="text-[15px] font-bold mb-3.5">{"\uD83D\uDCC5"} Set Target Days</h3>
            <div className="max-h-[300px] overflow-y-auto mb-3" style={{ scrollbarWidth: "thin", scrollbarColor: "#1e2d4a transparent" }}>
              {wings.map((w: any) => (
                <div key={w.id} className="mb-3"><label className="block text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Wing {w.id} ({w.display_name || ""})</label><input type="number" className="w-full px-2.5 py-2 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-200 text-xs focus:outline-none focus:border-cyan-400" min={0} max={365} value={directDays[w.id] ?? 0} onChange={(e) => setDirectDays((p: any) => ({ ...p, [w.id]: e.target.value }))} /></div>
              ))}
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowDaysModal(false)} className="px-3 py-1.5 rounded-md border border-[#1e2d4a] bg-[#1a2236] text-slate-300 text-xs cursor-pointer hover:border-cyan-400/50 hover:text-cyan-400 transition-colors">Cancel</button>
              <button onClick={applyDaysModal} className="px-3 py-1.5 rounded-md border border-cyan-400/50 bg-cyan-400/10 text-cyan-400 text-xs font-semibold cursor-pointer hover:bg-cyan-400/20 transition-colors">Apply</button>
            </div>
          </div>
        </div>
      )}

      {/* TOAST */}
      {toast && (
        <div className={`fixed bottom-3.5 right-3.5 px-4 py-2 rounded-lg bg-[#1a2236] border text-xs z-[999] transition-all duration-300 translate-y-0 opacity-100 ${toast.type === "ok" ? "border-emerald-400 text-emerald-400" : toast.type === "er" ? "border-red-400 text-red-400" : "border-[#1e2d4a] text-slate-200"}`}>{toast.msg}</div>
      )}
    </div>
  );
}