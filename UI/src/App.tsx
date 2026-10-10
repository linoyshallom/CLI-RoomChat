import React, { useState } from 'react';
import { useChat } from './hooks/useChat';
import { LoginScreen } from './components/LoginScreen';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { SettingsModal } from './components/SettingsModal';

export default function App() {
  const {
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
    setActiveRoomId,
    createOrJoinRoom,
    sendMessage,
    uploadFile,
    updateBackendConfig,
  } = useChat();

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // If user hasn't typed their display name yet, show simple connect screen
  if (!username) {
    return (
      <LoginScreen
        onJoin={login}
        backendUrl={backendConfig.baseUrl}
        onUpdateBackendUrl={(url) =>
          updateBackendConfig({ ...backendConfig, baseUrl: url })
        }
        serverError={connectionError}
      />
    );
  }

  return (
    <div
      id="roomchat-app"
      className="w-screen h-screen flex bg-[#0c1317] overflow-hidden text-[#e9edef] font-sans antialiased"
    >
      {/* WhatsApp Sidebar with room list & user header */}
      <Sidebar
        username={username}
        rooms={rooms}
        activeRoomId={activeRoomId}
        onSelectRoom={setActiveRoomId}
        onCreateRoom={createOrJoinRoom}
        onLogout={logout}
        onOpenSettings={() => setIsSettingsOpen(true)}
        isConnected={isConnected}
      />

      {/* WhatsApp Main Chat Conversation Canvas */}
      <ChatArea
        room={activeRoom}
        messages={messages}
        currentUsername={username}
        onSendMessage={sendMessage}
        onUploadFile={uploadFile}
        backendBaseUrl={backendConfig.baseUrl}
      />

      {/* FastAPI Connection Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        config={backendConfig}
        onSaveConfig={updateBackendConfig}
        isConnected={isConnected}
      />
    </div>
  );
}
