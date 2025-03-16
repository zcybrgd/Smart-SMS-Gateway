import requests
import subprocess
from flask import current_app
from app import db
from app.models import User
from datetime import datetime, timedelta
# --- API Endpoint ---
EVENTS_URL = "https://sciproject.pythonanywhere.com/all-users-events"

# --- RaspiSMS API Details ---
RASPI_SMS_API_KEY = PROCESS.env.RASPISMSKEY
RASPI_SMS_URL = "http://localhost:8080//api/scheduled/"
ID_PHONE = PROCESS.env.IDPHONE

def fetch_and_send_sms():
    """Fetch events from API and send SMS notifications."""
    from app import create_app
    app = create_app()
    with app.app_context():
        try:
            print("\n--- Fetching events ---")
            response = requests.get(EVENTS_URL)
            if response.status_code != 200:
                print(f"[ERROR] Failed to fetch events. Status Code: {response.status_code}")
                return

            data = response.json()
            events = data.get("events", [])

            print(f"Total events fetched: {len(events)}")
            if not events:
                print("[INFO] No new events to process.")
                return

            for event in events:
                user = User.query.filter_by(email=event["user_email"]).first()
                print(user.email, user.is_admin)
                if not user:
                    print(f"[WARNING] User {event['user_email']} not found. Skipping event: {event['title']}")
                    continue

                print(f"\n[INFO] Processing event '{event['title']}' for user: {user.email}")

                formatted_time = datetime.strptime(event["start"][:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
                sms_text = f"Reminder: {event['title']} at {event.get('location', 'Unknown location')} on {formatted_time}"
                phone_number = user.phone_number.replace("+", "%2B")  # Ensure proper formatting
                at_time = (datetime.now() + timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S")
                print(f"[INFO] Preparing SMS for {user.email} ({user.phone_number})")
                print(f"[SMS CONTENT]: {sms_text}")

                # Construct cURL command to send SMS
                curl_command = f"""curl -X POST "{RASPI_SMS_URL}" \
                -H 'X-Api-Key: {RASPI_SMS_API_KEY}' \
                -d 'text={sms_text}' \
                -d 'numbers={phone_number}' \
                -d 'id_phone={ID_PHONE}' \
                -d 'at={at_time}'""

                # Execute cURL
                process = subprocess.run(curl_command, shell=True, capture_output=True, text=True)

                # Log the response
                print(f"[SUCCESS] SMS sent to {user.email} ({user.phone_number})")
                print(f"[SMS API RESPONSE]: {process.stdout.strip()}")
                if process.stderr.strip():
                    print(f"[ERROR] SMS API Error: {process.stderr.strip()}")

        except Exception as e:
            print(f"[FATAL ERROR] Exception occurred: {e}")

#this is for testing, but this service will run as a scheduler in the system
if __name__ == "__main__":
    fetch_and_send_sms()
