"use client";
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Sidebar({ role }: { role: string }) {
  const pathname = usePathname();
  const superAdminLinks = [{ href: '/super-admin', label: 'All Societies' }];
  const adminLinks = [{ href: '/admin', label: 'Dashboard' }, { href: '/admin/meters', label: 'Meter Control' }];
  const links = role === 'super_admin' ? superAdminLinks : adminLinks;

  return (
    <aside className="w-64 h-screen bg-gray-950 border-r border-gray-800 flex flex-col">
      <div className="p-6 border-b border-gray-800">
        <h1 className="text-2xl font-bold text-cyan-400">⚡ EMS Cloud</h1>
        <p className="text-xs text-gray-500 mt-1 uppercase tracking-wider">{role.replace('_', ' ')}</p>
      </div>
      <nav className="flex-1 p-4 space-y-2">
        {links.map((link) => (
          <Link key={link.href} href={link.href} className={`block px-4 py-3 rounded-lg transition-colors ${pathname === link.href ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/50' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}>{link.label}</Link>
        ))}
      </nav>
      <div className="p-4 border-t border-gray-800">
        <button onClick={() => { localStorage.clear(); window.location.href = '/login'; }} className="w-full text-left px-4 py-3 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors">Logout</button>
      </div>
    </aside>
  );
}
