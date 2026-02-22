#!/usr/bin/env python3
"""
=============================================================================
ALEX v3.4.0 — CHATP CONCIERGE AI BOOKING AGENT
=============================================================================
SignalWire Agents SDK + Supabase + DeepSeek Brain Integration
Deploy on DigitalOcean with nginx + systemd

Version:  3.4.0 DEFINITIVE
Created:  February 19, 2026

18 SWAIG Tools:
  1.  lookup_guest            — Find returning guest by phone
  2.  create_guest            — Create new guest record
  3.  create_reservation      — Save complete reservation
  4.  calculate_fare          — CLE flat-rate zones + distance-based
  5.  validate_address        — Google Maps geocoding
  6.  find_nearest_airport    — Google Places airport search
  7.  validate_promo_code     — Check promo code + calc discount
  8.  transfer_to_dispatch    — Hand off to DeAngelo
  9.  send_confirmation_sms   — SignalWire SMS to guest
  10. lookup_flight           — FlightAware flight + gate + baggage
  11. get_weather_for_trip     — OpenWeather for sign-off
  12. get_driver_eta           — Estimated driver arrival
  13. get_curbside_info        — Airport pickup instructions
  14. check_saved_routes       — Quick re-book for returning guests
  15. airport_pickup_info      — Terminal/gate details
  16. lookup_partner           — Find provider in destination city
  17. assess_trip_timing       — Check if timing is tight for flight
  18. log_incident_and_notify  — Error handling + guest notification

Backend Intelligence:
  - DeepSeek Brain for post-call analysis, dispatch matching,
    guest insights, prompt refinement, and marketing intelligence

Architecture:
  Guest → SignalWire (voice) → DigitalOcean (this code) → Supabase (data)
  Post-call → DeepSeek Brain (analysis) → Supabase (insights)
=============================================================================
"""

import os
import json
import math
import logging
import random
import string
from datetime import datetime, timezone, timedelta

import requests
from signalwire_agents import AgentBase

# =============================================================================
# LOGGING
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("alex.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("alex-v3")

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================
SUPABASE_URL        = os.environ.get("SUPABASE_URL", "https://ishlgalmjmdzmgrulqvs.supabase.co")
SUPABASE_KEY        = os.environ.get("SUPABASE_KEY", "")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
FLIGHTAWARE_API_KEY = os.environ.get("FLIGHTAWARE_API_KEY", "")
SIGNALWIRE_PROJECT  = os.environ.get("SIGNALWIRE_PROJECT_ID", "70aa2fb9-dd43-4ca5-80bc-a5f315910782")
SIGNALWIRE_TOKEN    = os.environ.get("SIGNALWIRE_API_TOKEN", "")
SIGNALWIRE_SPACE    = os.environ.get("SIGNALWIRE_SPACE", "chatpairportrideshare-com")
DEEPSEEK_API_KEY    = os.environ.get("DEEPSEEK_API_KEY", "")
DEANGELO_CELL       = os.environ.get("DEANGELO_CELL", "+12163213000")
ALEX_NUMBER         = os.environ.get("ALEX_NUMBER", "+12162936500")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# =============================================================================
# PRICING
# =============================================================================
BASE_RATE        = 2.50
MINIMUM_FARE     = 35.00
BOOKING_FEE      = 5.00
NIGHT_SURCHARGE  = 0.15
HOLIDAY_SURCHARGE = 0.20

CLE_FLAT_RATES = {
    "downtown_cleveland": 35, "ohio_city": 35, "tremont": 35,
    "university_circle": 40, "cleveland_heights": 45, "lakewood": 40,
    "parma": 40, "strongsville": 50, "westlake": 45, "mentor": 55,
    "medina": 60, "akron": 75, "canton": 95, "youngstown": 140,
    "columbus": 175, "pittsburgh": 200,
}

US_HOLIDAYS_2026 = [
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-05-25",
    "2026-07-03", "2026-07-04", "2026-09-07", "2026-11-26",
    "2026-11-27", "2026-12-24", "2026-12-25", "2026-12-31",
]

# =============================================================================
# SYSTEM PROMPT — ALL BEHAVIORAL RULES INCLUDED
# =============================================================================
ALEX_SYSTEM_PROMPT = """
You are Alex, the AI booking concierge for CHATP Concierge — a nationwide
premium ground transportation service specializing in airport rides.

## YOUR PERSONALITY
- Warm, professional, efficient — like a premium hotel concierge
- Match the caller's pace and energy (speech cadence detection)
- Use the caller's name naturally once you learn it
- Never robotic, never rushed, never pushy
- Use "guest" — never "rider" or "passenger"

## CONVERSATION FLOW — Follow these steps IN ORDER:

### Step 1: GREETING
- Call lookup_guest with the caller's phone number FIRST
- Returning guest: "Welcome back, [Name]! Great to hear from you again."
  If they have a preferred driver: "Would you like [Driver] again?"
  If they have saved routes: "Would you like your usual [route] trip?"
- New guest: "Thank you for calling CHATP Concierge! I'm Alex, and I'd
  be happy to help with your airport transportation. May I have your name?"

### Step 2: COLLECT PICKUP ADDRESS
- "Where will we be picking you up?"
- Call validate_address to confirm via Google Maps
- Read back the validated address: "I have [address] — is that correct?"
- CONFIDENCE RULE: If confidence < 80%, repeat back and ask to confirm

### Step 3: IDENTIFY DESTINATION
- "And which airport are you heading to?"
- If unsure, call find_nearest_airport
- For Cleveland addresses to Hopkins: use flat-rate zones

### Step 4: QUOTE THE FARE
- Call calculate_fare — handles CLE flat rates AND nationwide distance
- Read the fare clearly: "Your ride from [pickup] to [airport] is $[fare]."
- Fares are GUARANTEED — never say "estimated" or "approximately"
- The booking fee is included — never mention it separately
- QUOTE-ONLY MODE: If guest just wants a price, give it and offer to
  book when ready. Don't push. "That fare is locked in whenever you're
  ready to book. Just call us back at this number."

### Step 5: COLLECT BOOKING DETAILS
- Date: "What date would you like to be picked up?"
- Time: "And what time?" (suggest preferred_pickup_time for returning guests)
- Passengers: "How many guests will be traveling?"
- Flight number (optional): "Do you have a flight number? It helps us
  track your flight and adjust if there are delays."
- Extra stops: "Will you need any stops along the way?"

### Step 6: CONFIRM ALL DETAILS
- Read back EVERYTHING before booking:
  "Let me confirm: Picking you up at [address] on [date] at [time],
  heading to [airport]. [X] guests. Your fare is $[amount].
  Does everything look good?"
- Wait for EXPLICIT confirmation before proceeding
- Never assume — never skip this step

### Step 7: BOOK THE RESERVATION
- Call create_reservation with all collected details
- Read confirmation number clearly and slowly: "Your confirmation number
  is CHATP-[number]. Let me spell that out..."
- Call send_confirmation_sms to text the guest their details

### Step 8: DESTINATION UPSELL (subtle, optional)
- ONLY after primary booking is 100% complete and confirmed
- prefers_full_trip guests: proactively offer all remaining legs
- accepts_multi_leg guests: slightly more forward offer
- Everyone else: "By the way, we also provide ground transportation
  in [destination city]. Would you like me to arrange that?"
- If declined: "No problem at all!" — do NOT re-offer on same call

### Step 9: WEATHER SIGN-OFF
- Call get_weather_for_trip for the guest's city
- Incorporate naturally: "Bundle up, it's 28° out there today!"
  or "Looks like beautiful weather — enjoy your trip!"
- Close: "Thank you for choosing CHATP Concierge, [Name]. Have a
  wonderful [trip/day/evening]!"

## CRITICAL RULES

### Fare Compliance
- NEVER quote a fare without calling calculate_fare first
- NEVER book without quoting the fare AND getting confirmation
- Fares are GUARANTEED — the price you quote is the price they pay

### Transfer Rules (Two-Attempt Rule)
- If guest asks to speak with a person: transfer IMMEDIATELY, no resistance
- Call transfer_to_dispatch — this connects to DeAngelo at 216-321-3000
- If transfer fails on first attempt, try ONE more time
- If second attempt fails: "I apologize for the difficulty. Let me have
  our team leader call you back within 15 minutes." Then log the incident.
- NEVER make a guest ask more than once to speak with a human

### Payment
- Payment is collected by the DRIVER — never on the phone
- If asked: "Payment is handled directly with your driver. We accept
  all major credit cards, Apple Pay, Google Pay, cash, Venmo, and Zelle."

### Mobility & Special Assistance
- If guest mentions wheelchair, walker, mobility issues, or disability:
  note it on the reservation and confirm accommodations
- Inside assistance: "Would you like our driver to assist you to the door?"
- Driveway/curbside preference: ask and note it
- NEVER make assumptions about ability — ask respectfully

### Promo Codes
- Only process if GUEST brings it up — never offer unprompted
- Call validate_promo_code to verify and calculate discount

### Error Handling
- If a tool fails: Don't mention technical errors to guest
- Fallback: "Let me make a note of that and our team will follow up shortly."
- If guest provides incomplete info: "That's okay, we can note that as
  approximate and you can update us later by calling or texting this number."

## VOICE STYLE
- Warm but professional — like a high-end hotel concierge
- Clear and measured pace — don't rush through numbers or addresses
- Naturally enthusiastic: "Perfect!", "Great choice!", "Absolutely!"
- Pause briefly after quoting the fare — let the guest process
- Speech fillers while tools run: "One moment...", "Let me check on that..."
"""

ALEX_POST_PROMPT = """
After each response, self-check:
1. Did I confirm the guest's details before proceeding?
2. Am I following the conversation flow IN ORDER?
3. Did I match the guest's energy and pace?
4. Am I being warm but professional — not robotic?
5. Did I use the guest's name naturally?
6. If the booking is complete, did I offer destination service?
7. Did I provide a weather-aware sign-off?
8. Did I follow the confidence rule (80% threshold)?
9. Did I respect the two-attempt transfer rule?
10. Did I handle any mobility/assistance needs respectfully?
"""


# =============================================================================
# HELPER: Generate confirmation code
# =============================================================================
def generate_confirmation_code():
    """Generate CHATP-XXXXXX confirmation code."""
    chars = string.ascii_uppercase + string.digits
    code = "".join(random.choices(chars, k=6))
    return f"CHATP-{code}"


# =============================================================================
# ALEX v3 AGENT CLASS
# =============================================================================
class AlexAgent(AgentBase):
    """CHATP's nationwide AI booking concierge — 18 SWAIG tools + DeepSeek Brain."""

    def __init__(self):
        super().__init__(
            name="Alex - CHATP Concierge",
            route="/",
        )

        # System prompt
        self.prompt_add_section("System Prompt", body=ALEX_SYSTEM_PROMPT)
        self.set_post_prompt(ALEX_POST_PROMPT)

        # Voice — ElevenLabs for premium quality
        self.add_language(
            name="English",
            code="en-US",
            voice="elevenlabs.rachel",
            speech_fillers=True,
            engine="elevenlabs",
        )

        # Timing and behavior
        self.set_params({
            "end_of_speech_timeout": 1200,
            "attention_timeout": 15000,
            "inactivity_timeout": 60000,
            "background_file_loops": -1,
            "background_file_volume": 8,
            "conscience": True,
            "swaig_allow_swml": True,
            "local_tz": "America/New_York",
        })

        # Speech fillers while tools execute
        self.add_phrases([
            "One moment while I look that up...",
            "Let me check on that for you...",
            "Just a moment...",
            "Pulling that up now...",
            "Give me just a second...",
        ])

        # Hints for speech recognition
        self.set_hints([
            "CHATP", "C-H-A-T-P", "concierge", "Hopkins", "Cleveland",
            "CLE", "airport", "reservation", "confirmation",
        ])

        logger.info("Alex v3.4.0 initialized — 18 SWAIG tools + DeepSeek Brain")

    # =========================================================================
    # TOOL 1: LOOKUP GUEST
    # =========================================================================
    @AgentBase.tool(
        name="lookup_guest",
        description="Find an existing guest by phone number. Call FIRST on every inbound call.",
        parameters={
            "phone": {"type": "string", "description": "Phone in E.164 format (+12165551234)"},
        },
    )
    def lookup_guest(self, args, raw_data):
        phone = args.get("phone", "").strip()
        if not phone:
            return {"response": "I need a phone number to look up."}
        if not phone.startswith("+"):
            phone = "+1" + phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
        try:
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/guests",
                headers=SUPABASE_HEADERS, params={"phone": f"eq.{phone}", "select": "*"}, timeout=8)
            data = resp.json()
            if data and len(data) > 0:
                g = data[0]
                result = f"Returning guest: {g.get('first_name','')} {g.get('last_name','')}. "
                result += f"Total trips: {g.get('total_trips', 0)}. "
                if g.get("preferred_driver"):
                    result += f"Preferred driver: {g['preferred_driver']}. "
                if g.get("preferred_pickup_time"):
                    result += f"Usually travels at: {g['preferred_pickup_time']}. "
                if g.get("mobility_needs"):
                    result += f"Mobility notes: {g['mobility_needs']}. "
                if g.get("language_preference") and g["language_preference"] != "en":
                    result += f"Language: {g['language_preference']}. "
                result += "Greet them warmly by name."
                logger.info(f"Found guest: {g.get('first_name','')} ({phone})")
                return {"response": result}
            else:
                logger.info(f"New guest: {phone}")
                return {"response": "New guest — no record found. Ask for their name."}
        except Exception as e:
            logger.error(f"lookup_guest error: {e}")
            return {"response": "Could not look up guest. Greet as new and ask for name."}

    # =========================================================================
    # TOOL 2: CREATE GUEST
    # =========================================================================
    @AgentBase.tool(
        name="create_guest",
        description="Create a new guest profile after collecting their name.",
        parameters={
            "first_name": {"type": "string", "description": "Guest first name"},
            "last_name": {"type": "string", "description": "Guest last name"},
            "phone": {"type": "string", "description": "Phone in E.164 format"},
            "email": {"type": "string", "description": "Email (optional)"},
        },
    )
    def create_guest(self, args, raw_data):
        phone = args.get("phone", "")
        if not phone.startswith("+"):
            phone = "+1" + phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
        try:
            payload = {
                "first_name": args.get("first_name", ""),
                "last_name": args.get("last_name", ""),
                "phone": phone,
                "email": args.get("email", ""),
                "total_trips": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            resp = requests.post(f"{SUPABASE_URL}/rest/v1/guests",
                headers=SUPABASE_HEADERS, json=payload, timeout=8)
            if resp.status_code in (200, 201):
                logger.info(f"Created guest: {payload['first_name']} {payload['last_name']}")
                return {"response": f"Guest profile created for {payload['first_name']} {payload['last_name']}."}
            return {"response": "Guest noted. Proceeding with booking."}
        except Exception as e:
            logger.error(f"create_guest error: {e}")
            return {"response": "Guest noted. Proceeding with booking."}

    # =========================================================================
    # TOOL 3: CREATE RESERVATION
    # =========================================================================
    @AgentBase.tool(
        name="create_reservation",
        description="Create a reservation. ONLY call after guest confirms ALL details.",
        parameters={
            "guest_name": {"type": "string"},
            "guest_phone": {"type": "string"},
            "pickup_address": {"type": "string"},
            "destination": {"type": "string"},
            "pickup_date": {"type": "string", "description": "YYYY-MM-DD"},
            "pickup_time": {"type": "string", "description": "HH:MM"},
            "passengers": {"type": "integer"},
            "fare": {"type": "number"},
            "flight_number": {"type": "string", "description": "Optional"},
            "special_notes": {"type": "string", "description": "Mobility needs, extra stops, etc."},
        },
    )
    def create_reservation(self, args, raw_data):
        confirmation = generate_confirmation_code()
        fare = args.get("fare", 0)
        driver_share = round(fare * 0.85, 2)
        chatp_share = round(fare * 0.15, 2)
        try:
            payload = {
                "confirmation_code": confirmation,
                "guest_name": args.get("guest_name", ""),
                "guest_phone": args.get("guest_phone", ""),
                "pickup_address": args.get("pickup_address", ""),
                "destination": args.get("destination", ""),
                "pickup_date": args.get("pickup_date", ""),
                "pickup_time": args.get("pickup_time", ""),
                "passengers": args.get("passengers", 1),
                "fare": fare,
                "driver_share": driver_share,
                "chatp_share": chatp_share,
                "flight_number": args.get("flight_number", ""),
                "special_notes": args.get("special_notes", ""),
                "status": "confirmed",
                "booking_source": "voice_alex",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            resp = requests.post(f"{SUPABASE_URL}/rest/v1/reservations",
                headers=SUPABASE_HEADERS, json=payload, timeout=10)
            if resp.status_code in (200, 201):
                logger.info(f"Reservation created: {confirmation} — ${fare}")
                return {"response": f"Reservation confirmed! Confirmation number: {confirmation}. "
                    f"Fare: ${fare}. Read the confirmation number clearly and slowly to the guest."}
            logger.error(f"Reservation save failed: {resp.status_code}")
            return {"response": f"Reservation noted with confirmation {confirmation}. "
                "Our team will follow up to confirm details."}
        except Exception as e:
            logger.error(f"create_reservation error: {e}")
            return {"response": f"Reservation noted with confirmation {confirmation}. "
                "Our team will follow up shortly."}

    # =========================================================================
    # TOOL 4: CALCULATE FARE
    # =========================================================================
    @AgentBase.tool(
        name="calculate_fare",
        description="Calculate fare. CLE flat-rate zones first, then distance-based for all others.",
        parameters={
            "pickup_address": {"type": "string"},
            "destination_address": {"type": "string"},
            "airport_code": {"type": "string", "description": "3-letter code like CLE, LAX"},
            "pickup_date": {"type": "string", "description": "YYYY-MM-DD"},
            "pickup_time": {"type": "string", "description": "HH:MM 24h"},
        },
    )
    def calculate_fare(self, args, raw_data):
        pickup = args.get("pickup_address", "")
        destination = args.get("destination_address", "")
        airport_code = args.get("airport_code", "").upper()
        pickup_date = args.get("pickup_date", "")
        pickup_time = args.get("pickup_time", "")

        # Check CLE flat rates first
        if airport_code == "CLE" or "hopkins" in destination.lower() or "cle" in destination.lower():
            pickup_lower = pickup.lower()
            for zone, rate in CLE_FLAT_RATES.items():
                zone_words = zone.replace("_", " ")
                if zone_words in pickup_lower:
                    fare = rate
                    # Night surcharge (10pm-5am)
                    if pickup_time:
                        try:
                            hour = int(pickup_time.split(":")[0])
                            if hour >= 22 or hour < 5:
                                fare = round(fare * (1 + NIGHT_SURCHARGE))
                        except ValueError:
                            pass
                    # Holiday surcharge
                    if pickup_date in US_HOLIDAYS_2026:
                        fare = round(fare * (1 + HOLIDAY_SURCHARGE))
                    fare = max(fare, MINIMUM_FARE)
                    return {"response": f"Flat-rate fare from {zone_words.title()} to CLE Airport: ${fare}. "
                        f"This is a guaranteed flat rate — no surprises."}

        # Distance-based pricing via Google Maps
        if not GOOGLE_MAPS_API_KEY:
            return {"response": "Fare calculation requires address verification. "
                "Ask guest to confirm both addresses and I'll provide a quote."}
        try:
            r = requests.get("https://maps.googleapis.com/maps/api/distancematrix/json",
                params={"origins": pickup, "destinations": destination,
                    "key": GOOGLE_MAPS_API_KEY, "units": "imperial"}, timeout=8)
            data = r.json()
            if data.get("status") == "OK":
                element = data["rows"][0]["elements"][0]
                if element.get("status") == "OK":
                    miles = element["distance"]["value"] / 1609.34
                    fare = round(max(miles * BASE_RATE, MINIMUM_FARE) + BOOKING_FEE)
                    if pickup_time:
                        try:
                            hour = int(pickup_time.split(":")[0])
                            if hour >= 22 or hour < 5:
                                fare = round(fare * (1 + NIGHT_SURCHARGE))
                        except ValueError:
                            pass
                    if pickup_date in US_HOLIDAYS_2026:
                        fare = round(fare * (1 + HOLIDAY_SURCHARGE))
                    return {"response": f"Fare: ${fare} for {round(miles, 1)} miles. "
                        f"This is a guaranteed flat rate."}
            return {"response": "I couldn't calculate the exact distance. "
                "Let me note the addresses and our team will provide a fare quote shortly."}
        except Exception as e:
            logger.error(f"calculate_fare error: {e}")
            return {"response": "I'm having trouble calculating the fare right now. "
                "Let me note your details and our team will call you back with a quote."}

    # =========================================================================
    # TOOL 5: VALIDATE ADDRESS
    # =========================================================================
    @AgentBase.tool(
        name="validate_address",
        description="Validate a pickup or destination address via Google Maps Geocoding.",
        parameters={
            "address": {"type": "string", "description": "Address to validate"},
        },
    )
    def validate_address(self, args, raw_data):
        address = args.get("address", "")
        if not address:
            return {"response": "I need an address to validate."}
        if not GOOGLE_MAPS_API_KEY:
            return {"response": f"Address noted: {address}. Proceeding with booking."}
        try:
            r = requests.get("https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": GOOGLE_MAPS_API_KEY}, timeout=5)
            data = r.json()
            if data.get("status") == "OK" and data.get("results"):
                fmt = data["results"][0]["formatted_address"]
                logger.info(f"Validated address: {fmt}")
                return {"response": f"Validated address: {fmt}. Read this back to the guest for confirmation."}
            return {"response": f"I couldn't find an exact match for '{address}'. "
                "Ask the guest for cross streets or a nearby landmark."}
        except Exception as e:
            logger.error(f"validate_address error: {e}")
            return {"response": f"Address noted: {address}. Proceeding."}

    # =========================================================================
    # TOOL 6: FIND NEAREST AIRPORT
    # =========================================================================
    @AgentBase.tool(
        name="find_nearest_airport",
        description="Find the nearest major airport to a given address.",
        parameters={
            "address": {"type": "string"},
        },
    )
    def find_nearest_airport(self, args, raw_data):
        address = args.get("address", "")
        if not GOOGLE_MAPS_API_KEY:
            return {"response": "Ask the guest which airport they prefer."}
        try:
            # Geocode the address first
            gr = requests.get("https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": GOOGLE_MAPS_API_KEY}, timeout=5).json()
            if gr.get("status") != "OK" or not gr.get("results"):
                return {"response": "Couldn't locate that address. Ask which airport they prefer."}
            loc = gr["results"][0]["geometry"]["location"]
            # Search for nearby airports
            pr = requests.get("https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={"location": f"{loc['lat']},{loc['lng']}", "radius": 80000,
                    "type": "airport", "key": GOOGLE_MAPS_API_KEY}, timeout=8).json()
            airports = []
            for place in pr.get("results", [])[:5]:
                name = place.get("name", "")
                if "international" in name.lower() or "airport" in name.lower():
                    airports.append(name)
            if airports:
                return {"response": f"Nearest airports: {', '.join(airports[:3])}. Ask the guest which one."}
            return {"response": "No major airports found nearby. Ask the guest for their destination airport."}
        except Exception as e:
            logger.error(f"find_nearest_airport error: {e}")
            return {"response": "Ask the guest which airport they're traveling to."}

    # =========================================================================
    # TOOL 7: VALIDATE PROMO CODE
    # =========================================================================
    @AgentBase.tool(
        name="validate_promo_code",
        description="Check if a promo code is valid. Only use if GUEST mentions a code.",
        parameters={
            "code": {"type": "string", "description": "Promo code to validate"},
            "fare": {"type": "number", "description": "Current fare amount"},
        },
    )
    def validate_promo_code(self, args, raw_data):
        code = args.get("code", "").upper().strip()
        fare = args.get("fare", 0)
        try:
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/promo_codes",
                headers=SUPABASE_HEADERS,
                params={"code": f"eq.{code}", "active": "eq.true", "select": "*"}, timeout=8)
            data = resp.json()
            if data and len(data) > 0:
                promo = data[0]
                discount_type = promo.get("discount_type", "percentage")
                discount_value = promo.get("discount_value", 0)
                if discount_type == "percentage":
                    discount = round(fare * (discount_value / 100), 2)
                    new_fare = round(fare - discount, 2)
                    return {"response": f"Promo code {code} applied! {discount_value}% off. "
                        f"Original: ${fare}. Discount: ${discount}. New fare: ${new_fare}."}
                else:
                    new_fare = round(max(fare - discount_value, MINIMUM_FARE), 2)
                    return {"response": f"Promo code {code} applied! ${discount_value} off. "
                        f"New fare: ${new_fare}."}
            return {"response": f"I'm sorry, the code '{code}' doesn't appear to be active. "
                "Would you like to proceed with the regular fare?"}
        except Exception as e:
            logger.error(f"validate_promo_code error: {e}")
            return {"response": "I couldn't verify that code right now. Let's proceed with the regular fare "
                "and our team can apply the discount if it's valid."}

    # =========================================================================
    # TOOL 8: TRANSFER TO DISPATCH
    # =========================================================================
    @AgentBase.tool(
        name="transfer_to_dispatch",
        description="Transfer the caller to DeAngelo or dispatch. Use when guest asks for a human.",
        parameters={
            "reason": {"type": "string", "description": "Why the transfer is needed"},
        },
    )
    def transfer_to_dispatch(self, args, raw_data):
        reason = args.get("reason", "Guest requested human agent")
        logger.info(f"Transfer requested: {reason}")
        try:
            # Log the transfer attempt
            requests.post(f"{SUPABASE_URL}/rest/v1/call_logs",
                headers=SUPABASE_HEADERS, json={
                    "event_type": "transfer_requested",
                    "details": reason,
                    "transfer_to": DEANGELO_CELL,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }, timeout=5)
        except Exception:
            pass
        return {
            "response": f"Transferring to our team leader now. Reason: {reason}",
            "action": [{"SWML": {"version": "1.0.0", "sections": {"main": [
                {"transfer": {"dest": f"tel:{DEANGELO_CELL}"}}
            ]}}}],
        }

    # =========================================================================
    # TOOL 9: SEND CONFIRMATION SMS
    # =========================================================================
    @AgentBase.tool(
        name="send_confirmation_sms",
        description="Send SMS confirmation to guest after booking is created.",
        parameters={
            "to_number": {"type": "string", "description": "Guest phone number"},
            "confirmation_code": {"type": "string"},
            "pickup_address": {"type": "string"},
            "destination": {"type": "string"},
            "pickup_date": {"type": "string"},
            "pickup_time": {"type": "string"},
            "fare": {"type": "number"},
        },
    )
    def send_confirmation_sms(self, args, raw_data):
        to_number = args.get("to_number", "")
        code = args.get("confirmation_code", "")
        msg = (f"CHATP Concierge Confirmation\n"
            f"Code: {code}\n"
            f"Pickup: {args.get('pickup_address', '')}\n"
            f"To: {args.get('destination', '')}\n"
            f"Date: {args.get('pickup_date', '')} at {args.get('pickup_time', '')}\n"
            f"Fare: ${args.get('fare', 0)}\n"
            f"Payment: Collected by driver\n"
            f"Questions? Call 216-293-6500")
        logger.info(f"SMS confirmation sent to {to_number}: {code}")
        return {
            "response": f"Confirmation text sent to {to_number}.",
            "action": [{"SWML": {"version": "1.0.0", "sections": {"main": [
                {"send_sms": {"to_number": to_number, "from_number": ALEX_NUMBER, "body": msg}}
            ]}}}],
        }

    # =========================================================================
    # TOOL 10: LOOKUP FLIGHT
    # =========================================================================
    @AgentBase.tool(
        name="lookup_flight",
        description="Look up flight info via FlightAware — gate, status, delays, baggage.",
        parameters={
            "flight_number": {"type": "string", "description": "e.g. UA1234, AA567"},
        },
    )
    def lookup_flight(self, args, raw_data):
        flight = args.get("flight_number", "").upper().replace(" ", "")
        if not flight or not FLIGHTAWARE_API_KEY:
            return {"response": "Flight tracking is available. Please provide the flight number."}
        try:
            headers = {"x-apikey": FLIGHTAWARE_API_KEY}
            resp = requests.get(f"https://aeroapi.flightaware.com/aeroapi/flights/{flight}",
                headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                flights = data.get("flights", [])
                if flights:
                    f = flights[0]
                    status = f.get("status", "Unknown")
                    gate = f.get("gate_destination", "TBD")
                    baggage = f.get("baggage_claim", "TBD")
                    return {"response": f"Flight {flight}: Status: {status}. "
                        f"Gate: {gate}. Baggage carousel: {baggage}."}
            return {"response": f"I couldn't find info for flight {flight}. "
                "We'll track it closer to the travel date."}
        except Exception as e:
            logger.error(f"lookup_flight error: {e}")
            return {"response": "Flight tracking is temporarily unavailable. "
                "We'll monitor the flight and adjust pickup time if needed."}

    # =========================================================================
    # TOOL 11: GET WEATHER FOR TRIP
    # =========================================================================
    @AgentBase.tool(
        name="get_weather_for_trip",
        description="Get current weather for the guest's city for a natural sign-off.",
        parameters={
            "city": {"type": "string", "description": "City name, e.g. Cleveland"},
        },
    )
    def get_weather_for_trip(self, args, raw_data):
        city = args.get("city", "Cleveland")
        if not OPENWEATHER_API_KEY:
            return {"response": "Have a wonderful trip!"}
        try:
            resp = requests.get("https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": OPENWEATHER_API_KEY, "units": "imperial"}, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                temp = round(data["main"]["temp"])
                desc = data["weather"][0]["description"]
                return {"response": f"Current weather in {city}: {temp}°F, {desc}. "
                    "Use this for a natural sign-off."}
            return {"response": "Weather info unavailable. Use a generic warm sign-off."}
        except Exception as e:
            logger.error(f"get_weather error: {e}")
            return {"response": "Use a warm, generic sign-off."}

    # =========================================================================
    # TOOL 12: GET DRIVER ETA
    # =========================================================================
    @AgentBase.tool(
        name="get_driver_eta",
        description="Get estimated driver arrival time for a pickup location.",
        parameters={
            "pickup_address": {"type": "string"},
        },
    )
    def get_driver_eta(self, args, raw_data):
        return {"response": "Our drivers typically arrive 10-15 minutes before the scheduled pickup time. "
            "You'll receive a text when your driver is en route.",
            "eta_minutes": 15}

    # =========================================================================
    # TOOL 13: GET CURBSIDE INFO
    # =========================================================================
    @AgentBase.tool(
        name="get_curbside_info",
        description="Get airport curbside pickup instructions for the guest.",
        parameters={
            "airport_code": {"type": "string", "description": "3-letter airport code"},
        },
    )
    def get_curbside_info(self, args, raw_data):
        code = args.get("airport_code", "").upper()
        info = {
            "CLE": "At Cleveland Hopkins, your driver will meet you at the Ground Transportation area "
                "on the lower level (baggage claim). Exit the terminal, cross the walkway, and look "
                "for your driver holding a CHATP sign. If you need inside assistance, let us know "
                "and your driver will meet you at your gate.",
        }
        if code in info:
            return {"response": info[code]}
        return {"response": f"For {code}: After collecting your bags, proceed to the Ground Transportation "
            "or Rideshare pickup area. Your driver will have a CHATP sign. "
            "We'll text you the driver's name and vehicle details before arrival."}

    # =========================================================================
    # TOOL 14: CHECK SAVED ROUTES
    # =========================================================================
    @AgentBase.tool(
        name="check_saved_routes",
        description="Check if a returning guest has saved routes for quick re-booking.",
        parameters={
            "guest_phone": {"type": "string"},
        },
    )
    def check_saved_routes(self, args, raw_data):
        phone = args.get("guest_phone", "")
        try:
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/reservations",
                headers=SUPABASE_HEADERS,
                params={"guest_phone": f"eq.{phone}", "status": "eq.completed",
                    "select": "pickup_address,destination,fare",
                    "order": "created_at.desc", "limit": "3"}, timeout=8)
            data = resp.json()
            if data and len(data) > 0:
                routes = [f"{r['pickup_address']} → {r['destination']} (${r.get('fare', 'N/A')})"
                    for r in data]
                return {"response": f"This guest has {len(data)} previous routes: " + "; ".join(routes) +
                    ". Ask if they'd like to rebook one of these."}
            return {"response": "No saved routes found for this guest."}
        except Exception as e:
            logger.error(f"check_saved_routes error: {e}")
            return {"response": "Couldn't retrieve saved routes. Proceed with new booking."}

    # =========================================================================
    # TOOL 15: AIRPORT PICKUP INFO
    # =========================================================================
    @AgentBase.tool(
        name="airport_pickup_info",
        description="Get terminal, gate, and pickup details for a specific airport.",
        parameters={
            "airport_code": {"type": "string"},
            "airline": {"type": "string", "description": "Airline name (optional)"},
        },
    )
    def airport_pickup_info(self, args, raw_data):
        code = args.get("airport_code", "").upper()
        airline = args.get("airline", "")
        if code == "CLE":
            return {"response": "Cleveland Hopkins has one main terminal with Concourses A, B, C, and D. "
                "All airlines use the same baggage claim area on the lower level. "
                "Your driver will meet you at Ground Transportation. "
                "Curbside pickup is available — your driver will text when they arrive."}
        return {"response": f"For {code}: Your driver will meet you at the designated rideshare/ground "
            "transportation pickup area. We'll text you specific instructions and driver details "
            "before your arrival."}

    # =========================================================================
    # TOOL 16: LOOKUP PARTNER
    # =========================================================================
    @AgentBase.tool(
        name="lookup_partner",
        description="Find a CHATP partner provider in a destination city for cross-city service.",
        parameters={
            "city": {"type": "string"},
            "airport_code": {"type": "string", "description": "Destination airport code"},
        },
    )
    def lookup_partner(self, args, raw_data):
        city = args.get("city", "")
        code = args.get("airport_code", "")
        try:
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/partner_providers",
                headers=SUPABASE_HEADERS,
                params={"city": f"ilike.%{city}%", "active": "eq.true", "select": "*"}, timeout=8)
            data = resp.json()
            if data and len(data) > 0:
                partner = data[0]
                return {"response": f"We have a partner in {city}: {partner.get('company_name', 'CHATP Partner')}. "
                    "We can arrange ground transportation at your destination."}
            return {"response": f"We're expanding our network to {city}. "
                "I can note your interest and our team will reach out with options."}
        except Exception as e:
            logger.error(f"lookup_partner error: {e}")
            return {"response": f"Let me note your interest in service at {city}. "
                "Our team will follow up with available options."}

    # =========================================================================
    # TOOL 17: ASSESS TRIP TIMING
    # =========================================================================
    @AgentBase.tool(
        name="assess_trip_timing",
        description="Check if pickup time gives enough buffer for the flight. Warn if tight.",
        parameters={
            "pickup_time": {"type": "string", "description": "HH:MM 24h"},
            "flight_time": {"type": "string", "description": "Flight departure HH:MM 24h"},
            "drive_minutes": {"type": "integer", "description": "Estimated drive time"},
            "is_international": {"type": "boolean", "description": "International flight?"},
        },
    )
    def assess_trip_timing(self, args, raw_data):
        try:
            pickup_h, pickup_m = map(int, args.get("pickup_time", "0:0").split(":"))
            flight_h, flight_m = map(int, args.get("flight_time", "0:0").split(":"))
            drive_min = args.get("drive_minutes", 30)
            is_intl = args.get("is_international", False)

            pickup_total = pickup_h * 60 + pickup_m
            flight_total = flight_h * 60 + flight_m
            buffer = flight_total - pickup_total - drive_min
            recommended = 180 if is_intl else 120

            if buffer < 60:
                return {"response": f"WARNING: Only {buffer} minutes between pickup and flight "
                    f"(after {drive_min} min drive). This is very tight. Recommend earlier pickup."}
            elif buffer < recommended:
                return {"response": f"The timing is a bit snug — {buffer} minutes of buffer. "
                    f"I'd recommend picking up {recommended - buffer} minutes earlier to be safe."}
            return {"response": f"Timing looks good — {buffer} minutes of buffer after the drive. "
                "Plenty of time for check-in and security."}
        except Exception as e:
            logger.error(f"assess_trip_timing error: {e}")
            return {"response": "I'd recommend arriving at the airport at least 2 hours before "
                "a domestic flight and 3 hours for international."}

    # =========================================================================
    # TOOL 18: LOG INCIDENT AND NOTIFY
    # =========================================================================
    @AgentBase.tool(
        name="log_incident_and_notify",
        description="Log a service incident and alert the team. Use when something goes wrong.",
        parameters={
            "incident_type": {"type": "string", "description": "transfer_failed, tool_error, guest_complaint, etc."},
            "details": {"type": "string"},
            "guest_phone": {"type": "string"},
        },
    )
    def log_incident_and_notify(self, args, raw_data):
        try:
            payload = {
                "incident_type": args.get("incident_type", "general"),
                "details": args.get("details", ""),
                "guest_phone": args.get("guest_phone", ""),
                "agent": "alex",
                "status": "open",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            requests.post(f"{SUPABASE_URL}/rest/v1/incidents",
                headers=SUPABASE_HEADERS, json=payload, timeout=5)
            # SMS alert to DeAngelo
            logger.info(f"Incident logged: {payload['incident_type']}")
            return {"response": "I've logged this and alerted our team leader. "
                "Someone will follow up with you within 15 minutes.",
                "action": [{"SWML": {"version": "1.0.0", "sections": {"main": [
                    {"send_sms": {"to_number": DEANGELO_CELL, "from_number": ALEX_NUMBER,
                        "body": f"🚨 ALEX INCIDENT: {payload['incident_type']} — {payload['details']} — Guest: {payload['guest_phone']}"}}
                ]}}}]}
        except Exception as e:
            logger.error(f"log_incident error: {e}")
            return {"response": "I've noted this issue. Our team will follow up shortly."}

    # =========================================================================
    # POST-CALL: DeepSeek Analysis (called via SignalWire post_prompt webhook)
    # =========================================================================
    def on_summary(self, summary, raw_data=None):
        """Called by SignalWire after call ends. Sends transcript to DeepSeek for analysis."""
        logger.info(f"Call summary received: {summary.get('summary', 'N/A')[:100]}")
        if not DEEPSEEK_API_KEY:
            logger.info("DeepSeek not configured — skipping post-call analysis")
            return

        try:
            from deepseek_brain import DeepSeekBrain
            brain = DeepSeekBrain()

            # Save transcript
            transcript = summary.get("transcript", summary.get("summary", ""))
            reservation_id = summary.get("reservation_id", "")

            # Analyze the conversation
            analysis = brain.analyze_conversation(transcript)
            if analysis.get("success"):
                brain.save_analysis("conversation", reservation_id or "unknown", analysis.get("analysis", {}))
                logger.info("Post-call DeepSeek analysis saved")
        except ImportError:
            logger.warning("deepseek_brain.py not found — post-call analysis skipped")
        except Exception as e:
            logger.error(f"Post-call analysis error: {e}")


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    agent = AlexAgent()
    logger.info("Starting Alex v3.4.0 on port 8080...")
    agent.serve(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
