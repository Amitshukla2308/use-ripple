"""
web_tools.py — Web search and fetch capabilities.
"""
import urllib.request
import urllib.error
import urllib.parse
import json
import re

def web_search(query: str, max_results: int = 5) -> str:
    """Uses the local SearxNG instance for clean JSON results."""
    url = f"http://localhost:8080/search?q={urllib.parse.quote(query)}&format=json"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = []
            
            for item in data.get("results", [])[:max_results]:
                href = item.get("url", "")
                snippet = item.get("content", "")
                title = item.get("title", "")
                if snippet or title:
                    results.append(f"Title: {title}\nLink: {href}\nSnippet: {snippet}")
            
            if not results:
                return "No useful results parsed. Check manual."
            return "\n\n".join(results)
    except Exception as e:
        return f"Search error: {e}"

def web_fetch(url: str) -> str:
    """Fetch URL and strip basic HTML to get text content, navigating SPA apps correctly via Playwright."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return "Fetch error: The 'playwright' library is not installed. Please run `pip install playwright && playwright install chromium`."
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page = context.new_page()
            
            try:
                # Wait until network is idle to ensure React/Vue apps load their content
                page.goto(url, wait_until="networkidle", timeout=15000)
            except PlaywrightTimeout:
                # Keep going, the page might have loaded enough text content already
                pass
                
            # Extract just the raw text rendered on screen
            text = page.locator("body").inner_text()
            browser.close()
            
            # Clean up excessive whitespace and cap to a reasonable token length
            text = "\n".join([line.strip() for line in text.splitlines() if line.strip()][:1000])
            return text or "No viewable text content found on the page."
    except Exception as e:
        return f"Fetch error: {e}"
