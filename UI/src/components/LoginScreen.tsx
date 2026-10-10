import React, { useState } from 'react';
import { MessageSquare, ArrowRight, Server, Shield, Sparkles } from 'lucide-react';

// Backend enforces this exact pattern (definitions.structs.UsernameData) and closes the socket
// with code 1008 on a mismatch - checking it here avoids that round trip for the common case.
const USERNAME_PATTERN = /^[a-zA-Z0-9._]+$/;

interface LoginScreenProps {
  onJoin: (username: string, initialRoom: string) => void;
  backendUrl: string;
  onUpdateBackendUrl: (url: string) => void;
  serverError?: string | null;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({
  onJoin,
  backendUrl,
  onUpdateBackendUrl,
  serverError,
}) => {
  const [username, setUsername] = useState('');
  const [roomType, setRoomType] = useState<'global' | 'private'>('global');
  const [privateRoomName, setPrivateRoomName] = useState('');
  const [showConfig, setShowConfig] = useState(false);
  const [tempBackendUrl, setTempBackendUrl] = useState(backendUrl);
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUsername = username.trim();
    if (!cleanUsername) {
      setError('Please choose a display name');
      return;
    }
    if (!USERNAME_PATTERN.test(cleanUsername)) {
      setError("Only letters, numbers, '.' and '_' are allowed");
      return;
    }
    if (roomType === 'private' && !privateRoomName.trim()) {
      setError('Enter a room name to join a private room');
      return;
    }
    const targetRoom = roomType === 'global' ? 'global' : privateRoomName.trim();
    onJoin(cleanUsername, targetRoom);
  };

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-[#111b21] p-4 font-sans select-none">
      {/* Top decorative WhatsApp band */}
      <div className="fixed top-0 left-0 right-0 h-32 bg-[#00a884] -z-0 opacity-90"></div>

      <div className="w-full max-w-md bg-[#222e35] rounded-xl shadow-2xl border border-[#2a3942] z-10 overflow-hidden">
        {/* Header banner */}
        <div className="p-6 pb-4 text-center bg-[#202c33] border-b border-[#2a3942]">
          <div className="w-16 h-16 bg-[#00a884] rounded-full mx-auto flex items-center justify-center text-white shadow-lg mb-3">
            <MessageSquare className="w-8 h-8" />
          </div>
          <h1 className="text-xl font-bold text-[#e9edef] tracking-wide">RoomChat</h1>
          <p className="text-xs text-[#8696a0] mt-1">
            Fast, real-time WebSocket chat with zero sign-up friction
          </p>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {(error || serverError) && (
            <div className="p-2.5 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs text-center">
              {error || serverError}
            </div>
          )}

          {/* Username Input */}
          <div>
            <label className="block text-xs font-semibold uppercase text-[#8696a0] tracking-wider mb-2">
              Your Display Name
            </label>
            <input
              id="username-input"
              type="text"
              autoFocus
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                if (error) setError('');
              }}
              placeholder="e.g. Alex, Linoy, Sarah"
              maxLength={25}
              className="w-full px-4 py-3 rounded-lg bg-[#111b21] border border-[#2a3942] text-[#e9edef] placeholder-[#8696a0] focus:outline-none focus:border-[#00a884] text-sm transition-all"
            />
            <div className="text-[11px] text-[#8696a0] mt-1.5 flex items-center gap-1">
              <Shield className="w-3 h-3 text-[#00a884]" /> No password needed. Pick a nickname and chat immediately!
            </div>
          </div>

          {/* Room Selection */}
          <div>
            <label className="block text-xs font-semibold uppercase text-[#8696a0] tracking-wider mb-2">
              Select Starting Room
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                id="select-global-room"
                onClick={() => setRoomType('global')}
                className={`py-2.5 px-3 rounded-lg border text-xs font-medium transition-all ${
                  roomType === 'global'
                    ? 'bg-[#00a884]/20 border-[#00a884] text-[#00a884]'
                    : 'bg-[#111b21] border-[#2a3942] text-[#8696a0] hover:text-[#e9edef]'
                }`}
              >
                🌐 Global Room
              </button>
              <button
                type="button"
                id="select-private-room"
                onClick={() => setRoomType('private')}
                className={`py-2.5 px-3 rounded-lg border text-xs font-medium transition-all ${
                  roomType === 'private'
                    ? 'bg-[#00a884]/20 border-[#00a884] text-[#00a884]'
                    : 'bg-[#111b21] border-[#2a3942] text-[#8696a0] hover:text-[#e9edef]'
                }`}
              >
                🔒 Named Room
              </button>
            </div>

            {roomType === 'private' && (
              <div className="mt-2.5">
                <input
                  id="private-room-input"
                  type="text"
                  value={privateRoomName}
                  onChange={(e) => setPrivateRoomName(e.target.value)}
                  placeholder="Room name (e.g. project-x, tea-corner)"
                  className="w-full px-3.5 py-2.5 rounded-lg bg-[#111b21] border border-[#2a3942] text-[#e9edef] placeholder-[#8696a0] focus:outline-none focus:border-[#00a884] text-xs"
                />
              </div>
            )}
          </div>

          {/* Connect Action Button */}
          <button
            id="join-chat-button"
            type="submit"
            className="w-full py-3 px-4 bg-[#00a884] hover:bg-[#02906f] active:bg-[#007a5e] text-white font-bold rounded-lg shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer text-sm"
          >
            <span>Enter RoomChat</span>
            <ArrowRight className="w-4 h-4" />
          </button>

          {/* Backend Settings Collapsible */}
          <div className="pt-2 border-t border-[#2a3942]">
            <button
              type="button"
              id="toggle-backend-settings"
              onClick={() => setShowConfig(!showConfig)}
              className="text-[11px] text-[#8696a0] hover:text-[#e9edef] flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <Server className="w-3.5 h-3.5 text-[#00a884]" />
              {showConfig ? 'Hide Backend Settings' : 'FastAPI Backend URL: ' + (backendUrl || `${window.location.origin} (same origin)`)}
            </button>

            {showConfig && (
              <div className="mt-2.5 p-3 rounded-lg bg-[#111b21] border border-[#2a3942] space-y-2">
                <div className="text-[11px] text-[#8696a0]">
                  FastAPI Server Base URL (WebSocket & HTTP file routes):
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={tempBackendUrl}
                    onChange={(e) => setTempBackendUrl(e.target.value)}
                    placeholder="http://127.0.0.1:5000"
                    className="flex-1 px-3 py-1.5 rounded bg-[#202c33] border border-[#2a3942] text-[#e9edef] text-xs focus:outline-none focus:border-[#00a884]"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      onUpdateBackendUrl(tempBackendUrl);
                      setShowConfig(false);
                    }}
                    className="px-3 py-1.5 bg-[#00a884] text-white rounded text-xs font-semibold hover:bg-[#02906f]"
                  >
                    Save
                  </button>
                </div>
                <div className="text-[10px] text-[#8696a0]">
                  Default: <code>http://127.0.0.1:5000</code>. Works seamlessly whether backend is running or in simulated preview mode!
                </div>
              </div>
            )}
          </div>
        </form>
      </div>
    </div>
  );
};
