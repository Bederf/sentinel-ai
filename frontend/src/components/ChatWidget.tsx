import { useState, lazy, Suspense } from "react";
import { MessageSquare, X, Maximize2, Minimize2 } from "lucide-react";

const Chat = lazy(() => import("./Chat").then(m => ({ default: m.Chat })));

interface ChatWidgetProps {
  siteId?: string;
}

export function ChatWidget({ siteId }: ChatWidgetProps) {
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/30"
          onClick={() => { setOpen(false); setFullscreen(false); }}
        />
      )}

      <div
        className="fixed z-50"
        style={{
          bottom: "24px",
          right: "24px",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-end",
          gap: "12px",
        }}
      >
        {open && (
          <div
            className="rounded-md shadow-md overflow-hidden flex flex-col transition-all duration-200"
            style={fullscreen ? {
              position: "fixed",
              inset: "40px",
              width: "auto",
              height: "auto",
              maxHeight: "none",
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            } : {
              width: "420px",
              height: "600px",
              maxHeight: "calc(100vh - 120px)",
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0"
              style={{ borderColor: "var(--color-sentinel-border)" }}
            >
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
                <span className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  AI Chat
                </span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setFullscreen(!fullscreen)}
                  className="p-1.5 rounded hover:brightness-125 transition-colors"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  title={fullscreen ? "Minimize" : "Fullscreen"}
                >
                  {fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                </button>
                <button
                  onClick={() => { setOpen(false); setFullscreen(false); }}
                  className="p-1.5 rounded hover:brightness-125 transition-colors"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  title="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 min-h-0">
              <Suspense
                fallback={
                  <div className="flex items-center justify-center h-full">
                    <div className="animate-spin h-5 w-5 border-2 rounded-full" style={{ borderColor: "var(--color-sentinel-blue)", borderTopColor: "transparent" }} />
                  </div>
                }
              >
                <Chat defaultSiteId={siteId} />
              </Suspense>
            </div>
          </div>
        )}

        <button
          onClick={() => setOpen(!open)}
          className="rounded-full shadow-lg hover:brightness-110 transition-all active:scale-95 flex items-center justify-center"
          style={{
            width: "56px",
            height: "56px",
            background: open
              ? "var(--color-sentinel-bg-secondary)"
              : "var(--color-sentinel-blue)",
            color: open
              ? "var(--color-sentinel-text-secondary)"
              : "white",
            border: open ? "1px solid var(--color-sentinel-border)" : "none",
          }}
          aria-label={open ? "Close chat" : "Open chat"}
        >
          {open ? (
            <X className="h-6 w-6" />
          ) : (
            <MessageSquare className="h-6 w-6" />
          )}
        </button>
      </div>
    </>
  );
}
