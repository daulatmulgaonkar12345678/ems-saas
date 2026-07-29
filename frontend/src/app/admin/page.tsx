"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import Sidebar from "@/components/Sidebar";

export default function AdminDashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    if (localStorage.getItem("role") !== "society_admin") {
      router.push("/login");
      return;
    }
    api.get("/api/admin/dashboard").then((res) => {
      setData(res.data);
      setLoading(false);
    });
  }, [router]);

  const getStatusStyles = (status: string) => {
    if (status === "ACTIVE") return "border-green-500/50 bg-green-500/5";
    if (status === "FULL") return "border-red-500/50 bg-red-500/5";
    return "border-gray-800 bg-gray-900";
  };

  const getStatusColor = (status: string) => {
    if (status === "ACTIVE") return "bg-green-500 text-black";
    if (status === "FULL") return "bg-red-500 text-white";
    return "bg-gray-700 text-gray-300";
  };

  const getBarColor = (status: string) => {
    if (status === "ACTIVE") return "bg-green-500";
    if (status === "FULL") return "bg-red-500";
    return "bg-gray-600";
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar role="society_admin" />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="mb-8 flex justify-between items-end">
          <div>
            <h1 className="text-3xl font-bold">Wing Overview</h1>
            <p className="text-gray-500 mt-1">Real-time electricity quota status</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-500">Active Wing</p>
            <p className="text-3xl font-bold text-cyan-400">{data?.active_wing || "-"}</p>
          </div>
        </div>
        {loading ? (
          <div className="text-gray-500">Connecting to device...</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
            {data && Object.entries(data.wings).map(([key, wing]: any) => (
              <div
                key={key}
                className={"p-6 rounded-2xl border-2 transition-all hover:scale-[1.02] " + getStatusStyles(wing.status)}
              >
                <div className="flex justify-between items-start mb-6">
                  <div>
                    <p className="text-sm text-gray-500 uppercase tracking-wider">Wing</p>
                    <h3 className="text-4xl font-black mt-1">{key}</h3>
                  </div>
                  <span className={"text-xs font-bold px-3 py-1 rounded-full " + getStatusColor(wing.status)}>
                    {wing.status}
                  </span>
                </div>
                <div className="mb-2 flex justify-between text-sm">
                  <span className="text-gray-400">Days Used</span>
                  <span className="font-bold">{wing.used_days} / {wing.target_days}</span>
                </div>
                <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={"h-full rounded-full transition-all " + getBarColor(wing.status)}
                    style={{ width: (wing.used_days / wing.target_days) * 100 + "%" }}
                  ></div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
