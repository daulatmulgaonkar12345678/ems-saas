import axios from 'axiosName="p-6 border-b border-gray-800">
        <h1 className="text-2xl font-bold text-cyan-400">⚡ EMS Cloud</h1>
        <p className="text-xs text-gray-500 mt-1 uppercase tracking-wider">{role.replace('_', ' ')}</p>
      </div>
      <nav className="flex-1 p-4 space-y-2">
        {links.map((link) => (
          <Link 
            key={link.href} 
            href={link.href}
            className={`block px-4 py-3 rounded-lg transition-colors ${
              pathname === link.href 
                ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/50' 
                : 'text-gray-400 hover:bg-gray-800 hover:text-white'
            }`}
          >
            {link.label}
          </Link>
        ))}
      </nav>
      <div className="p-4 border-t border-gray-800">
        <button 
          onClick={() => { localStorage.clear(); window.location.href = '/login'; }}
          className="w-full text-left px-4 py-3 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
        >
          Logout
        </button>
      </div>
    </aside>
  );
}
