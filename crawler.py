import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from typing import Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def fetch_page(url: str, page=None) -> Optional[BeautifulSoup]:
    """
    Fetch a webpage using an existing Playwright page object (fast), or launch one if None (slow).
    Bypasses JavaScript-only blockers and Cloudflare basic challenges.
    """
    if not url.startswith('http'):
        url = 'https://' + url

    try:
        if page:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            html_content = page.content()
            return BeautifulSoup(html_content, 'lxml')
        else:
            # Fallback for standalone calls without a managed browser context
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )
                new_page = context.new_page()
                new_page.goto(url, wait_until="domcontentloaded", timeout=20000)
                new_page.wait_for_timeout(2000)
                html_content = new_page.content()
                browser.close()
                return BeautifulSoup(html_content, 'lxml')
            
    except PlaywrightTimeoutError:
        print(f"Error fetching {url}: Page load timed out after 20 seconds.")
        return None
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def find_relevant_pages(soup: BeautifulSoup, base_url: str) -> dict:
    """
    Look for a contact and about page link in the HTML via fast keyword matching.
    """
    if not soup:
        return {"contact_url": None, "about_url": None}
        
    contact_url = None
    about_url = None
    
    CONTACT_KEYWORDS = ['contact', 'reach', 'get-in-touch', 'connect']
    ABOUT_KEYWORDS = ['about', 'team', 'our-story', 'who-we-are', 'our-company']
    
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        text = a_tag.get_text(strip=True).lower()
        
        if href.lower().startswith(('mailto:', 'tel:', 'javascript:')):
            continue
            
        full_url = urljoin(base_url, href)
        
        # Stop looking if both are found
        if contact_url and about_url:
            break
            
        # Match keywords in either the visible text or the URL structure
        search_string = (text + " " + href).lower()
        
        if not contact_url and any(k in search_string for k in CONTACT_KEYWORDS):
            contact_url = full_url
            
        if not about_url and any(k in search_string for k in ABOUT_KEYWORDS):
            about_url = full_url
            
    return {"contact_url": contact_url, "about_url": about_url}

if __name__ == "__main__":
    # Test block
    test_url = "https://www.google.com"
    print(f"Testing fetch_page for {test_url}...")
    soup = fetch_page(test_url)
    
    if soup:
        print(f"Successfully fetched! Page title: {soup.title.string if soup.title else 'No Title'}")
        
        print(f"Looking for relevant pages via LLM...")
        pages = find_relevant_pages(soup, test_url)
        print(f"Pages found: {pages}")
    else:
        print("Failed to fetch page.")
