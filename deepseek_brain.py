"""
DeepSeek Brain — Post-call analysis module for Alex v3.4
Handles: conversation analysis, dispatch recommendations, guest insights
"""
import os
import json
import logging
import requests

logger = logging.getLogger("deepseek-brain")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

class DeepSeekBrain:
    """AI analysis engine using DeepSeek API."""

    def __init__(self):
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.model = "deepseek-chat"

    def analyze_conversation(self, transcript):
        """Analyze a call transcript for insights."""
        if not DEEPSEEK_API_KEY:
            return {"success": False, "error": "No API key"}

        try:
            resp = requests.post(self.api_url,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": """Analyze this CHATP Concierge booking call transcript. Return JSON with:
- sentiment: positive/neutral/negative
- booking_outcome: booked/quote_only/transferred/abandoned
- guest_satisfaction: 1-10
- upsell_opportunity: boolean
- destination_interest: city name or null
- improvement_suggestions: array of strings
- key_phrases: array of notable guest phrases
- estimated_lifetime_value: low/medium/high"""},
                        {"role": "user", "content": transcript}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.3,
                },
                timeout=30
            )
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            tokens = data.get("usage", {}).get("total_tokens", 0)

            # Try to parse JSON from response
            try:
                analysis = json.loads(content)
            except json.JSONDecodeError:
                analysis = {"raw_response": content}

            return {"success": True, "analysis": analysis, "tokens": tokens}
