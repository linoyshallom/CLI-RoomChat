import React, { useState } from 'react';
import {
  MessageSquare,
  Plus,
  Lock,
  Globe,
  Search,
  LogOut,
  Settings,
  CircleDot,
  X,
  Radio
} from 'lucide-react';
import { RoomInfo } from '../types';

interface SidebarProps {
  username: string;
  rooms: RoomInfo[];
  activeRoomId: string;
  onSelectRoom: (roomId: string) => void;
  onCreateRoom: (roomName: string, isPrivate: boolean) => void;
  onLogout: () => void;
  onOpenSettings: () => void;
  isConnected: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  username,
  rooms,
  activeRoomId,
  onSelectRoom,
  onCreateRoom,
  onLogout,
  onOpenSettings,
  isConnected,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isCreatingRoom, setIsCreatingRoom] = useState(false);
  const [newRoomName, setNewRoomName] = useState('');
  const [isPrivate, setIsPrivate] = useState(false);

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRoomName.trim()) return;
    onCreateRoom(newRoomName.trim(), isPrivate);
    setNewRoomName('');
    setIsCreatingRoom(false);
  };

  const filteredRooms = rooms.filter((r) =>
    r.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <aside
      id="whatsapp-sidebar"
      className="w-full sm:w-80 md:w-96 h-full flex flex-col bg-[#111b21] border-r border-[#222e35] select-none flex-shrink-0"
    >
      {/* Top Profile & Actions Header */}
      <div className="h-16 px-4 bg-[#202c33] flex items-center justify-between border-b border-[#222e35]">
        {/* User Info */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full bg-[#00a884] text-white flex items-center justify-center font-bold text-sm shadow">
              {username.charAt(0).toUpperCase()}
            </div>
            <span
              className={`absolute bottom-0 right-0 w-3 h-3 rounded-full border-2 border-[#202c33] ${
                isConnected ? 'bg-[#00a884]' : 'bg-amber-500'
              }`}
              title={isConnected ? 'Connected to WebSocket' : 'Connecting or fallback'}
            />
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-[#e9edef] leading-tight">
              {username}
            </span>
            <span className="text-[11px] text-[#8696a0] flex items-center gap-1">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  isConnected ? 'bg-[#00a884]' : 'bg-amber-400'
                }`}
              />
              {isConnected ? 'Online' : 'Simulated/Offline'}
            </span>
          </div>
        </div>

        {/* Header Action Buttons */}
        <div className="flex items-center gap-1 text-[#aebac1]">
          <button
            id="new-room-btn"
            onClick={() => setIsCreatingRoom(true)}
            title="Join or Create Room"
            className="p-2 rounded-full hover:bg-[#374248] hover:text-[#e9edef] transition-colors"
          >
            <Plus className="w-5 h-5" />
          </button>
          <button
            id="settings-btn"
            onClick={onOpenSettings}
            title="Backend Configuration"
            className="p-2 rounded-full hover:bg-[#374248] hover:text-[#e9edef] transition-colors"
          >
            <Settings className="w-5 h-5" />
          </button>
          <button
            id="logout-btn"
            onClick={onLogout}
            title="Leave / Switch User"
            className="p-2 rounded-full hover:bg-rose-950/60 hover:text-rose-400 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* New Room Quick Form Modal/Bar */}
      {isCreatingRoom && (
        <form
          onSubmit={handleCreate}
          className="p-3 bg-[#202c33] border-b border-[#2a3942] animate-in fade-in duration-200"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-[#e9edef] flex items-center gap-1.5">
              <Plus className="w-3.5 h-3.5 text-[#00a884]" /> Join or Create Room
            </span>
            <button
              type="button"
              onClick={() => setIsCreatingRoom(false)}
              className="text-[#8696a0] hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              autoFocus
              placeholder="e.g. coffee-break, study-group"
              value={newRoomName}
              onChange={(e) => setNewRoomName(e.target.value)}
              className="flex-1 px-3 py-1.5 rounded-md bg-[#111b21] border border-[#2a3942] text-xs text-[#e9edef] focus:outline-none focus:border-[#00a884]"
            />
            <button
              type="submit"
              className="px-3 py-1.5 bg-[#00a884] hover:bg-[#02906f] text-white rounded-md text-xs font-semibold"
            >
              Join
            </button>
          </div>
          <label className="flex items-center gap-2 text-[11px] text-[#8696a0] cursor-pointer">
            <input
              type="checkbox"
              checked={isPrivate}
              onChange={(e) => setIsPrivate(e.target.checked)}
              className="rounded bg-[#111b21] border-[#2a3942] text-[#00a884] focus:ring-0"
            />
            <span>Mark as private room (lock icon)</span>
          </label>
        </form>
      )}

      {/* Search or Filter Bar */}
      <div className="px-3 py-2 border-b border-[#222e35]">
        <div className="relative flex items-center bg-[#202c33] rounded-lg px-3 py-1.5 border border-transparent focus-within:border-[#00a884]">
          <Search className="w-4 h-4 text-[#8696a0] mr-2 flex-shrink-0" />
          <input
            type="text"
            placeholder="Search or start new chat"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-transparent text-xs text-[#e9edef] placeholder-[#8696a0] focus:outline-none"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="text-[#8696a0] hover:text-[#e9edef]"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Rooms List */}
      <div className="flex-1 overflow-y-auto divide-y divide-[#222e35]/50">
        {filteredRooms.length === 0 ? (
          <div className="p-8 text-center text-[#8696a0] text-xs">
            No rooms found matching "{searchQuery}"
          </div>
        ) : (
          filteredRooms.map((room) => {
            const isActive = room.id === activeRoomId;
            return (
              <div
                key={room.id}
                id={`room-item-${room.id}`}
                onClick={() => onSelectRoom(room.id)}
                className={`flex items-center gap-3 px-3 py-3 cursor-pointer transition-colors ${
                  isActive
                    ? 'bg-[#2a3942]'
                    : 'hover:bg-[#202c33]'
                }`}
              >
                {/* Room Avatar */}
                <div
                  className={`w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 text-lg font-bold ${
                    room.id === 'global'
                      ? 'bg-emerald-900/60 text-emerald-400 border border-emerald-700/40'
                      : room.isPrivate
                      ? 'bg-amber-950/60 text-amber-400 border border-amber-800/40'
                      : 'bg-sky-950/60 text-sky-400 border border-sky-800/40'
                  }`}
                >
                  {room.id === 'global' ? (
                    <Globe className="w-6 h-6" />
                  ) : room.isPrivate ? (
                    <Lock className="w-5 h-5" />
                  ) : (
                    room.name.charAt(0).toUpperCase()
                  )}
                </div>

                {/* Info and Last Message */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-sm font-semibold text-[#e9edef] truncate">
                      {room.name}
                    </span>
                    {room.lastMessageTime && (
                      <span className="text-[11px] text-[#8696a0] ml-2 flex-shrink-0">
                        {room.lastMessageTime}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center justify-between">
                    <p className="text-xs text-[#8696a0] truncate pr-2">
                      {room.lastMessage || (room.id === 'global' ? 'Global public room' : 'Chat room ready')}
                    </p>
                    {room.unreadCount ? (
                      <span className="w-5 h-5 rounded-full bg-[#00a884] text-white text-[10px] font-bold flex items-center justify-center flex-shrink-0">
                        {room.unreadCount}
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Bottom status indicator */}
      <div className="px-4 py-2.5 bg-[#202c33] border-t border-[#222e35] flex items-center justify-between text-[11px] text-[#8696a0]">
        <div className="flex items-center gap-1.5">
          <CircleDot
            className={`w-3.5 h-3.5 ${
              isConnected ? 'text-[#00a884]' : 'text-amber-400'
            }`}
          />
          <span>{isConnected ? 'FastAPI Connected' : 'Connecting WebSocket...'}</span>
        </div>
        <span className="text-[10px] bg-[#111b21] px-2 py-0.5 rounded border border-[#2a3942]">
          Single WS & HTTP
        </span>
      </div>
    </aside>
  );
};
