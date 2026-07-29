"use client";
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/a</div>
          <div className="text-right"><p className="text-sm text-gray-500">Active Wing</p><p className="text-3xl font-bold text-cyan-400">{data?.active_wing || '-'}</p></div>
        </div>
        {loading ? <div className="text-gray-500">Connecting to device...</div> : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
            {data && Object.entries(data.wings).map(([key, wing]: any) => (
              <div key={key} className={`p-6 rounded-2xl border-2 ${getStatusStyles(wing.status)} transition-all hover:scale-[1.02]`}>
                <div className="flex justify-between items-start mb-6">
                  <div><p className="text-sm text-gray-500 uppercase tracking-wider">Wing</p><h3 className="text-4xl font-black mt-1">{key}</h3></div>
                  <span className={`text-xs font-bold px-3 py-1 rounded-full ${wing.status === 'ACTIVE' ? 'bg-green-500 text-black' : wing.status === 'FULL' ? 'bg-red-500 text-white' : 'bg-gray-700 text-gray-300'}`}>{wing.status}</span>
                </div>
                <div className="mb-2 flex justify-between text-sm"><span className="text-gray-400">Days Used</span><span className="font-bold">{wing.used_days} / {wing.target_days}</span></div>
                <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden"><div className={`h-full rounded-full transition-all ${wing.status === 'ACTIVE' ? 'bg-green-500' : wing.status === 'FULL' ? 'bg-red-500' : 'bg-gray-600'}`} style={{ width: `${(wing.used_days / wing.target_days) * 100}%` }}></div></div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
