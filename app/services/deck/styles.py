"""Shared CSS for Orionmano deck generation — dark navy theme matching brand."""

# Brand colors
NAVY = "#0C1929"
TEAL = "#14B8A6"
TEAL_DIM = "rgba(20,184,166,0.15)"
WHITE = "#F8FAFC"
GRAY = "#94A3B8"
DARK_CARD = "rgba(15,23,42,0.8)"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

@page { size: 1280px 720px; margin: 0; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Inter', sans-serif; background: #0C1929; color: #E2E8F0; }

.slide {
  width: 1280px; height: 720px; position: relative;
  overflow: hidden; background: #0C1929; page-break-after: always;
}
.slide:last-child { page-break-after: auto; }

.rel { position: relative; z-index: 2; }
.teal { color: #14B8A6; }
.white { color: #F8FAFC; }

.label {
  font-size: 11px; font-weight: 700; color: #14B8A6;
  text-transform: uppercase; letter-spacing: 4px; margin-bottom: 14px;
}

h1 { font-size: 44px; font-weight: 700; color: #F8FAFC; line-height: 1.15; margin-bottom: 14px; }
h2 { font-size: 36px; font-weight: 700; color: #F8FAFC; line-height: 1.15; margin-bottom: 12px; }
h3 { font-size: 18px; font-weight: 600; color: #F8FAFC; }
p { font-size: 15px; color: #94A3B8; line-height: 1.7; }

.divider {
  width: 50px; height: 3px;
  background: linear-gradient(90deg, #14B8A6, #2DD4BF);
  border-radius: 2px; margin: 14px 0;
}

.glow {
  position: absolute; border-radius: 50%; filter: blur(80px);
  opacity: 0.12; pointer-events: none;
}
.glow-t { background: #14B8A6; }
.glow-b { background: #3B82F6; }

.card {
  background: linear-gradient(135deg, rgba(15,23,42,0.9), rgba(12,25,41,0.6));
  border: 1px solid rgba(148,163,184,0.1); border-radius: 16px; padding: 24px;
}

.card-teal {
  background: linear-gradient(135deg, rgba(20,184,166,0.08), rgba(20,184,166,0.02));
  border: 1px solid rgba(20,184,166,0.15); border-radius: 16px; padding: 24px;
}

.stat-num { font-size: 48px; font-weight: 800; color: #14B8A6; line-height: 1; }
.stat-label { font-size: 12px; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 1.5px; margin-top: 6px; }

.icon-box {
  width: 48px; height: 48px;
  background: linear-gradient(135deg, rgba(20,184,166,0.15), rgba(20,184,166,0.05));
  border: 1px solid rgba(20,184,166,0.2); border-radius: 12px;
  display: flex; align-items: center; justify-content: center; margin-bottom: 12px;
  color: #14B8A6; font-size: 20px;
}

.g2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.g3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }

.footer {
  position: absolute; bottom: 0; left: 0; right: 0; height: 44px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 60px; border-top: 1px solid rgba(20,184,166,0.06); z-index: 10;
}
.footer span { font-size: 10px; color: #334155; letter-spacing: 1px; }
.footer .brand { color: #14B8A6; font-weight: 600; letter-spacing: 3px; text-transform: uppercase; }

.bullet { color: #14B8A6; margin-right: 8px; }
.bullet-item { font-size: 14px; color: #CBD5E1; margin-bottom: 10px; display: flex; align-items: flex-start; }
.bullet-item span { line-height: 1.5; }
"""
