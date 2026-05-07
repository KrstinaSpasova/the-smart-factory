import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Smart Factory Operations Center", layout="wide")

# ---- session state bootstrap ----
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# ---- sidebar: fleet summary ----
with st.sidebar:
    st.header("Fleet Summary")
    if st.button("Refresh", key="refresh_summary"):
        st.session_state.pop("fleet_summary", None)

    if "fleet_summary" not in st.session_state:
        try:
            r = requests.get(f"{BACKEND_URL}/fleet/summary", timeout=10)
            st.session_state.fleet_summary = r.json() if r.ok else None
        except Exception:
            st.session_state.fleet_summary = None

    summary = st.session_state.get("fleet_summary")
    if summary:
        st.metric("Total IPCs", summary.get("total_ipcs", "—"))
        cols = st.columns(2)
        cols[0].metric("Healthy", summary.get("healthy", "—"))
        cols[1].metric("Underutilized", summary.get("underutilized", "—"))
        cols[0].metric("At Risk", summary.get("at_risk", "—"))
        cols[1].metric("Overloaded", summary.get("overloaded", "—"))
    else:
        st.caption("Fleet data unavailable — backend may be starting up.")

    st.divider()
    st.caption(f"Session: `{st.session_state.session_id[:8]}…`")

# ---- main chat ----
st.title("Smart Factory Operations Center")
st.caption(
    "Ask about your IPC fleet. The assistant will surface recommendations "
    "and ask for your approval before recording any decision."
)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask about your IPC fleet…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/chat",
                    json={
                        "message": prompt,
                        "session_id": st.session_state.session_id,
                    },
                    timeout=120,
                )
                resp.raise_for_status()
                reply = resp.json()["reply"]
            except requests.exceptions.Timeout:
                reply = "The backend is taking too long to respond. Please try again."
            except Exception as exc:
                reply = f"Error contacting backend: {exc}"
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
