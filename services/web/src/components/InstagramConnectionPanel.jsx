import { useState, useEffect } from "react";
import {
  getInstagramConnectionStatus,
  postInstagramConnectStart,
  getInstagramConnectionCallback,
} from "../api";

/**
 * InstagramConnectionPanel.jsx
 *
 * Displays Instagram OAuth connection status and provides Connect / Reconnect flow.
 * Mirrors LinkedInConnectionPanel.jsx.
 *
 * Props:
 *   workspaceSlug  — workspace to check / connect
 *   onConnected    — optional callback() when connection succeeds
 */
export default function InstagramConnectionPanel({ workspaceSlug = "default", onConnected }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await getInstagramConnectionStatus(workspaceSlug);
      setStatus(data);
    } catch (e) {
      setError(e.message || "Failed to check Instagram status");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [workspaceSlug]);

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const data = await postInstagramConnectStart(workspaceSlug);
      // In a real browser environment, redirect to the authorization_url.
      // In demo / no-browser context, show the URL for manual navigation.
      if (data.authorization_url && data.client_configured) {
        window.location.href = data.authorization_url;
      } else {
        // Demo simulation: call callback directly
        await getInstagramConnectionCallback("demo-code", data.state, workspaceSlug);
        await load();
        onConnected?.();
      }
    } catch (e) {
      setError(e.message || "OAuth start failed");
    } finally {
      setConnecting(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-3" />
        <div className="h-3 bg-gray-800 rounded w-1/2" />
      </div>
    );
  }

  const connected = status?.connected;
  const expiresAt = status?.expires_at;

  return (
    <div className={`bg-gray-900 border rounded-lg p-5 ${
      connected ? "border-green-800" : "border-gray-800"
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          {/* Instagram icon placeholder */}
          <div className="w-8 h-8 bg-gradient-to-br from-pink-600 to-purple-600 rounded flex items-center justify-center text-white text-xs font-bold">
            ig
          </div>
          <div>
            <p className="text-white font-semibold text-sm">Instagram</p>
            <p className="text-gray-500 text-xs">Content distribution channel</p>
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase border ${
          connected
            ? "bg-green-900 text-green-300 border-green-700"
            : "bg-gray-800 text-gray-400 border-gray-700"
        }`}>
          {connected ? "Connected" : "Not Connected"}
        </span>
      </div>

      {error && (
        <div className="bg-red-950 border border-red-800 rounded p-2 mb-3 text-red-300 text-xs">
          {error}
        </div>
      )}

      {/* Details */}
      {connected && (
        <div className="mb-3 text-xs text-gray-400 space-y-0.5">
          {status.connected_by && <p>Connected by: <span className="text-gray-300">{status.connected_by}</span></p>}
          {expiresAt && <p>Token expires: <span className="text-gray-300">{new Date(expiresAt).toLocaleDateString()}</span></p>}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={handleConnect}
          disabled={connecting}
          className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
            connecting
              ? "bg-gray-700 text-gray-500 cursor-not-allowed"
              : connected
                ? "bg-gray-800 hover:bg-gray-700 text-gray-300"
                : "bg-pink-700 hover:bg-pink-600 text-white"
          }`}
        >
          {connecting ? "Connecting…" : connected ? "Reconnect" : "Connect Instagram"}
        </button>
        <button
          onClick={load}
          className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded text-sm"
        >
          ↺
        </button>
      </div>
    </div>
  );
}
