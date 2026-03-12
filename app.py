import streamlit as st
from groq import Groq
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import base64
import json
import os
from datetime import datetime
from pathlib import Path
import uuid
import pandas as pd

# ====================== CONFIG ======================
st.set_page_config(
    page_title="UX Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("UX Analyzer")

# ====================== FOLDERS & HISTORY FILE ======================
Path("screenshots").mkdir(exist_ok=True)
HISTORY_FILE = "audits_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

# ====================== ANALYSIS MODE ======================
analysis_mode = st.radio(
    "Mode",
    ["AI-Persona Simulation", "Competitor Comparison"]
)

# ====================== RULE SETS (Home Page) ======================
rule_sets = {
    "Nielsen's 10 Usability Heuristics": """1. Visibility of system status
2. Match between system and the real world
3. User control and freedom
4. Consistency and standards
5. Error prevention
6. Recognition rather than recall
7. Flexibility and efficiency of use
8. Aesthetic and minimalist design
9. Help users recognize, diagnose, and recover from errors
10. Help and documentation""",

    "Shneiderman's 8 Golden Rules": """1. Strive for consistency
2. Enable frequent users to use shortcuts
3. Offer informative feedback
4. Design dialog to yield closure
5. Offer simple error handling
6. Permit easy reversal of actions
7. Support internal locus of control
8. Reduce short-term memory load""",

    "Gerhardt-Powals' Cognitive Principles": """1. Automate unwanted workload
2. Reduce uncertainty
3. Fuse data
4. Present new information with meaningful aids
5. Limit data-driven tasks
6. Minimize mental effort""",

    "WCAG Accessibility (POUR)": """Perceivable – information and UI components must be presentable
Operable – UI components and navigation must be operable
Understandable – information and operation must be understandable
Robust – content must be robust enough"""
}

all_selected = st.checkbox("Select All Rules", value=True)

if all_selected:
    selected_sets = list(rule_sets.keys())
else:
    selected_sets = st.multiselect(
        "Select Rules",
        options=list(rule_sets.keys()),
        default=["Nielsen's 10 Usability Heuristics"]
    )

if not selected_sets:
    st.warning("Select a rule set")

# ====================== SIDEBAR ======================
with st.sidebar:
    if st.button("➕ New Audit", type="primary", use_container_width=True):
        st.session_state.current_audit = None
        if "comparison_result" in st.session_state:
            del st.session_state.comparison_result
        if "comp_urls" in st.session_state:
            st.session_state.comp_urls = ["", ""]
        st.rerun()

    st.subheader("Rules")
    for s in selected_sets:
        st.markdown(f"- {s}")

    st.divider()
    
    groq_key = "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"

    st.divider()
    st.subheader("History")
    
    history = load_history()
    
    if history:
        for audit in reversed(history[-10:]):
            label = f"{audit['url'][:30]}... ({audit.get('overall_score', 0):.0f}%)"
            if st.button(label, key=f"load_{audit['id']}"):
                st.session_state.current_audit = audit
                st.rerun()
    else:
        st.text("No history.")

    if history and st.button("Clear History", type="secondary"):
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
        for f in Path("screenshots").glob("*.png"):
            f.unlink()
        st.session_state.pop("current_audit", None)
        st.rerun()

# ====================== MAIN AREA ======================
if "current_audit" in st.session_state and st.session_state.current_audit:
    # ================== VIEWING PAST OR CURRENT AUDIT ==================
    audit = st.session_state.current_audit
    st.markdown(f"**{audit['url']}**")

    # Scores at top
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Overall", f"{audit.get('overall_score', 0):.0f}%")
    with col2:
        st.metric("Usability", f"{audit.get('usability_score', 0):.0f}%")
    with col3:
        st.metric("Accessibility", f"{audit.get('accessibility_score', 0):.0f}%")

    # Persona Scores (New Feature)
    if "persona_frustration_over_time" in audit:
        st.divider()
        st.subheader("Persona Frustration Levels Over Time")
        frustration_data = audit["persona_frustration_over_time"]

        all_series = []
        for persona, data_points in frustration_data.items():
            if data_points:
                # Create a pandas Series for each persona with time as the index
                s = pd.Series(
                    [dp['frustration'] for dp in data_points],
                    index=[dp['time'] for dp in data_points],
                    name=persona
                )
                all_series.append(s)

        if all_series:
            # Combine all series into a single DataFrame, sort by time, and fill gaps
            combined_df = pd.concat(all_series, axis=1).sort_index().ffill().bfill()
            st.line_chart(combined_df)

        # Persona Walkthrough Summaries
        if "persona_summaries" in audit:
            with st.expander("Walkthroughs"):
                for p_name, p_summary in audit["persona_summaries"].items():
                    st.markdown(f"**{p_name}:** {p_summary}")

    # Screenshot (if exists)
    screenshot_path = audit.get("screenshot_path")
    if screenshot_path and os.path.exists(screenshot_path):
        st.divider()
        st.image(screenshot_path, use_column_width=True)

    # Summary
    st.subheader("Summary")
    st.markdown(audit.get("summary", "No summary saved"))

    # Severity boxes
    st.subheader("Severity")
    issues = audit.get("issues", [])
    c = sum(1 for i in issues if i.get("severity", "").lower() == "critical")
    h = sum(1 for i in issues if i.get("severity", "").lower() == "high")
    m = sum(1 for i in issues if i.get("severity", "").lower() == "medium")
    l = sum(1 for i in issues if i.get("severity", "").lower() == "low")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Critical", c)
    col2.metric("High", h)
    col3.metric("Medium", m)
    col4.metric("Low", l)

    # Issues tabs
    st.subheader("Issues")
    
    personas_found = list(set(i.get("affected_persona", "General") for i in issues))
    personas_found.sort()
    tabs = st.tabs(["All"] + personas_found)
    
    def render_issues(filtered):
        if not filtered:
            st.text("None")
            return
        for issue in filtered:
            sev = issue.get("severity", "Medium").capitalize()
            emoji = {"Critical":"🔴","High":"🟠","Medium":"🟡","Low":"🟢"}.get(sev,"⚪")
            affected = issue.get("affected_persona", "General")
            with st.expander(f"{emoji} {issue.get('title')}"):
                st.write(issue.get('description'))
                st.write(f"**Fix:** {issue.get('recommendation')}")
                st.caption(f"{affected} | {issue.get('category')}")

    with tabs[0]: render_issues(issues)
    for i, p_name in enumerate(personas_found):
        with tabs[i+1]:
            render_issues([x for x in issues if x.get("affected_persona", "General") == p_name])

    # ====================== FOLLOW-UP AI TEXTBOX (for EVERY audit) ======================
    st.divider()
    question = st.text_area("Ask AI", placeholder="Question...", height=100)
    
    if st.button("Ask", type="primary", use_container_width=True):
        if question.strip() and groq_key:
            with st.spinner("Thinking..."):
                try:
                    client = Groq(api_key=groq_key)
                    
                    # Build rich context
                    p_context = json.dumps(audit.get('persona_scores', {}), indent=2)
                    context = f"""Website: {audit['url']}
Timestamp: {audit['timestamp']}
Scores: Overall {audit.get('overall_score'):.0f}%
Persona Scores: {p_context}
Summary: {audit.get('summary', '')[:1200]}
Issues: {json.dumps(audit.get('issues', []), indent=2)[:1800]}"""

                    response = client.chat.completions.create(
                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                        messages=[
                            {"role": "system", "content": "You are an expert UX consultant. Answer based ONLY on the previous analysis provided in context."},
                            {"role": "user", "content": f"{context}\n\nUser question: {question}"}
                        ],
                        max_tokens=1200,
                        temperature=0.3
                    )
                    answer = response.choices[0].message.content
                    st.markdown("### Answer")
                    st.markdown(answer)
                except Exception as e:
                    st.error(f"Could not get answer: {str(e)}")
        else:
            st.warning("Please enter a question and make sure your Groq key is set")

elif "comparison_result" in st.session_state and st.session_state.comparison_result:
    res = st.session_state.comparison_result
    st.subheader("⚔️ Competitor Comparison")
    
    st.success(f"**Winner:** {res.get('winner', 'N/A')}")
    st.markdown("### Comparison Report")
    st.write(res.get('comparison_report', ''))
    
    st.divider()
    st.subheader("Detailed Site Analysis")
    
    for site in res.get('sites', []):
        with st.expander(f"{site.get('url')} (Score: {site.get('score', 0):.0f}%)"):
            st.write(site.get('summary', ''))
            st.markdown("**Issues:**")
            for issue in site.get('issues', []):
                sev = issue.get('severity', 'Medium')
                st.markdown(f"- **[{sev}] {issue.get('title')}**: {issue.get('description')}")
    
    if st.button("New Analysis", type="primary"):
        del st.session_state.comparison_result
        st.rerun()

else:
    # ================== NEW ANALYSIS MODE ==================
    if analysis_mode == "Competitor Comparison":
        if "comp_urls" not in st.session_state:
            st.session_state.comp_urls = ["", ""]

        for i in range(len(st.session_state.comp_urls)):
            st.session_state.comp_urls[i] = st.text_input(f"URL {i+1}", value=st.session_state.comp_urls[i], placeholder="https://", key=f"comp_url_{i}")

        def add_url_field():
            st.session_state.comp_urls.append("")

        if len(st.session_state.comp_urls) < 3:
            st.button("Add another link", on_click=add_url_field)
        else:
            st.caption("Maximum limit of 3 URLs reached")

        target_urls = [u for u in st.session_state.comp_urls if u.strip()]

        if st.button("Compare Sites", type="primary", disabled=len(target_urls) < 2 or not selected_sets or not groq_key):
            with st.spinner("Analyzing competitors..."):
                try:
                    payloads = []
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        for t_url in target_urls:
                            if not t_url.startswith("http"): continue
                            pg = browser.new_page(viewport={"width": 1280, "height": 800})
                            pg.goto(t_url, wait_until="networkidle", timeout=60000)
                            pg.evaluate("window.scrollTo(0, 500)")
                            pg.wait_for_timeout(500)
                            scr_bytes = pg.screenshot(full_page=True)
                            html_c = pg.content()
                            pg.close()
                            
                            soup_c = BeautifulSoup(html_c, "html.parser")
                            txt_c = soup_c.get_text(separator="\n", strip=True)[:3000]
                            payloads.append({"url": t_url, "txt": txt_c, "img": base64.b64encode(scr_bytes).decode()})
                        browser.close()

                    client = Groq(api_key=groq_key)
                    msgs = [{"type": "text", "text": f"Compare these websites based on: {selected_sets}. Return JSON: {{ 'winner': 'URL', 'comparison_report': 'Detailed text comparing the sites...', 'sites': [ {{ 'url': '...', 'score': 0-100, 'summary': '...', 'issues': [ {{ 'title': '...', 'severity': 'Critical|High|Medium|Low', 'description': '...' }} ] }} ] }}."}]
                    for p_data in payloads:
                        msgs.append({"type": "text", "text": f"URL: {p_data['url']}\n{p_data['txt']}"})
                        msgs.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{p_data['img']}"}})

                    resp = client.chat.completions.create(
                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                        messages=[{"role": "user", "content": msgs}],
                        max_tokens=4000, temperature=0.2, response_format={"type": "json_object"}
                    )
                    st.session_state.comparison_result = json.loads(resp.choices[0].message.content)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    else:
        url = st.text_input("URL", placeholder="https://")
    
        if st.button("Analyze", type="primary", use_container_width=True, disabled=not selected_sets or not groq_key):
            if not url.startswith(("http://", "https://")):
                st.error("Invalid URL")
            else:
                with st.spinner("Analyzing..."):
                    try:
                        # Screenshot with Playwright
                        with sync_playwright() as p:
                            browser = p.chromium.launch(headless=True)
                            page = browser.new_page(viewport={"width": 1440, "height": 900})
                            page.goto(url, wait_until="networkidle", timeout=60000)
                            
                            # Simulate user interaction (scroll/zoom actions) for personas
                            # This ensures lazy loaded elements are present and mimics a "walk through"
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            page.wait_for_timeout(1000)
                            page.evaluate("window.scrollTo(0, 0)")
                            page.wait_for_timeout(500)
                            
                            html = page.content()
                            screenshot_bytes = page.screenshot(full_page=True)
                            browser.close()

                        soup = BeautifulSoup(html, "html.parser")
                        page_text = soup.get_text(separator="\n", strip=True)[:7000]
                        page_title = soup.title.string.strip() if soup.title else "No title"

                        img_base64 = base64.b64encode(screenshot_bytes).decode()

                        # Rule description
                        rule_desc = "\n\n".join([f"**{name}:**\n{rule_sets[name]}" for name in selected_sets])

                        client = Groq(api_key=groq_key)

                        system_prompt = "Return ONLY valid JSON. No extra text."
                        user_prompt = f"""URL: {url}
Title: {page_title}
Text: {page_text[:4000]}
Rule sets: {rule_desc}

Perform a simulation of 5 specific user personas walking through this page:
1. Standard User
2. Color Blind User (assess color contrast, reliance on color)
3. Elderly User (small text, complex navigation, confusing flows)
4. Motor Impairment (small click targets, keyboard navigation needs)
5. Non-native Speaker (idioms, complex language, unclear icons).

For each persona, simulate a 60-second journey. Estimate their frustration level (0=calm, 100=quits) over time. Record data points at key moments of interaction or confusion.

Return exactly this JSON:
{{
  "overall_score": float (0-100),
  "persona_frustration_over_time": {{
    "Standard": [{{"time": int (seconds), "frustration": int (0-100)}}],
    "Color Blind": [{{"time": int (seconds), "frustration": int (0-100)}}],
    "Elderly": [{{"time": int (seconds), "frustration": int (0-100)}}],
    "Motor Impairment": [{{"time": int (seconds), "frustration": int (0-100)}}],
    "Non-native Speaker": [{{"time": int (seconds), "frustration": int (0-100)}}]
  }},
  "summary": "2-3 paragraph summary",
  "persona_summaries": {{ "Standard": "...", "Color Blind": "...", "Elderly": "...", "Motor Impairment": "...", "Non-native Speaker": "..." }},
  "issues": [{{ "title": "...", "description": "...", "severity": "Critical|High|Medium|Low", "affected_persona": "Standard|Color Blind|Elderly|Motor Impairment|Non-native Speaker", "category": "Usability|Accessibility", "recommendation": "..." }}]
}}"""

                        response = client.chat.completions.create(
                            model="meta-llama/llama-4-scout-17b-16e-instruct",
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": [
                                    {"type": "text", "text": user_prompt},
                                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                                ]}
                            ],
                            max_tokens=4500,
                            temperature=0.25,
                            response_format={"type": "json_object"}
                        )

                        analysis = json.loads(response.choices[0].message.content)

                        # Save screenshot
                        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        screenshot_path = f"screenshots/{timestamp_str}.png"
                        with open(screenshot_path, "wb") as f:
                            f.write(screenshot_bytes)

                        # Calculate usability/accessibility scores from final frustration
                        frustration_data = analysis.get("persona_frustration_over_time", {})
                        std_frustration = frustration_data.get("Standard", [])
                        motor_frustration = frustration_data.get("Motor Impairment", [])
                        
                        final_std_frustration = std_frustration[-1]['frustration'] if std_frustration else 50
                        final_motor_frustration = motor_frustration[-1]['frustration'] if motor_frustration else 50

                        usability_score = 100 - final_std_frustration
                        accessibility_score = 100 - final_motor_frustration

                        # Build audit record
                        audit_data = {
                            "id": str(uuid.uuid4()),
                            "url": url,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "overall_score": round(analysis.get("overall_score", 50), 1),
                            "usability_score": usability_score,
                            "accessibility_score": accessibility_score,
                            "persona_frustration_over_time": frustration_data,
                            "persona_summaries": analysis.get("persona_summaries", {}),
                            "summary": analysis.get("summary", ""),
                            "issues": analysis.get("issues", []),
                            "selected_rule_sets": selected_sets,
                            "screenshot_path": screenshot_path
                        }

                        # Save to history
                        history = load_history()
                        history.append(audit_data)
                        if len(history) > 30:
                            history = history[-30:]
                        save_history(history)

                        # Show immediately
                        st.session_state.current_audit = audit_data
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))
