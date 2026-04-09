import os
import sys
import json
import csv
import argparse
import concurrent.futures

from discovery import find_official_website
from crawler import fetch_page, find_relevant_pages
from extractor import extract_emails, extract_phones, extract_socials, extract_location, clean_text_for_llm
from llm_processor import analyze_lead_full

import threading
thread_local = threading.local()
_original_print = print

def print(*args, **kwargs):
    msg = " ".join([str(a) for a in args])
    job_id = getattr(thread_local, 'job_id', None)
    if job_id:
        try:
            from sse_logger import job_logger
            level = "info"
            lower_msg = msg.lower()
            if "fail" in lower_msg or "error" in lower_msg or "[!]" in msg:
                level = "error"
            elif "[+]" in msg or "success" in lower_msg or "[*]" in msg or "finish" in lower_msg:
                level = "success"
            job_logger.log(job_id, msg, level)
        except ImportError:
            pass
    _original_print(*args, **kwargs)

def scrape_company(company_name: str, manual_url: str = None) -> dict:
    """
    Orchestrates the scraping process for a single company.
    Phase A: Find website
    Phase B: Crawl homepage
    Phase C: Extract data & potentially crawl contact page
    """
    result = {
        "company_name": company_name,
        "website_link": "Not Found",
        "email": "Not Found",
        "phone": "Not Found",
        "location": "Not Found",
        "socials": {
            "LinkedIn": "Not Found",
            "Facebook": "Not Found",
            "Instagram": "Not Found",
            "Twitter": "Not Found"
        },
        "niche": "Not Analyzed",
        "summary": "Not Analyzed",
        "decision_maker": "Not Assessed",
        "opening_line": "Not Generated",
        "pitch_angle": "Not Analyzed",
        "status": "Failed"
    }
        
    print(f"\n--- Scraping info for: {company_name} ---")
    
    # Phase A: Discovery
    if manual_url:
        website = manual_url
        print(f"[*] Skipping discovery, using manual URL: {website}")
    else:
        print("[Phase A] Looking for official website...")
        website = find_official_website(company_name)
        if not website:
            print("Could not find official website.")
            result["status"] = "Missing_Website"
            return result
        
    print(f"Found website: {website}")
    result["website_link"] = website # Keep the bug fix as it's essential data
    
    # Phase B: Crawling Homepage
    print("[Phase B] Fetching homepage...")
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        soup = fetch_page(website, page=page)
        if not soup:
            print("Failed to fetch homepage HTML.")
            browser.close()
            return result
            
        emails = []
        phones = []
        location = None
        socials = {}
        contact_url = None
        
        # Phase C: Extraction on Homepage
        print("[Phase C] Extracting data from homepage...")
        emails.extend(extract_emails(soup))
        phones.extend(extract_phones(soup))
        socials = extract_socials(soup)
        location = extract_location(soup)
        
        print("Looking for Contact and About pages...")
        pages = find_relevant_pages(soup, website)
        
        contact_url = pages.get("contact_url")
        about_url = pages.get("about_url")
        
        about_text = ""
        
        if contact_url and contact_url != "null":
            print(f"Fetching contact page: {contact_url}")
            contact_soup = fetch_page(contact_url, page=page)
            if contact_soup:
                emails.extend(extract_emails(contact_soup))
                phones.extend(extract_phones(contact_soup))
                for platform, link in extract_socials(contact_soup).items():
                    if link != "Not Found" and socials.get(platform, "Not Found") == "Not Found":
                        socials[platform] = link
                if not location:
                    location = extract_location(contact_soup)

        if about_url and about_url != "null" and about_url != contact_url:
            print(f"Fetching about page: {about_url}")
            about_soup = fetch_page(about_url, page=page)
            if about_soup:
                about_text = clean_text_for_llm(about_soup)
                
        browser.close()
            
    # Phase D: LLM Enrichment
    print("[Phase D] LLM Lead Intelligence...")
    home_text = clean_text_for_llm(soup)
    combined_text = home_text + "\n\n" + about_text
    
    analysis = analyze_lead_full(combined_text)
    
    result["niche"] = analysis.get("niche", "Unknown")
    result["summary"] = analysis.get("summary", "None")
    result["pitch_angle"] = analysis.get("pitch_angle", "Unknown")
    
    dm_name = analysis.get("decision_maker_name")
    dm_title = analysis.get("decision_maker_title")
    if dm_name and dm_name != "null":
        result["decision_maker"] = f"{dm_name} ({dm_title})" if dm_title and dm_title != "null" else dm_name
    else:
        result["decision_maker"] = "Unknown"
        
    result["opening_line"] = analysis.get("opening_line", "Loved seeing the impressive work your team has put together.")
    
    # Format results
    if emails:
        emails = list(set(emails))
        result["email"] = emails[0] if emails else "Not Found"
        
    if phones:
        phones = list(set(phones))
        result["phone"] = phones[0] if phones else "Not Found"
    
    if socials:
        result["socials"] = socials
        
    if location:
        result["location"] = location
        
    result["status"] = "Success"
    print("Scraping completed!")
    
    return result

def process_single_row(row: dict, business_col: str = 'Business Name') -> dict:
    """Worker function for threading: scrapes one company and updates its row."""
    company_name = row.get(business_col, '').strip()
    if not company_name:
        return row
        
    print(f"[*] Scraping: {company_name}...")
    scraped_data = scrape_company(company_name)
    
    # Enrich the original row
    if scraped_data.get('email') != "Not Found":
        row['Email'] = scraped_data['email']
        
    if scraped_data.get('phone') != "Not Found":
        row['Phone'] = scraped_data['phone']
        
    if scraped_data.get('location') != "Not Found":
        row['Location'] = scraped_data['location']
        
    if scraped_data.get('website_link') != "Not Found":
        row['Website'] = scraped_data['website_link']
        
    if 'socials' in scraped_data:
        socials = scraped_data['socials']
        for platform in ['LinkedIn', 'Facebook', 'Twitter', 'Instagram']:
            if socials.get(platform, "Not Found") != "Not Found":
                row[platform] = socials[platform]
                
    row['Niche'] = scraped_data.get('niche', '')
    row['Summary'] = scraped_data.get('summary', '')
    row['Decision Maker'] = scraped_data.get('decision_maker', '')
    row['Opening Line'] = scraped_data.get('opening_line', '')
    row['Pitch Angle'] = scraped_data.get('pitch_angle', '')
                
    print(f"[+] Finished: {company_name}")
    return row

def process_csv(input_csv: str, output_csv: str, max_workers: int = 5):
    """
    Reads a CSV file, extracts the 'Business Name', scrapes the data,
    and writes an enriched row to the output CSV.
    """
    if not os.path.exists(input_csv):
        print(f"Error: Could not find CSV file at {input_csv}")
        return
        
    # Read the original CSV
    with open(input_csv, mode='r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)
        
    # Define the specific columns to keep in the final output
    final_fieldnames = [
        'Business Name', 'Phone', 'Email', 'Location', 'Website', 
        'LinkedIn', 'Facebook', 'Twitter', 'Instagram',
        'Niche', 'Summary', 'Decision Maker', 'Opening Line', 'Pitch Angle'
    ]
    
    print(f"Found {len(rows)} companies to process in {input_csv}.")
    print(f"Starting concurrent scraping with {max_workers} threads...\n")
    
    # Pre-populate dictionary to preserve original order and data if interrupted
    enriched_rows = {i: row.copy() for i, row in enumerate(rows)}
    
    try:
        # Use ThreadPoolExecutor for concurrent scraping
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_idx = {executor.submit(process_single_row, row): i for i, row in enumerate(rows)}
            
            # Process as they complete
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    enriched_row = future.result()
                    enriched_rows[idx] = enriched_row
                except Exception as e:
                    print(f"[!] Error processing row {idx}: {e}")
                
                # Write incrementally so we don't lose data on crash
                with open(output_csv, mode='w', encoding='utf-8', newline='') as outfile:
                    # Filter only the fields we want to keep
                    writer = csv.DictWriter(outfile, fieldnames=final_fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows([enriched_rows[i] for i in range(len(rows))])
                    
    except KeyboardInterrupt:
        print("\n\n[!] Scraping interrupted by user (Ctrl+C). Saving current progress safely...")
        with open(output_csv, mode='w', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=final_fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows([enriched_rows[i] for i in range(len(rows))])
        print(f"--- Partial progress saved to {output_csv}. Exiting... ---")
        sys.exit(1)
            
    print(f"\n--- Batch processing complete! Results saved to {output_csv} ---")

def process_csv_for_job(job_id: int, input_csv: str, num_threads: int = 5, use_ai: bool = True):
    import traceback
    from db import insert_lead, update_job_progress
    from sse_logger import job_logger

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if 'Business Name' not in reader.fieldnames:
            job_logger.log(job_id, "CSV must contain a 'Business Name' column.", "error")
            return
        rows = list(reader)

    job_logger.log(job_id, f"Found {len(rows)} companies to process. (Threads: {num_threads})")

    def process_single_row_job(row):
        # Set thread local job ID for our print wrapper
        thread_local.job_id = job_id
        
        # Check Execution State
        from db import get_job_status
        import time
        while True:
            st = get_job_status(job_id)
            if not st:
                return
            if st['status'] == 'stopped':
                return
            if st['status'] == 'paused':
                time.sleep(1.5)
            else:
                break
        
        company_name = row.get('Business Name', '').strip()
        if not company_name:
            update_job_progress(job_id, delta_completed=0, delta_failed=1)
            return

        print(f"[*] Scraping: {company_name}")
        try:
            # We bypass the AI entirely if use_ai is False (could add logic inside scrape_company, but fine for now)
            scraped_data = scrape_company(company_name)
            
            lead_id = insert_lead(job_id, scraped_data)
            status = scraped_data.get('status', 'Failed')
            if status == 'Success':
                update_job_progress(job_id, delta_completed=1, delta_failed=0)
            else:
                update_job_progress(job_id, delta_completed=0, delta_failed=1)
                
            job_logger.log(job_id, f"Saved result for {company_name}", "success" if status == 'Success' else "error", lead_id=lead_id, lead_data=scraped_data)
            
        except Exception as e:
            update_job_progress(job_id, delta_completed=0, delta_failed=1)
            print(f"[!] Error scraping {company_name}: {str(e)}")
            job_logger.log(job_id, traceback.format_exc(), "error")

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        executor.map(process_single_row_job, rows)

    job_logger.log(job_id, "--- Batch processing complete! ---", "success")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Company Info Scraper")
    parser.add_argument("company", nargs='?', help="The name of the company to scrape")
    parser.add_argument("--csv", help="Path to input CSV file for batch processing", dest="input_csv")
    parser.add_argument("--out", help="Path to output CSV file", default="enriched_prospects.csv", dest="output_csv")
    parser.add_argument("--threads", help="Number of concurrent threads (default: 5)", type=int, default=5, dest="threads")
    args = parser.parse_args()
    
    if args.input_csv:
        process_csv(args.input_csv, args.output_csv, max_workers=args.threads)
    elif args.company:
        final_result = scrape_company(args.company)
        
        # Output to console
        print("\n--- Final Result ---")
        print(json.dumps(final_result, indent=2))
        
        # Save to file
        with open("results.json", "w", encoding="utf-8") as f:
            json.dump(final_result, f, indent=2)
        print("\nResult saved to results.json")
    else:
        parser.print_help()
