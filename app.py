import streamlit as st
import os
import pandas as pd
import backend  # Import the new backend service

# ====================== API KEY SETUP ======================
# Try to get from Environment (Best for Docker/Cloud), then Streamlit Secrets, then Fallback
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY") or "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"

# ====================== CONFIG ======================
st.set_page_config(
    page_title="UX Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("UX Analyzer")

# Initialize DB on app start
backend.init_db()

# ====================== ANALYSIS MODE ======================
analysis_mode = st.radio(
    "Mode",
    ["AI-Persona Simulation", "Competitor Comparison", "Dark Pattern Detector"]
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
    
    st.divider()
    st.subheader("History")
    
    history = backend.get_history(limit=15)
    
    if history:
        for audit in reversed(history[-10:]):
            label = f"{audit['url'][:30]}... ({audit.get('overall_score', 0):.0f}%)"
            if st.button(label, key=f"load_{audit['id']}"):
                st.session_state.current_audit = audit
                st.rerun()
    else:
        st.text("No history.")

    if history and st.button("Clear History", type="secondary"):
        backend.clear_history()
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
        if question.strip() and GROQ_API_KEY:
            with st.spinner("Thinking..."):
                try:
                    answer = backend.ask_ai_followup(question, audit, GROQ_API_KEY)
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

elif "dark_pattern_result" in st.session_state and st.session_state.dark_pattern_result:
    res = st.session_state.dark_pattern_result
    st.subheader("🕵️‍♀️ Dark Pattern & Manipulation Report")
    
    # Manipulation Score Gauge
    score = res.get('manipulation_score', 0)
    st.progress(score / 100, text=f"Manipulation Score: {score}/100 (High = Unethical)")
    
    st.markdown("### Executive Summary")
    st.write(res.get('summary', ''))

    st.subheader("Source Code Analysis")
    with st.expander("View Analyzed Source Code Snippets", expanded=False):
        st.code(res.get('analyzed_html_snippet', '<!-- No snippet returned -->'), language='html')

    st.subheader("Detected Patterns & Ethical Alternatives")
    for p in res.get('patterns', []):
        with st.expander(f"🚫 {p.get('name', 'Unknown Pattern')}"):
            st.markdown(f"**Description:** {p.get('description')}")
            st.markdown("**Violating Code:**")
            st.code(p.get('code_snippet', ''), language='html')
            st.success(f"**✅ Ethical Alternative:** {p.get('ethical_alternative')}")

    if st.button("New Analysis", type="primary"):
        del st.session_state.dark_pattern_result
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

        if st.button("Compare Sites", type="primary", disabled=len(target_urls) < 2 or not selected_sets or not GROQ_API_KEY):
            with st.spinner("Analyzing competitors..."):
                try:
                    # Call Backend
                    res = backend.compare_competitors(target_urls, selected_sets, GROQ_API_KEY)
                    st.session_state.comparison_result = res
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    elif analysis_mode == "Dark Pattern Detector":
        url = st.text_input("URL", placeholder="https://example.com")
        if st.button("Detect Dark Patterns", type="primary", disabled=not url or not GROQ_API_KEY):
             with st.spinner("Inspecting source code for manipulation tactics..."):
                try:
                    result = backend.detect_dark_patterns(url, GROQ_API_KEY)
                    st.session_state.dark_pattern_result = result
                    st.rerun()

                except Exception as e:
                    st.error(f"Analysis failed: {str(e)}")

    else:
        url = st.text_input("URL", placeholder="https://")
    
        if st.button("Analyze", type="primary", use_container_width=True, disabled=not selected_sets or not GROQ_API_KEY):
            if not url.startswith(("http://", "https://")):
                st.error("Invalid URL")
            else:
                with st.spinner("Analyzing..."):
                    try:
                        # Call Backend
                        # We pass the full dictionary of selected rules if needed, 
                        # but the backend expects {Name: Description}
                        chosen_rules = {k: rule_sets[k] for k in selected_sets}
                        audit_data = backend.analyze_ux_audit(url, chosen_rules, GROQ_API_KEY)
                        
                        # Show immediately
                        st.session_state.current_audit = audit_data
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))
