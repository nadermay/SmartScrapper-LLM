import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3:8b"

def call_ollama(prompt: str, json_format: bool = False) -> str:
    """Send a prompt to local Ollama and return the response text."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2 # Lower temperature for better extraction precision
        }
    }
    if json_format:
        payload["format"] = "json"

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        print(f"[!] Ollama request failed: {e}")
        return ""

def analyze_lead_full(text: str) -> dict:
    """Extract lead qualification data, decision maker info, sales opportunities, and drafting copy in ONE call."""
    truncated_text = text[:5000]
    prompt = f"""You are an expert B2B lead qualifier and sales copywriter. Analyze the following text extracted from a potential client's website.

Website Text:
{truncated_text}

Return EXACTLY this JSON structure and nothing else:
{{
  "summary": "A 1-sentence summary of what the company does",
  "niche": "The primary industry/niche (e.g., Commercial Roofing, HVAC, Residential Plumbing)",
  "decision_maker_name": "Full name of the Owner, Founder, CEO, or President if mentioned, else null",
  "decision_maker_title": "Their exact title if found, else null",
  "pitch_angle": "Identify a potential business weakness, missing service, or sales opportunity based on their site (e.g., 'No mention of 24/7 service', 'Website content is very sparse'). Keep it to 1 sentence.",
  "opening_line": "A single, highly personalized opening sentence to use in a cold email. Compliment their achievements, history, longevity, or specific focus area. Maintain a professional yet warm tone."
}}
"""
    res = call_ollama(prompt, json_format=True)
    try:
        data = json.loads(res)
        # Ensure fallback for opening line if the model messes up the json key
        if 'opening_line' not in data:
            data['opening_line'] = "I was impressed by your company's track record and wanted to reach out."
        return data
    except json.JSONDecodeError:
        return {
            "summary": "Failed to generate summary", 
            "niche": "Unknown", 
            "decision_maker_name": None, 
            "decision_maker_title": None,
            "pitch_angle": "Unknown",
            "opening_line": "I was impressed by your company's track record and wanted to reach out."
        }

def generate_cold_email(lead_data: dict, agency_context: dict) -> str:
    """Drafts a full cold email using the agency context and lead discoveries."""
    
    agency_name = agency_context.get("name", "Our Agency")
    agency_services = agency_context.get("services", "digital marketing and lead generation")
    agency_cta = agency_context.get("cta", "Are you open to a brief chat this week to see how we can help?")

    business_name = lead_data.get("business_name", "your business")
    dm = lead_data.get("decision_maker", "there")
    if dm == "Unknown" or not dm:
        dm = "Team"
    else:
        dm = dm.split("(")[0].strip() # remove title

    opening = lead_data.get("opening_line", "")
    niche = lead_data.get("niche", "your industry")
    weakness = lead_data.get("pitch_angle", "opportunities for growth")

    prompt = f"""You are a top-tier B2B executive sales copywriter writing a highly personalized cold email to a prospect.
Write a 3 to 4 sentence cold email to {dm} at {business_name}. 

Follow these EXACT rules:
1. Start the email with: "Hi {dm},"
2. Sentence 1: Use this exact opening line: "{opening}"
3. Sentence 2: Transition into their specific business opportunity or gap we noticed: "{weakness}"
4. Sentence 3: Briefly position our agency ({agency_name}) as the solution, mentioning we specialize in: "{agency_services}"
5. Sentence 4: End with this exact call to action: "{agency_cta}"
6. Sign off with: 
"Best,
[Your Name]
{agency_name}"

Do NOT include a Subject Line. Do not add any conversational filler before or after the email text. Return ONLY the exact email body. Make the transition sentences natural and professional.
"""
    
    # Use a slightly higher temperature for creative drafting
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.6
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"[!] Ollama email generation failed: {e}")
        return "Error generating email. Ensure Ollama is running."


if __name__ == "__main__":
    # Quick test to verify Ollama connectivity
    print("Testing Ollama connection...")
    test_res = call_ollama("Say 'Ollama is alive' if you can read this.", json_format=False)
    print(f"Response: {test_res}")
