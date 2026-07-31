"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Sidebar({ role }: { role: string }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  const superAdminLinks = [{ href: "/super-admin", label: "All Societies" }];
  const adminLinks = [{ href: "/admin", label: "Pi Control" }];
  const links = role === "super_admin" ? superAdminLinks : adminLinks;

  const navContent = (
    <>
      <div className="p-6 border-b border-gray-800">
        <h1 className="text-2xl font-bold text-cyan-400">EMS Cloud</h1>
        <p className="text-xs text-gray-500 mt-1 uppercase tracking-wider">{role.replace("_", " ")}</p>
      </div>
      <nav className="flex-1 p-4 space-y-2">
        {links.map((link) => (
          <Link key={link.href} href={link.href} className={pathname === link.href ? "block px-4 py-3 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/50" : "block px-4 py-3 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-white"}>{link.label}</Link>
        ))}
      </nav>
      <div className="p-4 border-t border-gray-800">
        <button onClick={() => { localStorage.clear(); window.location.href = "/login"; }} className="w-full text-left px-4 py-3 text-red-400 hover:bg-red-500/10 rounded-lg">Logout</button>
      </div>
    </>
  );

  return (
    <>
      <div className="fixed top-0 left-0 right-0 z-40 h-14 bg-gray-950 border-b border-gray-800 flex items-center px-4 gap-3">
        <button onClick={() => setOpen(true)} className="p-2 -ml-2 text-gray-400 hover:text-white">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <h1 className="text-lg font-bold text-cyan-400">EMS Cloud</h1>
      </div>
      {open && <div className="md:hidden fixed inset-0 bg-black/60 z-40" onClick={() => setOpen(false)} />}
      <aside className={"fixed inset-y-0 left-0 z-50 w-64 bg-gray-950 border-r border-gray-800 flex flex-col transform transition-transform duration-200 ease-in-out  " + (open ? "translate-x-0" : "-translate-x-full")}>
        {navContent}
      </aside>
    </>
  );
}