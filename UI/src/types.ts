export interface ChatMessage {
  id: string;
  room: string;
  sender: string;
  text?: string;
  timestamp: string; // ISO or formatted HH:MM
  isMe?: boolean;
  type?: 'text' | 'file' | 'system';
  file?: {
    filename: string;
    url: string;
    size?: string;
    contentType?: string;
  };
}

export interface RoomInfo {
  id: string; // e.g. "global", "room-123"
  name: string;
  isPrivate: boolean;
  unreadCount?: number;
  lastMessage?: string;
  lastMessageTime?: string;
}

export interface BackendConfig {
  baseUrl: string; // e.g. "http://127.0.0.1:5000"
  wsPath: string; // e.g. "/ws"
  uploadPath: string; // e.g. "/files" or "/upload"
  downloadPath: string; // e.g. "/files"
}
