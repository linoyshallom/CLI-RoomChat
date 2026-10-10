import { useCallback, useEffect, useRef, useState } from 'react';
import { ChatMessage, RoomInfo, BackendConfig } from '../types';

// Mirrors definitions.structs.MessageInfo.formatted_msg() on the server - the single source
// of formatting for every line that reaches this socket.
const CHAT_LINE = /^\[(?<timestamp>[^\]]+)\] \[(?<sender>[^\]]+)\]: (?<body>[\s\S]*)$/;
const SYSTEM_LINE = /^\[SYSTEM\]: (?<body>[\s\S]*)$/;
// Mirrors server.app._generate_file_id(): f"file_id-{uuid4()}-{basename(filename)}"
const FILE_ID_LINE = /^(file_id-[0-9a-fA-F-]{36}-(.+))$/;

const DEFAULT_GLOBAL_ROOM: RoomInfo = { id: 'GLOBAL', name: 'Global Room', isPrivate: false };

type PendingJoin = { roomType: 'GLOBAL' } | { roomType: 'PRIVATE'; groupName: string };

function sendJoinFrame(socket: WebSocket, pending: PendingJoin) {
  const frame: Record<string, string> = { action: 'join', room_type: pending.roomType };
  if (pending.roomType === 'PRIVATE') frame.group_name = pending.groupName;
  socket.send(JSON.stringify(frame));
}

function resolveHttpBase(baseUrl: string): string {
  return baseUrl || window.location.origin;
}

export function useChat() {
  const [username, setUsername] = useState<string>(() => {
    return localStorage.getItem('roomchat_username') || '';
  });

  const [rooms, setRooms] = useState<RoomInfo[]>([DEFAULT_GLOBAL_ROOM]);
  const [activeRoomId, setActiveRoomIdState] = useState<string>('GLOBAL');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Backend config: baseUrl empty means "same origin as this page" - correct by default once
  // FastAPI is serving this built UI itself. VITE_BACKEND_URL only matters for `npm run dev`,
  // where the UI dev server and the FastAPI backend run on two different ports.
  const [backendConfig, setBackendConfig] = useState<BackendConfig>(() => {
    const saved = localStorage.getItem('roomchat_backend_config');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        // fall through to defaults
      }
    }
    return {
      baseUrl: (import.meta as any).env?.VITE_BACKEND_URL || '',
      wsPath: '/ws/chat',
      uploadPath: '/files',
      downloadPath: '/files',
    };
  });

  const wsRef = useRef<WebSocket | null>(null);
  const pendingJoinRef = useRef<PendingJoin | null>(null);
  const usernameRef = useRef(username);
  const activeRoomIdRef = useRef(activeRoomId);
  const lastSystemTextRef = useRef<string>('');

  useEffect(() => { usernameRef.current = username; }, [username]);
  useEffect(() => { activeRoomIdRef.current = activeRoomId; }, [activeRoomId]);

  const updateBackendConfig = (newConfig: BackendConfig) => {
    setBackendConfig(newConfig);
    localStorage.setItem('roomchat_backend_config', JSON.stringify(newConfig));
  };

  const appendMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
    setRooms((prev) =>
      prev.map((r) =>
        r.id === activeRoomIdRef.current
          ? { ...r, lastMessage: msg.file ? `📎 ${msg.file.filename}` : msg.text, lastMessageTime: msg.timestamp }
          : r
      )
    );
  }, []);

  // Applies a join locally (clears history, switches the active room, remembers it for the
  // socket's next open/reopen) - the server does the matching thing on its side once the
  // corresponding wire frame reaches it.
  const applyJoin = useCallback((pending: PendingJoin) => {
    pendingJoinRef.current = pending;
    const roomId = pending.roomType === 'GLOBAL' ? 'GLOBAL' : pending.groupName;
    // Set synchronously (not just via state) so history frames that arrive before React's
    // effect-driven ref sync runs still get tagged against the room just joined, not the old one.
    activeRoomIdRef.current = roomId;
    setMessages([]);
    setActiveRoomIdState(roomId);
    setRooms((prev) =>
      prev.some((r) => r.id === roomId)
        ? prev
        : [
            ...prev,
            {
              id: roomId,
              name: pending.roomType === 'GLOBAL' ? 'Global Room' : pending.groupName,
              isPrivate: pending.roomType === 'PRIVATE',
            },
          ]
    );
  }, []);

  // Login handler - just records the desired starting room and sets the username; the
  // WebSocket effect below (keyed on `username`) opens the connection and sends the join.
  const login = (chosenName: string, initialRoomId: string) => {
    const trimmedName = chosenName.trim();
    const isGlobal = !initialRoomId || initialRoomId.trim().toLowerCase() === 'global';
    pendingJoinRef.current = isGlobal
      ? { roomType: 'GLOBAL' }
      : { roomType: 'PRIVATE', groupName: initialRoomId.trim() };

    setConnectionError(null);
    setUsername(trimmedName);
    localStorage.setItem('roomchat_username', trimmedName);
  };

  const logout = () => {
    wsRef.current?.close();
    wsRef.current = null;
    pendingJoinRef.current = null;
    setUsername('');
    localStorage.removeItem('roomchat_username');
    setMessages([]);
    setRooms([DEFAULT_GLOBAL_ROOM]);
    setActiveRoomIdState('GLOBAL');
    setConnectionError(null);
  };

  // Leaves the current room ('switch') and immediately requests the new one ('join') on the
  // same socket - this is exactly the two-frame sequence the backend's state machine expects.
  const switchRoom = useCallback(
    (roomType: 'GLOBAL' | 'PRIVATE', groupName?: string) => {
      const socket = wsRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) return;

      const pending: PendingJoin =
        roomType === 'GLOBAL' ? { roomType: 'GLOBAL' } : { roomType: 'PRIVATE', groupName: (groupName || '').trim() };
      if (pending.roomType === 'PRIVATE' && !pending.groupName) return;

      socket.send(JSON.stringify({ action: 'switch' }));
      sendJoinFrame(socket, pending);
      applyJoin(pending);
    },
    [applyJoin]
  );

  // Sidebar's room picker only ever knows a free-typed name - the backend has no concept of
  // a "public named room", only the single fixed GLOBAL room and arbitrary PRIVATE rooms.
  const createOrJoinRoom = useCallback(
    (roomName: string) => {
      const trimmed = roomName.trim();
      if (!trimmed) return;
      if (trimmed.toLowerCase() === 'global') switchRoom('GLOBAL');
      else switchRoom('PRIVATE', trimmed);
    },
    [switchRoom]
  );

  // Clicking an already-known room in the sidebar re-runs the same switch/join exchange.
  const selectRoom = useCallback(
    (roomId: string) => {
      if (roomId === activeRoomIdRef.current) return;
      const target = rooms.find((r) => r.id === roomId);
      if (!target) return;
      if (target.id === 'GLOBAL') switchRoom('GLOBAL');
      else switchRoom('PRIVATE', target.id);
    },
    [rooms, switchRoom]
  );

  const sendMessage = useCallback((text: string) => {
    const socket = wsRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !text.trim()) return;
    socket.send(JSON.stringify({ action: 'message', text }));
    // No local echo: the server broadcasts a sent message back to its own sender too.
  }, []);

  // Upload via plain HTTP POST, then send the returned file_id as an ordinary chat message -
  // that's the only thing that makes a file visible to anyone else in the room (server has no
  // separate "file message" concept).
  const uploadFile = useCallback(
    async (file: File) => {
      const uploadUrl = `${resolveHttpBase(backendConfig.baseUrl)}${backendConfig.uploadPath}`;
      const formData = new FormData();
      formData.append('file', file);

      try {
        const response = await fetch(uploadUrl, { method: 'POST', body: formData });
        if (!response.ok) {
          const text = response.status === 413 ? 'Upload failed: file exceeds the 16 MB limit.' : 'Upload failed.';
          appendMessage({
            id: `sys-${Date.now()}`,
            room: activeRoomIdRef.current,
            sender: 'System',
            text,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            type: 'system',
          });
          return;
        }
        const data: { file_id: string } = await response.json();
        sendMessage(data.file_id);
      } catch {
        appendMessage({
          id: `sys-${Date.now()}`,
          room: activeRoomIdRef.current,
          sender: 'System',
          text: 'Could not reach the backend to upload the file.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          type: 'system',
        });
      }
    },
    [backendConfig.baseUrl, backendConfig.uploadPath, sendMessage, appendMessage]
  );

  // Owns the single WebSocket for the session. Re-runs (closing any previous socket first) when
  // the username or backend location changes - never on room switches, which reuse the socket.
  useEffect(() => {
    if (!username) {
      wsRef.current?.close();
      wsRef.current = null;
      return;
    }

    const httpBase = resolveHttpBase(backendConfig.baseUrl);
    const wsBase = httpBase.replace(/^http/, 'ws').replace(/\/$/, '');
    const wsUrl = `${wsBase}${backendConfig.wsPath}?username=${encodeURIComponent(username)}`;

    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onopen = () => {
      setIsConnected(true);
      setConnectionError(null);
      const pending = pendingJoinRef.current ?? { roomType: 'GLOBAL' as const };
      applyJoin(pending);
      sendJoinFrame(socket, pending);
    };

    socket.onmessage = (event) => {
      let frame: { type?: string; text?: string };
      try {
        frame = JSON.parse(event.data);
      } catch {
        return;
      }
      const rawText = frame.text ?? '';
      const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      if (frame.type === 'SYSTEM') {
        const body = rawText.match(SYSTEM_LINE)?.groups?.body ?? rawText;
        lastSystemTextRef.current = body;
        appendMessage({
          id: `sys-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          room: activeRoomIdRef.current,
          sender: 'System',
          text: body,
          timestamp: now,
          type: 'system',
        });
        return;
      }

      // CHAT - either pre-formatted "[ts] [sender]: body", or (defensively) raw text.
      const match = rawText.match(CHAT_LINE);
      const sender = match?.groups?.sender ?? 'Unknown';
      const body = match?.groups?.body ?? rawText;
      const timestamp = match?.groups?.timestamp ?? now;
      const isMe = sender.toLowerCase() === usernameRef.current.toLowerCase();

      const fileMatch = body.match(FILE_ID_LINE);
      const base: ChatMessage = {
        id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        room: activeRoomIdRef.current,
        sender,
        timestamp,
        isMe,
        type: fileMatch ? 'file' : 'text',
      };

      if (fileMatch) {
        base.file = { filename: fileMatch[2], url: `${backendConfig.downloadPath}/${fileMatch[1]}` };
      } else {
        base.text = body;
      }

      appendMessage(base);
    };

    socket.onclose = (event) => {
      setIsConnected(false);
      // 1008 is the server's "connection rejected" close code: an invalid username at connect
      // time, or a malformed frame later. Either way there's no session to resume - go back
      // to the username screen and surface the SYSTEM text the server sent just before closing.
      if (event.code === 1008) {
        setConnectionError(lastSystemTextRef.current || 'Connection rejected by the server.');
        pendingJoinRef.current = null;
        setUsername('');
        localStorage.removeItem('roomchat_username');
      }
    };

    socket.onerror = () => {
      setIsConnected(false);
    };

    return () => {
      socket.close();
      if (wsRef.current === socket) wsRef.current = null;
    };
  }, [username, backendConfig.baseUrl, backendConfig.wsPath, applyJoin, appendMessage]);

  const activeRoom = rooms.find((r) => r.id === activeRoomId) || {
    id: activeRoomId,
    name: activeRoomId,
    isPrivate: false,
  };

  return {
    username,
    rooms,
    activeRoom,
    activeRoomId,
    messages,
    isConnected,
    connectionError,
    backendConfig,
    login,
    logout,
    setActiveRoomId: selectRoom,
    createOrJoinRoom,
    sendMessage,
    uploadFile,
    updateBackendConfig,
  };
}
