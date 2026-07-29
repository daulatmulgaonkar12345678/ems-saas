"use client";
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import Sidebar from '@/components/Sidebar';

export default function SuperAdminDashboard() {
  const [societies, setSocieties] = useState([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const role = localStorage.getItem('role');
    if (role !== 'super_admin') return router.push('/login');
    
    api.get('/api/super-admin/societies').then(res => {
      setSocieties(res.data);
      setLoading(false);
    });
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar role="super_admin" />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Society Management</h1>
          <p className="text-gray-500 mt-1">Overview of all registered societies</p>
        </div>

        {loading ? (
          <div className="text-gray-500">Loading data...</div>
        ) : (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full text-left">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="px-6 py-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Society Name</th>
                  <th className="px-6 py-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Location</th>
                  <th className="px-6 py-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Plan</th>
                  <th className="px-6 py-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {societies.map((soc: any) => (
                  <tr key={soc.name} className="hover:bg-gray-800/30 transition-colors">
                    <td className="px-6 py-4 font-medium">{soc.name}</td>
                    <td className="px-6 py-4 text-gray-400">{soc.location}</td>
                    <td className="px-6 py-4">
                      <span className="px-3 py-1 bg-blue-500/10 text-blue-400 rounded-full text-xs font-semibold">{soc.plan}</span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="flex items-center gap-2 text-green-400">
                        <span className="w-2 h-2 bg-green-400 rounded-full"></span>
                        {soc.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
