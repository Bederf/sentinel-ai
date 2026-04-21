import { useState, useEffect, useRef } from "react";

const LOGO_URL = "/images/sentinel-logo.png";

const theme = {
  navyDeep: "#060E18",
  navy: "#0B1D33",
  navyMid: "#0F2640",
  navyLight: "#163350",
  teal: "#2E86AB",
  tealBright: "#3AAFDE",
  tealGlow: "rgba(46,134,171,0.15)",
  amber: "#E8913A",
  amberGlow: "rgba(232,145,58,0.2)",
  white: "#F0F4F8",
  whitePure: "#FFFFFF",
  grey: "#7B8FA3",
  greyLight: "#A8B8C8",
};

// ─── Staggered fade-in hook ───
function useFadeIn(delay = 0) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);
  return {
    opacity: visible ? 1 : 0,
    transform: visible ? "translateY(0)" : "translateY(28px)",
    transition: `all 0.85s cubic-bezier(0.22,1,0.36,1) ${delay}ms`,
  };
}

// ─── Intersection observer hook ───
function useReveal(): [React.RefObject<HTMLElement | null>, React.CSSProperties] {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setVisible(true); obs.unobserve(el); } },
      { threshold: 0.12 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return [ref, {
    opacity: visible ? 1 : 0,
    transform: visible ? "translateY(0)" : "translateY(30px)",
    transition: "all 0.8s cubic-bezier(0.22,1,0.36,1)",
  }];
}

// ─── Breathing dot ───
function LiveDot() {
  const [pulse, setPulse] = useState(false);
  useEffect(() => {
    const i = setInterval(() => setPulse(p => !p), 1500);
    return () => clearInterval(i);
  }, []);
  return (
    <span style={{
      display: "inline-block", width: 7, height: 7, borderRadius: "50%",
      background: theme.teal, marginRight: 8, verticalAlign: "middle",
      boxShadow: pulse ? `0 0 12px ${theme.teal}` : `0 0 4px rgba(46,134,171,0.3)`,
      opacity: pulse ? 1 : 0.6,
      transition: "all 1.4s ease-in-out",
    }} />
  );
}

// ─── Capability card ───
function CapCard({ icon, name, text }: { icon: string; name: string; text: string }) {
  const [hov, setHov] = useState(false);
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: hov ? theme.navyLight : theme.navyMid,
        padding: "2.25rem 1.75rem",
        transition: "background 0.4s cubic-bezier(0.22,1,0.36,1)",
        position: "relative", overflow: "hidden",
      }}
    >
      <div style={{
        position: "absolute", inset: 0,
        background: "linear-gradient(135deg, rgba(46,134,171,0.05), transparent)",
        opacity: hov ? 1 : 0, transition: "opacity 0.4s",
      }} />
      <div style={{ fontSize: "1.6rem", marginBottom: "1rem", position: "relative", zIndex: 1 }}>{icon}</div>
      <div style={{
        fontWeight: 600, fontSize: "0.95rem", letterSpacing: "0.02em",
        color: theme.whitePure, marginBottom: "0.5rem", position: "relative", zIndex: 1,
      }}>{name}</div>
      <p style={{
        fontSize: "0.82rem", fontWeight: 300, color: theme.grey,
        lineHeight: 1.65, margin: 0, position: "relative", zIndex: 1,
      }}>{text}</p>
    </div>
  );
}

// ─── Stat ───
function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{
        fontSize: "clamp(2rem, 4vw, 2.8rem)", fontWeight: 800, letterSpacing: "-0.02em",
        background: `linear-gradient(135deg, ${theme.tealBright}, ${theme.amber})`,
        WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
        backgroundClip: "text",
      }}>{value}</div>
      <div style={{
        fontSize: "0.72rem", fontWeight: 500, color: theme.grey,
        letterSpacing: "0.1em", textTransform: "uppercase", marginTop: "0.35rem",
      }}>{label}</div>
    </div>
  );
}

// ─── Form input ───
function FormInput({ type = "text", name, placeholder, required, style: s }: {
  type?: string; name: string; placeholder: string; required?: boolean; style?: React.CSSProperties;
}) {
  const [focused, setFocused] = useState(false);
  return (
    <input
      type={type} name={name} placeholder={placeholder} required={required}
      aria-label={placeholder}
      onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      style={{
        width: "100%", padding: "0.85rem 1.15rem",
        background: theme.navyMid,
        border: `1px solid ${focused ? theme.teal : "rgba(46,134,171,0.1)"}`,
        borderRadius: 12, color: theme.white,
        fontFamily: "'Outfit', sans-serif", fontSize: "0.9rem", fontWeight: 300,
        outline: "none", minHeight: 48,
        boxShadow: focused ? `0 0 0 3px ${theme.tealGlow}` : "none",
        transition: "border-color 0.3s, box-shadow 0.3s",
        ...s,
      }}
    />
  );
}

// ─── Separator ───
function Sep() {
  return (
    <div style={{
      width: 60, height: 1, margin: "1rem auto",
      background: `linear-gradient(90deg, transparent, ${theme.teal}, transparent)`,
      opacity: 0.5,
    }} />
  );
}

// ═══════════════════════════════════════════
//  MAIN COMPONENT
// ═══════════════════════════════════════════
interface SentinelSplashProps {
  onEnterPlatform: () => void;
}

export default function SentinelSplash({ onEnterPlatform }: SentinelSplashProps) {
  const [submitted, setSubmitted] = useState(false);

  // Staggered hero animations
  const aNav = useFadeIn(100);
  const aLogo = useFadeIn(300);
  const aLabel = useFadeIn(600);
  const aH1 = useFadeIn(800);
  const aP = useFadeIn(1000);
  const aBtn = useFadeIn(1200);
  const aScroll = useFadeIn(1600);

  // Scroll reveal sections
  const [capRef, capStyle] = useReveal();
  const [statRef, statStyle] = useReveal();
  const [contactRef, contactStyle] = useReveal();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setTimeout(() => setSubmitted(false), 3500);
  };

  const capabilities = [
    { icon: "\u{1F52E}", name: "Predictive Maintenance", text: "AI detects failures before they happen. Cut equipment downtime by up to 70%." },
    { icon: "\u{26A1}", name: "Energy Optimisation", text: "HVAC, lighting, and load management driven by real-time building intelligence." },
    { icon: "\u{2600}\u{FE0F}", name: "Solar & BESS", text: "Autonomous battery dispatch, TOU arbitrage, and generation forecasting." },
    { icon: "\u{1F331}", name: "Green Reporting", text: "Automated carbon accounting, ESG reporting, and Green Star certification support." },
    { icon: "\u{1F4AC}", name: "Conversational AI", text: "Ask your building anything via WhatsApp. No logins, no portals \u2014 just answers." },
    { icon: "\u{1F50C}", name: "Load Shedding Ready", text: "Automated response, generator coordination, and BESS priority management." },
  ];

  const stats = [
    { value: "40%", label: "Downtime Reduction" },
    { value: "R2.4M", label: "Annual Savings" },
    { value: "90%", label: "Less Reporting" },
    { value: "24/7", label: "Autonomous Monitoring" },
  ];

  return (
    <div style={{
      background: theme.navyDeep, color: theme.white,
      fontFamily: "'Outfit', sans-serif",
      minHeight: "100vh", overflow: "hidden", position: "relative",
      WebkitFontSmoothing: "antialiased",
    }}>

      {/* Google Font */}
      <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@200;300;400;500;600;700;800;900&display=swap" rel="stylesheet" />

      {/* Atmosphere */}
      <div style={{
        position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none",
        background: [
          `radial-gradient(ellipse 900px 700px at 15% 10%, rgba(46,134,171,0.07), transparent 70%)`,
          `radial-gradient(ellipse 600px 500px at 85% 70%, rgba(232,145,58,0.03), transparent 70%)`,
          `radial-gradient(ellipse 1200px 800px at 50% 50%, rgba(15,38,64,0.8), transparent)`,
        ].join(", "),
      }} />

      {/* Grid overlay */}
      <div style={{
        position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none",
        backgroundImage: [
          "linear-gradient(rgba(46,134,171,0.018) 1px, transparent 1px)",
          "linear-gradient(90deg, rgba(46,134,171,0.018) 1px, transparent 1px)",
        ].join(", "),
        backgroundSize: "80px 80px",
        WebkitMaskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, black 30%, transparent 80%)",
        maskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, black 30%, transparent 80%)",
      }} />

      {/* Content wrapper */}
      <div style={{
        position: "relative", zIndex: 2,
        maxWidth: 1140, margin: "0 auto",
        padding: "0 clamp(1.25rem, 4vw, 2.5rem)",
      }}>

        {/* Header */}
        <header style={{
          padding: "1.75rem 0",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexWrap: "wrap", gap: "0.75rem",
          ...aNav,
        }}>
          <span style={{
            fontWeight: 700, fontSize: "0.85rem",
            letterSpacing: "0.2em", textTransform: "uppercase",
            color: theme.greyLight,
          }}>Sentinel</span>
          <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
            <span style={{
              display: "flex", alignItems: "center", gap: 4,
              fontSize: "0.8rem", color: theme.grey,
            }}>
              <LiveDot />
              <a href="mailto:info@sentinel-ai.co.za" style={{
                color: theme.teal, textDecoration: "none",
              }}>info@sentinel-ai.co.za</a>
            </span>
            <button
              onClick={onEnterPlatform}
              style={{
                padding: "0.5rem 1.25rem",
                background: "transparent",
                border: `1px solid ${theme.teal}`,
                borderRadius: 100,
                color: theme.teal,
                fontFamily: "'Outfit', sans-serif",
                fontWeight: 600, fontSize: "0.78rem",
                letterSpacing: "0.04em",
                cursor: "pointer",
                transition: "all 0.3s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = theme.teal;
                e.currentTarget.style.color = theme.navyDeep;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = theme.teal;
              }}
            >
              Enter Platform
            </button>
          </div>
        </header>

        {/* Hero */}
        <section style={{
          minHeight: "82vh",
          display: "flex", flexDirection: "column",
          justifyContent: "center", alignItems: "center",
          textAlign: "center", padding: "3rem 0 2rem",
        }}>

          {/* Logo */}
          <div style={{
            width: "min(420px, 75vw)", marginBottom: "2.5rem",
            ...aLogo,
          }}>
            <img
              src={LOGO_URL}
              alt="SENTINEL - Intelligent Asset Protection"
              style={{
                width: "100%", height: "auto",
                filter: "invert(1) brightness(2) contrast(1.1)",
                userSelect: "none",
              }}
              draggable={false}
            />
          </div>

          <p style={{
            fontSize: "clamp(0.7rem, 1.5vw, 0.85rem)",
            fontWeight: 500, letterSpacing: "0.35em",
            textTransform: "uppercase", color: theme.teal,
            marginBottom: "2rem",
            ...aLabel,
          }}>AI-Powered Building Intelligence</p>

          <h1 style={{
            fontSize: "clamp(2.4rem, 6vw, 4.2rem)",
            fontWeight: 800, lineHeight: 1.05,
            letterSpacing: "-0.02em", marginBottom: "1.75rem",
            ...aH1,
          }}>
            Your buildings talk.<br />
            <span style={{
              background: `linear-gradient(135deg, ${theme.teal}, ${theme.tealBright})`,
              WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}>We help you listen.</span>
          </h1>

          <p style={{
            fontSize: "clamp(1rem, 2.2vw, 1.2rem)",
            fontWeight: 300, color: theme.greyLight,
            maxWidth: 580, lineHeight: 1.75, marginBottom: "3rem",
            ...aP,
          }}>
            Predictive maintenance, energy optimisation, solar&nbsp;&amp;&nbsp;BESS
            management, and sustainability reporting&nbsp;&mdash; all through a single
            conversational&nbsp;interface.
          </p>

          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", justifyContent: "center", ...aBtn }}>
            <a
              href="#contact"
              onClick={(e) => {
                e.preventDefault();
                document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" });
              }}
              style={{
                display: "inline-flex", alignItems: "center", gap: "0.8rem",
                padding: "1.05rem 2.5rem",
                background: `linear-gradient(135deg, ${theme.teal}, ${theme.tealBright})`,
                color: theme.navyDeep,
                fontFamily: "'Outfit', sans-serif",
                fontWeight: 700, fontSize: "0.95rem",
                letterSpacing: "0.04em",
                border: "none", borderRadius: 100,
                cursor: "pointer", textDecoration: "none",
                boxShadow: `0 4px 24px rgba(46,134,171,0.25), inset 0 1px 0 rgba(255,255,255,0.15)`,
                minHeight: 52,
              }}
            >
              Request a Demo
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor" width="16" height="16">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
              </svg>
            </a>
            <button
              onClick={onEnterPlatform}
              style={{
                display: "inline-flex", alignItems: "center", gap: "0.8rem",
                padding: "1.05rem 2.5rem",
                background: "transparent",
                color: theme.teal,
                fontFamily: "'Outfit', sans-serif",
                fontWeight: 700, fontSize: "0.95rem",
                letterSpacing: "0.04em",
                border: `2px solid ${theme.teal}`,
                borderRadius: 100,
                cursor: "pointer",
                minHeight: 52,
                transition: "all 0.3s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(46,134,171,0.1)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
            >
              Enter Platform
            </button>
          </div>

          {/* Scroll hint */}
          <div style={{
            marginTop: "3rem",
            display: "flex", flexDirection: "column",
            alignItems: "center", gap: "0.5rem",
            ...aScroll,
          }}>
            <span style={{
              fontSize: "0.7rem", letterSpacing: "0.2em",
              textTransform: "uppercase", color: theme.grey, fontWeight: 400,
            }}>Explore</span>
            <div style={{
              width: 1, height: 40,
              background: `linear-gradient(to bottom, ${theme.teal}, transparent)`,
              opacity: 0.5,
            }} />
          </div>
        </section>

        {/* Capabilities */}
        <section ref={capRef as React.RefObject<HTMLElement>} style={{ padding: "5rem 0", ...capStyle }}>
          <p style={{
            fontSize: "0.7rem", fontWeight: 600,
            letterSpacing: "0.3em", textTransform: "uppercase",
            color: theme.teal, marginBottom: "1rem", textAlign: "center",
          }}>Platform</p>
          <h2 style={{
            fontSize: "clamp(1.6rem, 3.5vw, 2.2rem)",
            fontWeight: 700, textAlign: "center",
            marginBottom: "3.5rem", letterSpacing: "-0.01em",
          }}>One platform. Every building system.</h2>

          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: 1,
            background: "rgba(46,134,171,0.06)",
            borderRadius: 20, overflow: "hidden",
            border: "1px solid rgba(46,134,171,0.06)",
          }}>
            {capabilities.map((c, i) => (
              <CapCard key={i} {...c} />
            ))}
          </div>
        </section>

        <Sep />

        {/* Stats */}
        <section ref={statRef as React.RefObject<HTMLElement>} style={{
          padding: "3rem 0",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "2rem",
          ...statStyle,
        }}>
          {stats.map((s, i) => <Stat key={i} {...s} />)}
        </section>

        <Sep />

        {/* Contact */}
        <section ref={contactRef as React.RefObject<HTMLElement>} id="contact" style={{
          padding: "5rem 0 3rem", textAlign: "center",
          ...contactStyle,
        }}>
          <h2 style={{
            fontSize: "clamp(1.6rem, 3vw, 2.2rem)",
            fontWeight: 700, marginBottom: "0.75rem",
          }}>Let's Talk Buildings</h2>
          <p style={{
            color: theme.greyLight, fontSize: "1rem", fontWeight: 300,
            marginBottom: "3rem", maxWidth: 460,
            marginLeft: "auto", marginRight: "auto", lineHeight: 1.7,
          }}>
            Get a complimentary site assessment and see what SENTINEL
            can unlock for your portfolio.
          </p>

          <form
            onSubmit={handleSubmit}
            style={{
              display: "flex", flexDirection: "column", gap: "0.85rem",
              maxWidth: 420, margin: "0 auto",
            }}
          >
            <div style={{ display: "flex", gap: "0.85rem", flexWrap: "wrap" }}>
              <FormInput name="name" placeholder="Your name" required style={{ flex: 1, minWidth: 160 }} />
              <FormInput name="company" placeholder="Company" required style={{ flex: 1, minWidth: 160 }} />
            </div>
            <FormInput type="email" name="email" placeholder="Email address" required />
            <FormInput type="tel" name="phone" placeholder="Phone number" />
            <textarea
              name="message"
              placeholder="Tell us about your buildings &mdash; how many sites, what BMS, any solar?"
              aria-label="Message"
              rows={4}
              style={{
                width: "100%", padding: "0.85rem 1.15rem",
                background: theme.navyMid,
                border: "1px solid rgba(46,134,171,0.1)",
                borderRadius: 12, color: theme.white,
                fontFamily: "'Outfit', sans-serif",
                fontSize: "0.9rem", fontWeight: 300,
                outline: "none", resize: "vertical", minHeight: 110,
              }}
            />
            <button
              type="submit"
              disabled={submitted}
              style={{
                padding: "0.95rem 2rem",
                background: submitted
                  ? "linear-gradient(135deg, #1BA39C, #27AE60)"
                  : `linear-gradient(135deg, ${theme.teal}, ${theme.tealBright})`,
                color: theme.navyDeep,
                fontFamily: "'Outfit', sans-serif",
                fontWeight: 700, fontSize: "0.9rem",
                letterSpacing: "0.04em",
                border: "none", borderRadius: 100,
                cursor: submitted ? "default" : "pointer",
                minHeight: 52,
                boxShadow: `0 4px 20px rgba(46,134,171,0.2)`,
                transition: "all 0.35s cubic-bezier(0.22,1,0.36,1)",
              }}
            >
              {submitted ? "Sent \u2713" : "Send Enquiry"}
            </button>
          </form>
        </section>

        {/* Footer */}
        <footer style={{
          padding: "3rem 0 2.5rem", textAlign: "center",
          borderTop: "1px solid rgba(46,134,171,0.06)",
          marginTop: "2rem",
        }}>
          <div style={{
            fontWeight: 700, fontSize: "0.75rem",
            letterSpacing: "0.2em", textTransform: "uppercase",
            color: theme.grey, marginBottom: "0.4rem",
          }}>Sentinel</div>
          <div style={{
            fontSize: "0.7rem", fontWeight: 300,
            color: "rgba(123,143,163,0.4)",
          }}>&copy; 2026 SENTINEL. Intelligent Asset Protection. All rights reserved.</div>
          <div style={{
            marginTop: "1rem",
            display: "flex", justifyContent: "center", gap: "2.5rem",
          }}>
            <a href="mailto:info@sentinel-ai.co.za" style={{
              fontSize: "0.78rem", fontWeight: 400,
              color: theme.grey, textDecoration: "none",
            }}>Email</a>
            <a href="https://sentinel-ai.co.za" target="_blank" rel="noopener noreferrer" style={{
              fontSize: "0.78rem", fontWeight: 400,
              color: theme.grey, textDecoration: "none",
            }}>sentinel-ai.co.za</a>
          </div>
        </footer>

      </div>
    </div>
  );
}
