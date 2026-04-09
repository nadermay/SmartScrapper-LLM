import re
import json
from bs4 import BeautifulSoup
from typing import Optional, List

def extract_emails(soup: BeautifulSoup) -> List[str]:
    """
    Extracts emails from a parsed BeautifulSoup object.
    First checks 'mailto:' links, then falls back to regex on the text content.
    """
    if not soup:
        return []
        
    emails = set()
    
    # 1. Check for mailto: links (most reliable)
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if href.lower().startswith('mailto:'):
            # Extract email from mailto:email@domain.com
            email_part = href[7:].split('?')[0].strip()  # Cut off any ?subject=...
            if email_part:
                emails.add(email_part)
                
    # 2. Check text content with regex
    # Common email regex pattern
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    
    text_content = soup.get_text(separator=' ')
    found_emails = re.findall(email_pattern, text_content)
    
    for email in found_emails:
        # Filter out obvious false positives and image extensions
        email_lower = email.lower()
        if not any(email_lower.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']):
            emails.add(email)
            
    return list(emails)

def extract_phones(soup: BeautifulSoup) -> List[str]:
    """
    Extracts phone numbers from a parsed BeautifulSoup object.
    Checks 'tel:' links first, then uses regex on text content.
    """
    if not soup:
        return []
        
    phones = set()
    
    # 1. Check for tel: links
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if href.lower().startswith('tel:'):
            phone_part = href[4:].strip()
            # Clean up the number
            clean_phone = re.sub(r'[^\d+]', '', phone_part)
            if len(clean_phone) >= 10:
                phones.add(clean_phone)
                
    # 2. Check text content with regex
    # Matches common US and international formats: (123) 456-7890 | 123-456-7890 | +1 123 456 7890
    phone_pattern = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    
    text_content = soup.get_text(separator=' ')
    found_phones = re.findall(phone_pattern, text_content)
    
    for phone in found_phones:
        # Skip numeric strings that look like zip codes or years
        if len(re.sub(r'[^\d]', '', phone)) >= 10:
            phones.add(phone.strip())
            
    return list(phones)

def extract_socials(soup: BeautifulSoup) -> dict:
    """
    Extracts social media links from a parsed BeautifulSoup object.
    Focuses on LinkedIn (company), Facebook, Instagram, and Twitter/X.
    """
    socials = {
        "LinkedIn": "Not Found",
        "Facebook": "Not Found",
        "Instagram": "Not Found",
        "Twitter": "Not Found"
    }
    
    if not soup:
        return socials
        
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        href_lower = href.lower()
        
        # LinkedIn
        if 'linkedin.com/company' in href_lower or 'linkedin.com/in' in href_lower:
            socials['LinkedIn'] = href
        # Facebook
        elif 'facebook.com' in href_lower and 'sharer' not in href_lower:
            socials['Facebook'] = href
        # Instagram
        elif 'instagram.com' in href_lower:
            socials['Instagram'] = href
        # Twitter / X
        elif ('twitter.com' in href_lower or 'x.com' in href_lower) and 'intent' not in href_lower and 'share' not in href_lower:
            socials['Twitter'] = href
            
    return socials

def extract_location(soup: BeautifulSoup) -> Optional[str]:
    """
    Tries to extract a physical location/address from a parsed BeautifulSoup object.
    Uses JSON-LD schema, maps links, <address> tags, footers, and regex.
    """
    if not soup:
        return None
        
    # 1. Check JSON-LD schema (Highly reliable for businesses)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            # JSON-LD can be a single object or a list of objects
            schemas = data if isinstance(data, list) else [data]
            
            for schema in schemas:
                if isinstance(schema, dict) and 'address' in schema:
                    address = schema['address']
                    if isinstance(address, dict):
                        parts = [
                            address.get('streetAddress', ''),
                            address.get('addressLocality', ''),
                            address.get('addressRegion', ''),
                            address.get('postalCode', '')
                        ]
                        valid_parts = [str(p).strip() for p in parts if p]
                        if valid_parts:
                            return ", ".join(valid_parts)
                    elif isinstance(address, str):
                        return address.strip()
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    # 2. Check Google Maps links
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].lower()
        if 'google.com/maps' in href or 'maps.google.com' in href or 'maps.app.goo.gl' in href:
            text = a_tag.get_text(separator=' ', strip=True)
            # If the link text contains numbers, it's likely the address
            if len(text) > 10 and any(char.isdigit() for char in text):
                return text
                
    # 3. Look for explicit <address> tags
    address_tags = soup.find_all('address')
    if address_tags:
        best_candidate = " ".join(address_tags[0].get_text(separator=' ', strip=True).split())
        if len(best_candidate) > 10 and any(char.isdigit() for char in best_candidate):
            return best_candidate
            
    # 4. Check footer section for keywords
    footer = soup.find('footer')
    if footer:
        footer_text = footer.get_text(separator=' ', strip=True)
        keywords = ['Headquarters', 'HQ', 'Address', 'Location', 'St.', 'Street', 'Ave', 'Avenue', 'Blvd', 'Rd', 'Road']
        
        if any(kw.lower() in footer_text.lower() for kw in keywords):
            chunks = footer.get_text(separator='\n', strip=True).split('\n')
            for chunk in chunks:
                if 10 < len(chunk) < 150 and any(char.isdigit() for char in chunk):
                    if any(kw.lower() in chunk.lower() for kw in keywords):
                        return " ".join(chunk.split())
                        
    # 5. Last resort: Regex for US-style physical addresses in general text
    # Matches "123 Main St" or "12345 Corporate Drive, Suite 100"
    address_pattern = r'\b\d{1,5}\s+(?:[A-Za-z0-9#-]+\s+){1,4}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|Suite|Ste)\b'
    text_content = soup.get_text(separator=' ', strip=True)
    match = re.search(address_pattern, text_content, re.IGNORECASE)
    if match:
        return " ".join(match.group(0).split())

    return None

def clean_text_for_llm(soup: BeautifulSoup) -> str:
    """
    Cleans a BeautifulSoup object to extract text suitable for an LLM context window.
    Removes headers, footers, scripts, and standardizes spacing.
    """
    if not soup:
        return ""
        
    # Copy soup to avoid modifying the original if it's used elsewhere
    import copy
    soup_copy = copy.copy(soup)
    
    # Remove unwanted tags that clutter the text with navigation/formatting noise
    for element in soup_copy(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        element.extract()
        
    text = soup_copy.get_text(separator=' ', strip=True)
    # Collapse multiple whitespace characters into a single space
    clean_text = re.sub(r'\s+', ' ', text)
    
    return clean_text
