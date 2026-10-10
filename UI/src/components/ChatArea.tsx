import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Paperclip,
  Smile,
  File,
  Download,
  CheckCheck,
  Check,
  Globe,
  Lock,
  MoreVertical,
  Phone,
  Video,
  X,
  ArrowDown
} from 'lucide-react';
import { ChatMessage, RoomInfo } from '../types';

interface ChatAreaProps {
  room: RoomInfo;
  messages: ChatMessage[];
  currentUsername: string;
  onSendMessage: (text: string) => void;
  onUploadFile: (file: File) => void;
  backendBaseUrl: string;
}

export const ChatArea: React.FC<ChatAreaProps> = ({
  room,
  messages,
  currentUsername,
  onSendMessage,
  onUploadFile,
  backendBaseUrl,
}) => {
  const [inputText, setInputText] = useState('');
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Auto scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim()) return;
    onSendMessage(inputText.trim());
    setInputText('');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onUploadFile(e.target.files[0]);
      e.target.value = '';
    }
  };

  const commonEmojis = ['😊', '😂', '👍', '❤️', '🔥', '🎉', '🚀', '🙌', '👀', '💯'];

  return (
    <div id="chat-area" className="flex-1 flex flex-col h-full bg-[#0b141a] relative overflow-hidden">
      {/* WhatsApp Header */}
      <div className="h-16 px-4 bg-[#202c33] border-b border-[#222e35] flex items-center justify-between z-10 select-none">
        <div className="flex items-center gap-3">
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm ${
              room.id === 'global'
                ? 'bg-emerald-900/70 text-emerald-300 border border-emerald-700/50'
                : room.isPrivate
                ? 'bg-amber-950/70 text-amber-300 border border-amber-800/50'
                : 'bg-[#00a884] text-white'
            }`}
          >
            {room.id === 'global' ? (
              <Globe className="w-5 h-5" />
            ) : room.isPrivate ? (
              <Lock className="w-5 h-5" />
            ) : (
              room.name.charAt(0).toUpperCase()
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-[#e9edef] leading-tight">
                {room.name}
              </h2>
              {room.isPrivate && (
                <span className="text-[10px] bg-[#111b21] text-amber-400 px-1.5 py-0.5 rounded border border-amber-800/40">
                  Private
                </span>
              )}
            </div>
            <div className="text-[11px] text-[#8696a0]">
              {room.id === 'global'
                ? 'Global public room • Everyone can see messages'
                : `Room #${room.name} • Direct real-time group`}
            </div>
          </div>
        </div>

        {/* Top actions */}
        <div className="flex items-center gap-1 text-[#aebac1]">
          <span className="text-xs bg-[#111b21] px-2.5 py-1 rounded text-[#8696a0] border border-[#2a3942] hidden sm:inline-block">
            WebSocket Active
          </span>
          <button
            title="Room details"
            className="p-2 rounded-full hover:bg-[#374248] text-[#aebac1] hover:text-[#e9edef] transition-colors"
          >
            <MoreVertical className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Messages Canvas with WhatsApp background */}
      <div
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto p-4 sm:px-8 space-y-2.5 whatsapp-bg relative"
      >
        {/* Safety notice / encryption badge */}
        <div className="flex justify-center my-2">
          <div className="bg-[#182229] border border-[#222d34] text-[#ffd279] text-[11px] px-3 py-1 rounded-lg text-center max-w-md shadow-sm">
            Messages and files in <strong>{room.name}</strong> are transmitted directly via your FastAPI WebSocket connection.
          </div>
        </div>

        {/* Chat message bubbles */}
        {messages.map((msg) => {
          const isMe = msg.sender.toLowerCase() === currentUsername.toLowerCase() || msg.isMe;
          const isSystem = msg.type === 'system' || msg.sender === 'system';

          if (isSystem) {
            return (
              <div key={msg.id} className="flex justify-center my-1.5">
                <span className="bg-[#182229] text-[#8696a0] text-[11px] px-3 py-0.5 rounded-md border border-[#222d34]">
                  {msg.text}
                </span>
              </div>
            );
          }

          return (
            <div
              key={msg.id}
              className={`flex flex-col ${isMe ? 'items-end' : 'items-start'}`}
            >
              <div
                className={`max-w-[82%] sm:max-w-[65%] rounded-lg px-3 py-2 shadow-sm text-sm relative break-words ${
                  isMe
                    ? 'bg-[#005c4b] text-[#e9edef] rounded-tr-none'
                    : 'bg-[#202c33] text-[#e9edef] rounded-tl-none'
                }`}
              >
                {/* Sender Name if not me */}
                {!isMe && (
                  <div className="text-[11px] font-bold text-[#53bdeb] mb-0.5 select-none">
                    {msg.sender}
                  </div>
                )}

                {/* File Attachment Payload if present */}
                {msg.file && (
                  <div className="mb-2 p-2.5 rounded bg-black/20 border border-white/10 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="p-2 rounded bg-[#00a884]/30 text-[#00a884]">
                        <File className="w-5 h-5" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-[#e9edef] truncate">
                          {msg.file.filename}
                        </div>
                        {msg.file.size && (
                          <div className="text-[10px] text-[#8696a0]">
                            {msg.file.size}
                          </div>
                        )}
                      </div>
                    </div>
                    <a
                      href={msg.file.url.startsWith('http') ? msg.file.url : `${backendBaseUrl}${msg.file.url}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      download={msg.file.filename}
                      className="p-1.5 rounded-full bg-[#2a3942] hover:bg-[#374248] text-[#00a884] transition-colors flex-shrink-0"
                      title="Download file"
                    >
                      <Download className="w-4 h-4" />
                    </a>
                  </div>
                )}

                {/* Text body */}
                {msg.text && (
                  <p className="whitespace-pre-wrap leading-relaxed text-[13.5px]">
                    {msg.text}
                  </p>
                )}

                {/* Time & status check */}
                <div
                  className={`flex items-center justify-end gap-1 text-[10px] mt-1 select-none ${
                    isMe ? 'text-[#8696a0]' : 'text-[#8696a0]'
                  }`}
                >
                  <span>{msg.timestamp}</span>
                  {isMe && <CheckCheck className="w-3.5 h-3.5 text-[#53bdeb]" />}
                </div>
              </div>
            </div>
          );
        })}

        <div ref={messagesEndRef} />
      </div>

      {/* Emoji Bar Picker (Quick Tray) */}
      {showEmojiPicker && (
        <div className="px-4 py-2 bg-[#202c33] border-t border-[#2a3942] flex items-center gap-2 overflow-x-auto">
          {commonEmojis.map((emoji) => (
            <button
              key={emoji}
              type="button"
              onClick={() => {
                setInputText((prev) => prev + emoji);
              }}
              className="text-lg hover:scale-125 transition-transform p-1 cursor-pointer"
            >
              {emoji}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setShowEmojiPicker(false)}
            className="text-xs text-[#8696a0] hover:text-white ml-auto"
          >
            Close
          </button>
        </div>
      )}

      {/* WhatsApp Input Bar */}
      <form
        onSubmit={handleSend}
        className="h-16 px-4 bg-[#202c33] border-t border-[#222e35] flex items-center gap-2 select-none"
      >
        {/* Emoji Button */}
        <button
          type="button"
          onClick={() => setShowEmojiPicker(!showEmojiPicker)}
          className={`p-2 rounded-full transition-colors ${
            showEmojiPicker
              ? 'text-[#00a884] bg-[#2a3942]'
              : 'text-[#8696a0] hover:text-[#e9edef]'
          }`}
          title="Emojis"
        >
          <Smile className="w-6 h-6" />
        </button>

        {/* File Attachment Input (hidden) & Button */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          className="hidden"
          id="file-upload-input"
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="p-2 text-[#8696a0] hover:text-[#e9edef] rounded-full transition-colors cursor-pointer"
          title="Attach file (HTTP upload to FastAPI)"
        >
          <Paperclip className="w-5 h-5" />
        </button>

        {/* Message Input Field */}
        <div className="flex-1">
          <input
            id="chat-input"
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Type a message..."
            className="w-full py-2.5 px-4 rounded-lg bg-[#2a3942] text-[#e9edef] placeholder-[#8696a0] text-sm focus:outline-none focus:ring-1 focus:ring-[#00a884]"
          />
        </div>

        {/* Send Button */}
        <button
          id="send-button"
          type="submit"
          disabled={!inputText.trim()}
          className={`w-10 h-10 rounded-full flex items-center justify-center transition-all cursor-pointer ${
            inputText.trim()
              ? 'bg-[#00a884] text-white hover:bg-[#02906f] shadow'
              : 'bg-[#2a3942] text-[#8696a0]'
          }`}
          title="Send message"
        >
          <Send className="w-5 h-5" />
        </button>
      </form>
    </div>
  );
};
