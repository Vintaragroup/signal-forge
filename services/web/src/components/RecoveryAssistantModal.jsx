import { useState } from "react";
import { getSystemRecoveryStatus, postWorkersRecoverOrphaned } from "../api";

/**
 * RecoveryAssistantModal.jsx
 *
 * Guided recovery modal that detects system issues and walks operators
 * through remediation steps with one-click actions.
 *
 * Props:
 *   isOpen   — boolean
 *   onClose  — () => void
 */
export default function RecoveryAssistantModal({ isOpen, onClose }) {
  const [step, setStep] = useState("scan"); // scan | results | recovering | done
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [recoveryResult, setRecoveryResult] = useState(null);

  async function scan() {
    setStep("scan");
    setError(null);
    try {
      const data = await getSystemRecoveryStatus();
      setStatus(data);
      setStep("results");
    } catch (e) {
      setError(e.message || "Scan failed");
      setStep("results");
    }
  }

  async function recover() {
    setStep("recovering");
    try {
      const result = await postWorkersRecoverOrphaned();
      setRecoveryResult(result);
      setStep("done");
    } catch (e) {
      setError(e.message || "Recovery failed");
      setStep("results");
    }
  }

  function reset() {
    setStep("scan");
    setStatus(null);
    setError(null);
    setRecoveryResult(null);
  }

  if (!isOpen) return null;

  const stuckCount = status?.stuck_count || 0;
  const workerRisk = status?.orphaned_task_risk;
  const staleWorkers = status?.worker_health?.stale || 0;
  const hasIssues = stuckCount > 0 || workerRisk || staleWorkers > 0;

  return (
    <>
      <div className="fixed inset-0 bg-black/60 z-40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-gray-950 border border-gray-800 rounded-xl shadow-2xl w-full max-w-lg">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
            <div className="flex items-center gap-2">
              <span className="text-lg">🔧</span>
              <h2 className="text-white font-semibold text-sm">Recovery Assistant</h2>
            </div>
            <button onClick={onClose} className="text-gray-500 hover:text-white text-xl">×</button>
          </div>

          {/* Body */}
          <div className="px-6 py-5">
            {/* Initial scan prompt */}
            {step === "scan" && (
              <div className="text-center py-4">
                <p className="text-gray-400 text-sm mb-6">
                  Scan the system for stuck orchestrations, stale workers, and orphaned tasks.
                </p>
                <button
                  onClick={scan}
                  className="px-5 py-2 bg-blue-700 hover:bg-blue-600 text-white rounded-lg text-sm font-medium"
                >
                  Start System Scan
                </button>
              </div>
            )}

            {/* Results */}
            {step === "results" && (
              <div>
                {error && (
                  <div className="bg-red-950 border border-red-800 rounded-lg p-3 mb-4 text-red-300 text-sm">
                    {error}
                  </div>
                )}

                {status && (
                  <div className="space-y-3 mb-5">
                    <div className={`flex items-center justify-between p-3 rounded-lg ${
                      stuckCount > 0 ? "bg-red-950 border border-red-800" : "bg-gray-900 border border-gray-800"
                    }`}>
                      <div>
                        <p className="text-sm font-medium text-white">Stuck Orchestrations</p>
                        <p className="text-xs text-gray-400 mt-0.5">Running longer than 60 minutes</p>
                      </div>
                      <span className={`text-lg font-bold ${stuckCount > 0 ? "text-red-400" : "text-green-400"}`}>
                        {stuckCount}
                      </span>
                    </div>

                    <div className={`flex items-center justify-between p-3 rounded-lg ${
                      staleWorkers > 0 ? "bg-yellow-950 border border-yellow-800" : "bg-gray-900 border border-gray-800"
                    }`}>
                      <div>
                        <p className="text-sm font-medium text-white">Stale Workers</p>
                        <p className="text-xs text-gray-400 mt-0.5">Missed heartbeat in last 5 minutes</p>
                      </div>
                      <span className={`text-lg font-bold ${staleWorkers > 0 ? "text-yellow-400" : "text-green-400"}`}>
                        {staleWorkers}
                      </span>
                    </div>

                    <div className={`flex items-center justify-between p-3 rounded-lg ${
                      workerRisk ? "bg-yellow-950 border border-yellow-800" : "bg-gray-900 border border-gray-800"
                    }`}>
                      <div>
                        <p className="text-sm font-medium text-white">Orphaned Task Risk</p>
                        <p className="text-xs text-gray-400 mt-0.5">Tasks assigned to stale workers</p>
                      </div>
                      <span className={`text-sm font-bold ${workerRisk ? "text-yellow-400" : "text-green-400"}`}>
                        {workerRisk ? "YES" : "NO"}
                      </span>
                    </div>
                  </div>
                )}

                {status && hasIssues && (
                  <div className="bg-blue-950 border border-blue-800 rounded-lg p-3 mb-4">
                    <p className="text-blue-300 text-sm font-medium">Recommended Action</p>
                    <p className="text-blue-200 text-xs mt-1">
                      {status.recommendation || "Run worker recovery to reassign orphaned tasks and clear stale workers."}
                    </p>
                  </div>
                )}

                {status && !hasIssues && (
                  <div className="bg-green-950 border border-green-800 rounded-lg p-4 text-center">
                    <p className="text-green-300 text-sm font-semibold">✓ System Healthy</p>
                    <p className="text-green-200 text-xs mt-1">No issues detected. No action needed.</p>
                  </div>
                )}

                <div className="flex gap-3 mt-4">
                  <button
                    onClick={scan}
                    className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
                  >
                    Re-scan
                  </button>
                  {hasIssues && (
                    <button
                      onClick={recover}
                      className="px-4 py-1.5 bg-yellow-700 hover:bg-yellow-600 text-white rounded text-sm font-medium"
                    >
                      Run Recovery
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Recovering */}
            {step === "recovering" && (
              <div className="text-center py-6">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-4" />
                <p className="text-gray-300 text-sm">Recovering orphaned tasks…</p>
              </div>
            )}

            {/* Done */}
            {step === "done" && (
              <div>
                <div className="bg-green-950 border border-green-800 rounded-lg p-4 mb-4">
                  <p className="text-green-300 font-semibold text-sm">✓ Recovery Complete</p>
                  {recoveryResult && (
                    <div className="mt-2 text-xs text-green-200">
                      <p>Tasks recovered: <strong>{recoveryResult.recovered_tasks ?? 0}</strong></p>
                      <p>Stale workers cleared: <strong>{recoveryResult.stale_workers?.length ?? 0}</strong></p>
                    </div>
                  )}
                </div>
                <button
                  onClick={reset}
                  className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm"
                >
                  Scan Again
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
