import json
import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Smart Factory Operations Center",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state bootstrap ───────────────────────────────────────────────────
for _k, _v in {
    "session_id":     str(uuid.uuid4()),
    "messages":       [],
    "dark_mode":      False,
    "pending_approval": None,   # {"proposals": [...], "approve_msg": str, "reject_msg": str}
    "fleet_summary":  None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Theme ─────────────────────────────────────────────────────────────────────

def _inject_theme(dark: bool) -> None:
    # ── colour palette ────────────────────────────────────────────────────────
    if dark:
        # black / dark-grey / white  (GitHub-style dark)
        bg           = "#0D1117"
        sidebar      = "#161B22"
        card         = "#1C2128"
        card2        = "#22272E"
        border       = "#30363D"
        primary      = "#58A6FF"
        primary_h    = "#79C0FF"
        text         = "#E6EDF3"
        subtext      = "#8B949E"
        user_bg      = "#1B2533"
        asst_bg      = "#161B22"
        input_bg     = "#1C2128"
        metric_bg    = "#1C2128"
        btn_approve  = "#238636"
        btn_rej      = "#DA3633"
        btn_appr_h   = "#2EA043"
        btn_rej_h    = "#F85149"
        divider      = "#30363D"
        header_bg    = "#0D1117"
        sidebar_text = "#E6EDF3"
        badge_over   = ("rgba(218,54,51,0.2)", "#F85149")   # bg, text
        badge_risk   = ("rgba(210,153,34,0.2)", "#E3B341")
        badge_under  = ("rgba(88,166,255,0.15)", "#79C0FF")
        badge_ok     = ("rgba(46,160,67,0.2)",  "#3FB950")
    else:
        # pure white / corporate blue
        bg           = "#FFFFFF"
        sidebar      = "#0B3D91"
        card         = "#F8FAFF"
        card2        = "#EEF3FB"
        border       = "#C8DCEE"
        primary      = "#0B3D91"
        primary_h    = "#1A5FA8"
        text         = "#0F1D2E"
        subtext      = "#4A6582"
        user_bg      = "#E0EFFF"
        asst_bg      = "#FFFFFF"
        input_bg     = "#FFFFFF"
        metric_bg    = "#E8F2FF"
        btn_approve  = "#15803D"
        btn_rej      = "#B91C1C"
        btn_appr_h   = "#166534"
        btn_rej_h    = "#991B1B"
        divider      = "#C8DCEE"
        header_bg    = "#0B3D91"
        sidebar_text = "#FFFFFF"
        badge_over   = ("#FEE2E2", "#B91C1C")
        badge_risk   = ("#FEF3C7", "#92400E")
        badge_under  = ("#DBEAFE", "#1D4ED8")
        badge_ok     = ("#DCFCE7", "#15803D")

    st.markdown(f"""
<style>
/* ── Foundations ─────────────────────────────────────────────────────────── */
.stApp {{
    background-color: {bg};
}}
.stApp > header {{
    background-color: {header_bg} !important;
    border-bottom: 1px solid {border};
}}
.main .block-container {{
    padding-top: 1.25rem;
    max-width: 860px;
    background-color: {bg};
}}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    background-color: {sidebar} !important;
    border-right: 1px solid {border};
}}
[data-testid="stSidebar"] *:not(button) {{
    color: {sidebar_text} !important;
}}
[data-testid="stSidebar"] .stMetric {{
    background-color: {"rgba(255,255,255,0.10)" if not dark else metric_bg};
    border: 1px solid {"rgba(255,255,255,0.18)" if not dark else border};
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 4px;
}}
[data-testid="stSidebar"] [data-testid="stMetricValue"] {{
    color: {sidebar_text} !important;
    font-weight: 700 !important;
}}
[data-testid="stSidebar"] button {{
    background-color: {"rgba(255,255,255,0.14)" if not dark else "rgba(255,255,255,0.08)"} !important;
    color: {sidebar_text} !important;
    border: 1px solid {"rgba(255,255,255,0.28)" if not dark else border} !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
}}
[data-testid="stSidebar"] button:hover {{
    background-color: {"rgba(255,255,255,0.24)" if not dark else "rgba(255,255,255,0.15)"} !important;
}}
[data-testid="stSidebarToggleButton"] svg {{
    fill: {sidebar_text} !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: {"rgba(255,255,255,0.2)" if not dark else border} !important;
}}
/* Dark-mode toggle label inside sidebar */
[data-testid="stSidebar"] [data-testid="stToggle"] label span {{
    color: {sidebar_text} !important;
}}

/* ── Typography ──────────────────────────────────────────────────────────── */
h1 {{
    color: {primary} !important;
    font-size: 1.75rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.4px !important;
}}
h2, h3 {{
    color: {primary} !important;
    font-weight: 700 !important;
}}
h4, h5 {{
    color: {text} !important;
    font-weight: 600 !important;
}}
p, li {{
    color: {text};
}}
.stCaption p {{
    color: {subtext} !important;
    font-size: 0.78rem !important;
}}
hr {{
    border-color: {divider} !important;
}}

/* ── Chat messages ───────────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {{
    background-color: {asst_bg};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 4px 10px;
    margin: 5px 0;
}}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
    background-color: {user_bg};
}}

/* ── Chat input ──────────────────────────────────────────────────────────── */
[data-testid="stChatInput"] textarea {{
    background-color: {input_bg} !important;
    color: {text} !important;
    border: 1.5px solid {border} !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
}}
[data-testid="stChatInput"] textarea:focus {{
    border-color: {primary} !important;
    box-shadow: 0 0 0 3px {"rgba(88,166,255,0.2)" if dark else "rgba(11,61,145,0.12)"} !important;
}}

/* ── Approval / recommendation card ─────────────────────────────────────── */
.approval-card {{
    background-color: {card2};
    border: 1.5px solid {primary};
    border-radius: 14px;
    padding: 18px 22px;
    margin: 10px 0 14px 0;
    box-shadow: 0 2px 8px {"rgba(0,0,0,0.35)" if dark else "rgba(11,61,145,0.08)"};
}}
.approval-card h4 {{
    margin: 0 0 12px 0;
    font-size: 1rem;
    color: {primary} !important;
}}
.proposal-row {{
    background-color: {card};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 8px;
    font-size: 0.9rem;
    color: {text};
    line-height: 1.5;
}}

/* ── Status badges ───────────────────────────────────────────────────────── */
.badge {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-left: 6px;
    vertical-align: middle;
}}
.badge-overloaded {{ background: {badge_over[0]}; color: {badge_over[1]}; }}
.badge-at_risk    {{ background: {badge_risk[0]}; color: {badge_risk[1]}; }}
.badge-underutil  {{ background: {badge_under[0]}; color: {badge_under[1]}; }}
.badge-healthy    {{ background: {badge_ok[0]};    color: {badge_ok[1]};   }}

/* ── Generic buttons ─────────────────────────────────────────────────────── */
.stButton > button {{
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
    font-size: 0.9rem !important;
}}

/* ── Starter-prompt buttons ──────────────────────────────────────────────── */
.starter-btn .stButton > button {{
    background-color: {card2} !important;
    border: 1px solid {border} !important;
    color: {text} !important;
    text-align: left !important;
    padding: 10px 14px !important;
    height: auto !important;
    white-space: pre-wrap !important;
}}
.starter-btn .stButton > button:hover {{
    border-color: {primary} !important;
    background-color: {"rgba(88,166,255,0.08)" if dark else "rgba(11,61,145,0.06)"} !important;
}}

/* ── Thinking animation ──────────────────────────────────────────────────── */
@keyframes sf-pulse {{
    0%, 100% {{ opacity: 1; }}
    50%       {{ opacity: 0.35; }}
}}
.sf-thinking {{
    animation: sf-pulse 1.3s ease-in-out infinite;
    color: {subtext} !important;
    font-style: italic;
    font-size: 0.95rem;
}}

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar       {{ width: 5px; }}
::-webkit-scrollbar-track {{ background: {bg}; }}
::-webkit-scrollbar-thumb {{ background: {border}; border-radius: 3px; }}

/* ── Hide Streamlit chrome ───────────────────────────────────────────────── */
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
[data-testid="stToolbar"] {{ visibility: hidden; }}
</style>

<script>
/* ── Approve / Reject button colouring via MutationObserver ─────────────── */
(function () {{
  var A = "{btn_approve}", AH = "{btn_appr_h}";
  var R = "{btn_rej}",     RH = "{btn_rej_h}";

  function paint() {{
    document.querySelectorAll(".stButton button").forEach(function (btn) {{
      var t = (btn.innerText || "").trim();
      if (t.indexOf("Approve") !== -1) {{
        btn.style.setProperty("background-color", A, "important");
        btn.style.setProperty("border-color",     A, "important");
        btn.style.setProperty("color",         "#fff", "important");
        btn.onmouseenter = function () {{
          this.style.setProperty("background-color", AH, "important");
        }};
        btn.onmouseleave = function () {{
          this.style.setProperty("background-color", A, "important");
        }};
      }} else if (t.indexOf("Reject") !== -1) {{
        btn.style.setProperty("background-color", R, "important");
        btn.style.setProperty("border-color",     R, "important");
        btn.style.setProperty("color",         "#fff", "important");
        btn.onmouseenter = function () {{
          this.style.setProperty("background-color", RH, "important");
        }};
        btn.onmouseleave = function () {{
          this.style.setProperty("background-color", R, "important");
        }};
      }}
    }});
  }}

  paint();
  new MutationObserver(paint).observe(document.body, {{
    childList: true,
    subtree:   true,
  }});
}})();
</script>
""", unsafe_allow_html=True)


_inject_theme(st.session_state.dark_mode)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _send_message(message: str):
    """
    POST to /chat/stream, show a pulsing 'Thinking…' placeholder until the
    first token arrives, then stream tokens live.  Returns
    (full_reply, needs_approval, proposals).
    """
    placeholder = st.empty()
    placeholder.markdown(
        '<span class="sf-thinking">⏳ Thinking…</span>',
        unsafe_allow_html=True,
    )

    full_text      = ""
    needs_approval = False
    proposals      = []

    try:
        with requests.post(
            f"{BACKEND_URL}/chat/stream",
            json={"message": message, "session_id": st.session_state.session_id},
            stream=True,
            timeout=180,
        ) as r:
            r.raise_for_status()
            for raw_line in r.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")
                if etype == "token":
                    full_text += event.get("text", "")
                    placeholder.markdown(full_text + "▌")
                elif etype == "end":
                    needs_approval = event.get("needs_approval", False)
                    proposals      = event.get("proposals", [])
                elif etype == "error":
                    full_text = f"⚠️ Backend error: {event.get('text', 'unknown error')}"

    except requests.exceptions.ConnectionError:
        full_text = "⚠️ Cannot reach the backend. Make sure it is running."
    except requests.exceptions.Timeout:
        full_text = "⚠️ The backend took too long to respond. Please try again."
    except Exception as exc:
        full_text = f"⚠️ Unexpected error: {exc}"

    if not full_text:
        full_text = "No response received."

    placeholder.markdown(full_text)
    return full_text, needs_approval, proposals


def _load_fleet_summary():
    try:
        r = requests.get(f"{BACKEND_URL}/fleet/summary", timeout=8)
        return r.json() if r.ok else None
    except Exception:
        return None


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🏭 Smart Factory")
    st.markdown(
        "<span style='font-size:0.8rem;opacity:0.7;'>Operations Center</span>",
        unsafe_allow_html=True,
    )
    st.divider()

    # Dark-mode toggle
    dark = st.toggle("🌙 Dark mode", value=st.session_state.dark_mode, key="dm_toggle")
    if dark != st.session_state.dark_mode:
        st.session_state.dark_mode = dark
        st.rerun()

    st.divider()

    # Fleet summary
    st.markdown("#### Fleet Summary")
    _, col_r = st.columns([4, 1])
    with col_r:
        if st.button("↻", help="Refresh"):
            st.session_state.fleet_summary = None

    if st.session_state.fleet_summary is None:
        st.session_state.fleet_summary = _load_fleet_summary()

    sm = st.session_state.fleet_summary
    if sm:
        st.metric("Total IPCs", sm.get("total_ipcs", "—"))
        c1, c2 = st.columns(2)
        c1.metric("✅ Healthy",      sm.get("healthy",       "—"))
        c2.metric("💤 Underutil.",   sm.get("underutilized", "—"))
        c1.metric("⚠️ At Risk",      sm.get("at_risk",       "—"))
        c2.metric("🔴 Overloaded",   sm.get("overloaded",    "—"))
    else:
        st.caption("Fleet data unavailable — backend may still be starting.")

    st.divider()

    # Recent decisions
    st.markdown("#### Recent Decisions")
    try:
        resp = requests.get(f"{BACKEND_URL}/decisions", timeout=5)
        if resp.ok:
            decs = resp.json()
            if decs:
                for d in decs[-5:][::-1]:
                    icon = {"approved": "✅", "rejected": "❌", "deferred": "⏸️"}.get(
                        d.get("status", ""), "•"
                    )
                    st.markdown(
                        f"{icon} **{d.get('ipc_id','?')}** "
                        f"<span style='font-size:0.75rem;opacity:0.75'>"
                        f"{d.get('status','')}</span>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No decisions recorded yet.")
        else:
            st.caption("Decisions unavailable.")
    except Exception:
        st.caption("Decisions unavailable.")

    st.divider()
    st.caption(f"Session `{st.session_state.session_id[:8]}…`")

    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages         = []
        st.session_state.pending_approval = None
        st.rerun()


# ── Page header ───────────────────────────────────────────────────────────────

st.markdown(
    """
    <div style="margin-bottom: 0.25rem;">
      <h1 style="margin-bottom:0; padding-bottom:0;">
        🏭 Smart Factory Operations Center
      </h1>
      <p style="margin-top:5px; font-size:0.88rem; opacity:0.65;">
        AI-powered IPC fleet management &mdash;
        human approval required before any action is recorded.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.divider()

# ── Starter prompts (empty conversation only) ─────────────────────────────────

if not st.session_state.messages:
    st.markdown("**Suggested prompts**")
    starters = [
        ("🔍 Fleet overview",    "Give me an overview of the fleet"),
        ("⚠️ At-risk IPCs",       "Which IPCs are most at risk right now?"),
        ("💤 Underutilized",      "What would you recommend about underutilized IPCs?"),
        ("🔴 Urgent actions",     "Are there any IPCs we should act on urgently?"),
        ("📋 Recent decisions",   "What decisions have been made recently?"),
        ("📈 IPC history",        "Show me the history for an IPC over the last 30 days"),
    ]
    cols = st.columns(3)
    for i, (label, prompt_text) in enumerate(starters):
        with cols[i % 3]:
            st.markdown('<div class="starter-btn">', unsafe_allow_html=True)
            if st.button(label, use_container_width=True, key=f"starter_{i}"):
                st.session_state._queued_prompt = prompt_text
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

# ── Conversation history ──────────────────────────────────────────────────────

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Approval card (shown when the agent is awaiting a decision) ───────────────

pending = st.session_state.pending_approval
if pending:
    proposals = pending.get("proposals", [])

    st.markdown(
        '<div class="approval-card"><h4>⚡ Recommendations awaiting your approval</h4>',
        unsafe_allow_html=True,
    )
    for p in proposals:
        ipc   = p.get("ipc_id", "—")
        label = p.get("label", "").lower()
        badge_cls = {
            "overloaded":   "badge badge-overloaded",
            "at_risk":      "badge badge-at_risk",
            "underutilized":"badge badge-underutil",
            "healthy":      "badge badge-healthy",
        }.get(label, "badge")
        desc  = p.get("description", "")[:100]
        st.markdown(
            f'<div class="proposal-row">'
            f'<strong>{ipc}</strong>'
            f'{"<span class=\\"" + badge_cls + "\\">" + label.replace("_"," ") + "</span>" if label else ""}'
            f'<br/><span style="font-size:0.85rem">{desc}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )

    approve_label = pending.get("approve_msg", "Approve all recommendations")
    reject_label  = pending.get("reject_msg",  "Reject all recommendations")

    b1, b2, _ = st.columns([2, 2, 4])
    with b1:
        approved = st.button("✅ Approve", use_container_width=True, key="approve_btn", type="primary")
    with b2:
        rejected = st.button("❌ Reject",  use_container_width=True, key="reject_btn")

    st.markdown("</div>", unsafe_allow_html=True)

    if approved:
        st.session_state.pending_approval  = None
        st.session_state._queued_prompt    = approve_label
        st.rerun()
    elif rejected:
        st.session_state.pending_approval  = None
        st.session_state._queued_prompt    = reject_label
        st.rerun()

# ── Queued prompt (starter buttons / approval buttons) ────────────────────────

if "_queued_prompt" in st.session_state:
    queued = st.session_state.pop("_queued_prompt")
    st.session_state.messages.append({"role": "user", "content": queued})
    with st.chat_message("user"):
        st.markdown(queued)
    with st.chat_message("assistant"):
        reply, needs_approval, proposals = _send_message(queued)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    if needs_approval:
        st.session_state.pending_approval = {
            "proposals":   proposals,
            "approve_msg": "Approve all recommendations",
            "reject_msg":  "Reject all recommendations",
        }
    st.rerun()

# ── Chat input ────────────────────────────────────────────────────────────────

if prompt := st.chat_input(
    "Ask about your IPC fleet…",
    disabled=bool(pending),
):
    st.session_state.pending_approval = None
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        reply, needs_approval, proposals = _send_message(prompt)

    st.session_state.messages.append({"role": "assistant", "content": reply})
    if needs_approval:
        st.session_state.pending_approval = {
            "proposals":   proposals,
            "approve_msg": "Approve all recommendations",
            "reject_msg":  "Reject all recommendations",
        }
        st.rerun()
