import { useState } from "react";
import { postDemoWorkspaceSeed } from "../api";

/**
 * DemoWorkspaceSeeder.jsx
 *
 * One-click demo environment seeder for pilot and onboarding demos.
 * Seeds realistic workflow runs, orchestrations, recommendations,
 * autonomy actions, and client memory entries.
 *
 * Props:
 *   defaultSlug  — default workspace slug (default "demo-workspace")
 *   onSeeded     — optional callback(result) when seeding completes
 */
export default function DemoWorkspaceSeeder({ defaultSlug = "demo-workspace", onSeeded }) {
  const [slug, setSlug] = useState(defaultSlug);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSeed() {
    if (!slug.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await postDemoWorkspaceSeed({ workspace_slug: slug.trim() });
      setResult(data);
      onSeeded?.(data);
    } catch (e) {
      setError(e.message || "Seed failed");
    } finally {
      setLoading(false);
    }
  }

  const ENTITY_ICONS = {
    workflows:       "⚙️",
    orchestrations:  "🔄",
    recommendations: "💡",
    autonomy_actions:"🤖",
    memory_entries:  "🧠",
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🌱</span>
        <h3 className="text-white font-semibold text-sm">Demo Workspace Seeder</h3>
      </div>
      <p className="text-gray-500 text-xs mb-4">
        Populate a workspace with realistic demo data for pilot walkthroughs and onboarding demos.
      </p>

      {/* Slug input */}
      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          placeholder="workspace-slug"
          className="flex-1 bg-gray-800 border border-gray-700 text-white text-sm rounded px-3 py-1.5 focus:outline-none focus:border-blue-600 font-mono"
        />
        <button
          onClick={handleSeed}
          disabled={loading || !slug.trim()}
          className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
            loading || !slug.trim()
              ? "bg-gray-700 text-gray-500 cursor-not-allowed"
              : "bg-green-700 hover:bg-green-600 text-white"
          }`}
        >
          {loading ? "Seeding…" : "Seed Demo Data"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-950 border border-red-800 rounded p-3 text-red-300 text-xs mb-3">
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-green-950 border border-green-800 rounded-lg p-4">
          <p className="text-green-300 text-sm font-semibold mb-3">
            ✓ Seeded: <span className="font-mono">{result.workspace_slug}</span>
          </p>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(result.created || {}).map(([key, count]) => (
              <div key={key} className="flex items-center gap-2">
                <span className="text-base">{ENTITY_ICONS[key] || "•"}</span>
                <div>
                  <p className="text-green-200 text-xs font-medium">{count}</p>
                  <p className="text-green-500 text-xs capitalize">
                    {key.replace(/_/g, " ")}
                  </p>
                </div>
              </div>
            ))}
          </div>
          <p className="text-green-600 text-xs mt-3">
            Total: {result.total_entities} entities seeded
          </p>
          <button
            onClick={() => { setResult(null); setSlug(defaultSlug); }}
            className="mt-3 px-3 py-1 bg-green-900 hover:bg-green-800 text-green-300 rounded text-xs"
          >
            Seed Another
          </button>
        </div>
      )}
    </div>
  );
}
