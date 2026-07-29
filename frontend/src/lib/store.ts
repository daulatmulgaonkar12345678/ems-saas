export interface Society { id: string; name: string; target_host: string; target_port: number; notes: string; enabled: boolean }
export interface LogEntry { id: number; timestamp: string; method: string; url: string; action: string; detail: string; status_code: number; society: string }

let societies: Society[] = [];
let logs: LogEntry[] = [];
let activeSociety: Society | null = null;
let totalReq = 0, blocked = 0, allowed = 0;
let startTime = new Date().toISOString();

export function getSocs() { return societies; }
export function setSocs(s: Society[]) { societies = s; }
export function getActive() { return activeSociety; }
export function setActive(s: Society | null) { activeSociety = s; }
export function addLog(method: string, url: string, action: string, detail: string, sc: number) {
  logs.push({ id: logs.length, timestamp: new Date().toISOString(), method, url, action, detail, status_code: sc, society: activeSociety?.name || "None" });
  if (logs.length > 1000) logs = logs.slice(-1000);
  totalReq++; if (action === "BLOCKED") blocked++; else allowed++;
}
export function getStats() {
  const up = Math.floor((Date.now() - new Date(startTime).getTime()) / 1000);
  const h = String(Math.floor(up / 3600)).padStart(2, "0");
  const m = String(Math.floor((up % 3600) / 60)).padStart(2, "0");
  const s = String(up % 60).padStart(2, "0");
  return { total_requests: totalReq, blocked, allowed, uptime_human: `${h}:${m}:${s}`, log_count: logs.length, proxy_running: !!activeSociety, active_society: activeSociety?.name || "" };
}
export function getLogs(since: number) { return { logs: logs.slice(since), total: logs.length, next: logs.length }; }
export function clearAllLogs() { logs = []; totalReq = 0; blocked = 0; allowed = 0; startTime = new Date().toISOString(); }
