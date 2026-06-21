import { useState, useEffect } from "react";
import { Globe, Plus, Trash2, Shield, AlertTriangle, CheckCircle } from "lucide-react";
import { usePlatformStore } from "../store";

interface ManageWebsitesProps {
  sendMessage: (type: string, payload: any) => void;
}

export default function ManageWebsites({ sendMessage }: ManageWebsitesProps) {
  const platforms = usePlatformStore((s) => s.platforms);
  const [newPlatformName, setNewPlatformName] = useState("");
  const [newPlatformUrl, setNewPlatformUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [pendingUrl, setPendingUrl] = useState<string | null>(null);

  useEffect(() => {
    sendMessage("platform:list", {});
  }, [sendMessage]);

  useEffect(() => {
    if (loading && pendingUrl) {
      const isAdded = platforms.some((p) => p.url.toLowerCase() === pendingUrl.toLowerCase());
      if (isAdded) {
        setSuccess(`Successfully verified and added dynamic AI agent target!`);
        setNewPlatformName("");
        setNewPlatformUrl("");
        setPendingUrl(null);
        setLoading(false);
        setTimeout(() => setSuccess(null), 4000);
      }
    }
  }, [platforms, loading, pendingUrl]);

  const handleAddPlatform = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (loading) return;

    if (!newPlatformName.trim()) {
      setError("Please enter a website name");
      return;
    }

    if (!newPlatformUrl.trim()) {
      setError("Please enter a homepage URL");
      return;
    }

    let formattedUrl = newPlatformUrl.trim();
    if (!/^https?:\/\//i.test(formattedUrl)) {
      formattedUrl = "https://" + formattedUrl;
    }

    try {
      new URL(formattedUrl);
    } catch {
      setError("Please enter a valid URL (e.g., https://example.com)");
      return;
    }

    setLoading(true);
    setPendingUrl(formattedUrl);

    sendMessage("platform:add", {
      name: newPlatformName.trim(),
      url: formattedUrl
    });

    // Timeout fallback if server verification fails or rejects
    setTimeout(() => {
      setLoading((currLoading) => {
        if (currLoading) {
          setError("Verification failed or took too long. Check that the site is online and reachable.");
          setPendingUrl(null);
          return false;
        }
        return currLoading;
      });
    }, 7000);
  };

  const handleDeactivate = (platformId: string, name: string) => {
    if (confirm(`Are you sure you want to deactivate ${name}? It will no longer be available for flight searches.`)) {
      sendMessage("platform:deactivate", { platformId });
    }
  };

  const isBuiltIn = (id: string) => {
    return ["makemytrip", "easemytrip", "cleartrip", "yatra", "ixigo", "paytm", "google_flights"].includes(id);
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Manage Scrape Sources</h1>
        <p className="page-subtitle">Add custom travel portals. Our general AI Web Agents will dynamically navigate and brute force coupon codes on them.</p>
      </div>

      <div className="grid-2-1" style={{ gridTemplateColumns: "1.2fr 1.8fr" }}>
        {/* LEFT COLUMN — Add Website Form */}
        <div className="flex-col gap-md">
          <span className="form-label">Add Search Website</span>
          <form className="glass-card module-card flex-col gap-md" onSubmit={handleAddPlatform} style={{ padding: 20 }}>
            <div className="flex-row gap-sm" style={{ alignItems: "center", marginBottom: 6 }}>
              <Shield size={18} className="text-primary" />
              <div style={{ fontSize: 13, fontWeight: 600 }}>AI Dynamic Targeting</div>
            </div>
            
            <p style={{ fontSize: 11, color: "hsl(var(--text-secondary))", lineHeight: 1.4, margin: "0 0 10px" }}>
              Provide the landing page URL of any travel portal. The AI Agent will read the page DOM, find flight search fields, input coordinates, and scan listings.
            </p>

            <div>
              <label className="form-label">Website Name</label>
              <input
                type="text"
                placeholder="e.g. Yatra, Ixigo, Goibibo"
                className="form-input"
                value={newPlatformName}
                onChange={(e) => setNewPlatformName(e.target.value)}
              />
            </div>

            <div>
              <label className="form-label">Homepage URL</label>
              <input
                type="text"
                placeholder="e.g. https://www.yatra.com/"
                className="form-input"
                value={newPlatformUrl}
                onChange={(e) => setNewPlatformUrl(e.target.value)}
              />
            </div>

            {error && (
              <div className="flex-row gap-xs text-error" style={{ fontSize: 11, alignItems: "center" }}>
                <AlertTriangle size={12} />
                <span>{error}</span>
              </div>
            )}

            {success && (
              <div className="flex-row gap-xs text-success" style={{ fontSize: 11, alignItems: "center" }}>
                <CheckCircle size={12} />
                <span>{success}</span>
              </div>
            )}

            <button type="submit" className="btn btn-primary flex-row gap-xs" disabled={loading} style={{ width: "100%", justifyContent: "center", marginTop: 8 }}>
              {loading ? (
                <span>Verifying Website...</span>
              ) : (
                <>
                  <Plus size={16} />
                  <span>Add Dynamic Source</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* RIGHT COLUMN — Platforms List */}
        <div className="flex-col gap-md">
          <span className="form-label">Configured Travel Sites ({platforms.length})</span>
          <div className="grid-2" style={{ maxHeight: "calc(100vh - 210px)", overflowY: "auto", paddingRight: 6 }}>
            {platforms.map((p) => {
              const native = isBuiltIn(p.id);
              return (
                <div key={p.id} className="glass-card module-card flex-col" style={{ padding: "16px 20px", justifyContent: "space-between", height: "100%" }}>
                  <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{p.name}</h3>
                      <span style={{ fontSize: 10, color: "hsl(var(--text-muted))", display: "inline-block", marginTop: 2 }}>
                        ID: {p.id}
                      </span>
                    </div>
                    {native ? (
                      <span className="badge badge-success" style={{ fontSize: 9 }}>SYSTEM NATIVE</span>
                    ) : (
                      <span className="badge badge-primary" style={{ fontSize: 9 }}>DYNAMIC AGENT</span>
                    )}
                  </div>
                  
                  <div className="flex-row gap-xs text-muted" style={{ fontSize: 11, marginBottom: 16, alignItems: "center" }}>
                    <Globe size={11} />
                    <a href={p.url} target="_blank" rel="noreferrer" className="text-secondary" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 220 }}>
                      {p.url}
                    </a>
                  </div>

                  <div className="flex-row" style={{ justifyContent: "flex-end", minHeight: 28 }}>
                    {!native && (
                      <button
                        className="btn btn-secondary flex-row gap-xs"
                        onClick={() => handleDeactivate(p.id, p.name)}
                        style={{ padding: "5px 10px", fontSize: 11, height: 28, color: "hsl(var(--color-error))" }}
                      >
                        <Trash2 size={12} />
                        <span>Remove</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
