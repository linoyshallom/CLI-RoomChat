import React, { useState } from 'react';
import { X, Server, Globe, Radio, CheckCircle2, AlertCircle, FileUp, Download } from 'lucide-react';
import { BackendConfig } from '../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: BackendConfig;
  onSaveConfig: (newConfig: BackendConfig) => void;
  isConnected: boolean;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  config,
  onSaveConfig,
  isConnected,
}) => {
  const [baseUrl, setBaseUrl] = useState(config.baseUrl);
  const [wsPath, setWsPath] = useState(config.wsPath);
  const [uploadPath, setUploadPath] = useState(config.uploadPath);
  const [downloadPath, setDownloadPath] = useState(config.downloadPath);
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
  const [testMessage, setTestMessage] = useState('');

  if (!isOpen) return null;

  const handleTest = async () => {
    setTestStatus('testing');
    setTestMessage('');

    // Try WebSocket connection test
    const rawWsUrl = baseUrl.replace(/^http/, 'ws') + wsPath;
    try {
      const ws = new WebSocket(rawWsUrl);
      const timeout = setTimeout(() => {
        ws.close();
        setTestStatus('error');
        setTestMessage(`Timeout connecting to ${rawWsUrl}. Verify FastAPI is running.`);
      }, 3000);

      ws.onopen = () => {
        clearTimeout(timeout);
        setTestStatus('success');
        setTestMessage(`Successfully connected to ${rawWsUrl}!`);
        ws.close();
      };

      ws.onerror = () => {
        clearTimeout(timeout);
        setTestStatus('error');
        setTestMessage(`Could not connect to ${rawWsUrl}. If running locally on port 5000, ensure CORS & host 0.0.0.0.`);
      };
    } catch (err: any) {
      setTestStatus('error');
      setTestMessage(err.message || 'Invalid URL');
    }
  };

  const handleSave = () => {
    onSaveConfig({
      baseUrl: baseUrl.trim() || 'http://127.0.0.1:5000',
      wsPath: wsPath.trim() || '/ws/chat',
      uploadPath: uploadPath.trim() || '/files',
      downloadPath: downloadPath.trim() || '/files',
    });
    onClose();
  };

  return (
    <div
      id="settings-modal"
      className="fixed inset-0 bg-black/75 backdrop-blur-xs z-50 flex items-center justify-center p-4 font-sans select-none"
    >
      <div className="w-full max-w-lg bg-[#222e35] rounded-xl shadow-2xl border border-[#2a3942] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-5 py-4 bg-[#202c33] border-b border-[#2a3942] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-[#00a884]/20 flex items-center justify-center text-[#00a884]">
              <Server className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#e9edef]">FastAPI Backend Connection</h3>
              <p className="text-xs text-[#8696a0]">Single host:port for WebSocket and HTTP file endpoints</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-[#8696a0] hover:text-[#e9edef] rounded-full hover:bg-[#374248]"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs">
          <div>
            <label className="block text-[#8696a0] font-semibold mb-1.5 uppercase tracking-wider text-[11px]">
              Backend Base URL
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://127.0.0.1:5000"
              className="w-full px-3 py-2 rounded-lg bg-[#111b21] border border-[#2a3942] text-[#e9edef] text-sm focus:outline-none focus:border-[#00a884]"
            />
            <p className="text-[11px] text-[#8696a0] mt-1">
              Dev default: <code>http://127.0.0.1:5000</code>. Both the single WebSocket and file routes share this URL.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[#8696a0] font-semibold mb-1 text-[11px]">
                WebSocket Path
              </label>
              <input
                type="text"
                value={wsPath}
                onChange={(e) => setWsPath(e.target.value)}
                placeholder="/ws/chat"
                className="w-full px-3 py-1.5 rounded-lg bg-[#111b21] border border-[#2a3942] text-[#e9edef] focus:outline-none focus:border-[#00a884]"
              />
            </div>
            <div>
              <label className="block text-[#8696a0] font-semibold mb-1 text-[11px]">
                File Upload / Download Path
              </label>
              <input
                type="text"
                value={uploadPath}
                onChange={(e) => {
                  setUploadPath(e.target.value);
                  setDownloadPath(e.target.value);
                }}
                placeholder="/files"
                className="w-full px-3 py-1.5 rounded-lg bg-[#111b21] border border-[#2a3942] text-[#e9edef] focus:outline-none focus:border-[#00a884]"
              />
            </div>
          </div>

          {/* Test connection */}
          <div className="pt-2 flex items-center justify-between border-t border-[#2a3942]">
            <button
              type="button"
              onClick={handleTest}
              disabled={testStatus === 'testing'}
              className="px-3 py-1.5 rounded bg-[#2a3942] hover:bg-[#374248] text-[#e9edef] font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <Radio className="w-3.5 h-3.5 text-[#00a884]" />
              {testStatus === 'testing' ? 'Testing Connection...' : 'Test WebSocket Ping'}
            </button>

            <span className="text-[11px] text-[#8696a0]">
              Status: {isConnected ? <span className="text-[#00a884] font-bold">Connected</span> : 'Standby / Ready'}
            </span>
          </div>

          {testStatus === 'success' && (
            <div className="p-2.5 rounded bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>{testMessage}</span>
            </div>
          )}

          {testStatus === 'error' && (
            <div className="p-2.5 rounded bg-amber-950/50 border border-amber-800/80 text-amber-300 text-xs flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <span>{testMessage}</span>
                <p className="mt-1 text-[11px] text-amber-400/80">
                  Note: If you are running the applet in cloud preview and your FastAPI backend is on your local machine (`127.0.0.1`), use tools like ngrok or run your backend with CORS enabled. In the meantime, the UI includes built-in live local room messaging so you can test everything right now!
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-[#202c33] border-t border-[#2a3942] flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-[#8696a0] hover:text-[#e9edef]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="px-4 py-1.5 bg-[#00a884] hover:bg-[#02906f] text-white text-xs font-semibold rounded-lg shadow transition-all"
          >
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
};
