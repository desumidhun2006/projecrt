import os
import json
import uuid
import base64
import sqlite3
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from groq import Groq
from playwright.sync_api import sync_playwright

# Configuration
DB_FILE = "ux_analyzer.db"
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Initialize Database
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS audits
                     (id TEXT PRIMARY KEY, 
                      url TEXT, 
                      timestamp TEXT, 
                      overall_score REAL, 
                      audit_data TEXT, 
                      screenshot_path TEXT)''')
        conn.commit()

# --- Data Access Layer ---

def get_history(limit=10):
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM audits ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        
        history = []
        for row in rows:
            # Reconstruct dictionary to match legacy format for frontend compatibility
            data = json.loads(row['audit_data'])
            data['id'] = row['id']
            data['url'] = row['url']
            data['timestamp'] = row['timestamp']
            data['overall_score'] = row['overall_score']
            data['screenshot_path'] = row['screenshot_path']
            history.append(data)
        return history[::-1] # Return in chronological order for some UI logic, or reverse in UI

def save_audit_to_db(audit_data):
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO audits (id, url, timestamp, overall_score, audit_data, screenshot_path) VALUES (?, ?, ?, ?, ?, ?)",
                  (audit_data['id'], 
                   audit_data['url'], 
                   audit_data['timestamp'], 
                   audit_data['overall_score'], 
                   json.dumps(audit_data), 
                   audit_data.get('screenshot_path')))
        conn.commit()

def clear_history():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    for f in SCREENSHOT_DIR.glob("*.png"):
        f.unlink()
    init_db()

# --- Core Logic Layer ---

def get_groq_client(api_key):
    if not api_key:
        raise ValueError("Groq API Key is missing. Please set it in Settings.")
    return Groq(api_key=api_key)

def capture_page(url):
    """Captures page content and screenshot using Playwright."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a generic user agent to avoid bot detection
        context = browser.new_context(viewport={"width": 1440, "height": 900}, user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        
        # Simulation: Scroll to trigger lazy loads
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)
        page.evaluate("window.scrollTo(0, 0)")
        
        html = page.content()
        screenshot_bytes = page.screenshot(full_page=True)
        browser.close()
        
    return html, screenshot_bytes

def analyze_ux_audit(url, rule_sets, api_key):
    html, screenshot_bytes = capture_page(url)
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(separator="\n", strip=True)[:7000]
    page_title = soup.title.string.strip() if soup.title else "No title"
    img_base64 = base64.b64encode(screenshot_bytes).decode()

    rule_desc = "\n\n".join([f"**{name}:**\n{rules}" for name, rules in rule_sets.items()])
    
    client = get_groq_client(api_key)
    system_prompt = "Return ONLY valid JSON. No extra text."
    user_prompt = f"""URL: {url}\nTitle: {page_title}\nText: {page_text[:4000]}\nRule sets: {rule_desc}\n\nPerform a simulation of 5 specific user personas walking through this page:\n1. Standard User\n2. Color Blind User\n3. Elderly User\n4. Motor Impairment\n5. Non-native Speaker.\n\nFor each persona, simulate a 60-second journey. Estimate frustration level (0-100). Return JSON:\n{{\n  "overall_score": float,\n  "persona_frustration_over_time": {{ "Standard": [{{"time": int, "frustration": int}}], ... }},\n  "summary": "Minimum 2000 words audit report...",\n  "persona_summaries": {{ "Standard": "...", ... }},\n  "issues": [{{ "title": "...", "description": "...", "severity": "Critical|High|Medium|Low", "affected_persona": "...", "category": "...", "recommendation": "..." }}]\n}}"""

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
    
    # Post-process scores
    frustration = analysis.get("persona_frustration_over_time", {})
    usability = 100 - (frustration.get("Standard", [{}])[-1].get('frustration', 50) if frustration.get("Standard") else 50)
    accessibility = 100 - (frustration.get("Motor Impairment", [{}])[-1].get('frustration', 50) if frustration.get("Motor Impairment") else 50)

    # Save artifacts
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = str(SCREENSHOT_DIR / f"{timestamp_str}.png")
    with open(screenshot_path, "wb") as f:
        f.write(screenshot_bytes)

    audit_data = {
        "id": str(uuid.uuid4()),
        "url": url,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "overall_score": round(analysis.get("overall_score", 50), 1),
        "usability_score": usability,
        "accessibility_score": accessibility,
        "persona_frustration_over_time": frustration,
        "persona_summaries": analysis.get("persona_summaries", {}),
        "summary": analysis.get("summary", ""),
        "issues": analysis.get("issues", []),
        "screenshot_path": screenshot_path
    }
    
    save_audit_to_db(audit_data)
    return audit_data

def compare_competitors(target_urls, selected_rule_sets, api_key):
    payloads = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for t_url in target_urls:
            if not t_url.startswith("http"): continue
            pg = browser.new_page(viewport={"width": 1280, "height": 800})
            pg.goto(t_url, wait_until="networkidle", timeout=60000)
            scr_bytes = pg.screenshot(full_page=True)
            txt_c = BeautifulSoup(pg.content(), "html.parser").get_text(separator="\n", strip=True)[:3000]
            pg.close()
            payloads.append({"url": t_url, "txt": txt_c, "img": base64.b64encode(scr_bytes).decode()})
        browser.close()

    client = get_groq_client(api_key)
    msgs = [{"type": "text", "text": f"Compare based on: {selected_rule_sets}. Return JSON: {{ 'winner': 'URL', 'comparison_report': '...', 'sites': [ {{ 'url': '...', 'score': 0-100, 'summary': '...', 'issues': [...] }} ] }}."}]
    for p_data in payloads:
        msgs.append({"type": "text", "text": f"URL: {p_data['url']}\n{p_data['txt']}"})
        msgs.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{p_data['img']}"}})

    resp = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role": "user", "content": msgs}],
        max_tokens=4000, temperature=0.2, response_format={"type": "json_object"}
    )
    return json.loads(resp.choices[0].message.content)

def detect_dark_patterns(url, api_key):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        html_content = page.content()
        screenshot_bytes = page.screenshot(full_page=True)
        browser.close()

    soup = BeautifulSoup(html_content, "html.parser")
    for s in soup(["script", "style", "svg"]): s.decompose()
    clean_html = soup.prettify()[:15000]

    client = get_groq_client(api_key)
    sys_prompt = "You are a Dark Pattern Detector. Evaluate against ethical heuristics. Return JSON: { 'url': '...', 'manipulation_score': 0-100, 'summary': '...', 'analyzed_html_snippet': '...', 'patterns': [{ 'name': '...', 'description': '...', 'code_snippet': '...', 'ethical_alternative': '...' }] }"
    user_msg = f"URL: {url}\nHTML:\n{clean_html}"
    
    resp = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        temperature=0.3
    )
    result = json.loads(resp.choices[0].message.content)
    
    # Save to history via DB logic (optional mapping)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = str(SCREENSHOT_DIR / f"{timestamp_str}.png")
    with open(screenshot_path, "wb") as f:
        f.write(screenshot_bytes)
        
    audit_data = {
        "id": str(uuid.uuid4()),
        "url": url,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "overall_score": 100 - result.get('manipulation_score', 0),
        "summary": result.get('summary', ''),
        "issues": [], # Simplified for this mode
        "screenshot_path": screenshot_path,
        "dark_pattern_result": result # Custom field
    }
    save_audit_to_db(audit_data)
    return result

def ask_ai_followup(question, audit_context, api_key):
    client = get_groq_client(api_key)
    # Truncate context to save tokens
    context_str = json.dumps(audit_context, indent=2)[:4000]
    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {"role": "system", "content": "You are an expert UX consultant. Answer based on context."},
            {"role": "user", "content": f"Context: {context_str}\n\nQuestion: {question}"}
        ],
        max_tokens=1000,
        temperature=0.3
    )
    return response.choices[0].message.content
