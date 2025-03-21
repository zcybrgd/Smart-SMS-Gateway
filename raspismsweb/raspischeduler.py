import requests  
import subprocess  
import json  
import os  
from flask import current_app  
from app import db  
from app.models import User  
from datetime import datetime, timedelta  
from apscheduler.schedulers.background import BackgroundScheduler  


EVENTS_URL = os.environ['GCURL']  


RASPI_SMS_API_KEY = os.environ['RASPISMSAPI']
RASPI_SMS_URL = "http://localhost:8080/api/scheduled/"   
ID_PHONE = os.environ['IDPHONE']  

# --- Logs ---  
SENT_SMS_FILE = os.environ['LOGPATH']  

def load_sent_sms():  
    """Load sent SMS records from JSON file."""  
    if os.path.exists(SENT_SMS_FILE):  
        with open(SENT_SMS_FILE, "r") as file:  
            return json.load(file)  
    return {}   

def save_sent_sms(sent_sms):  
    """Save updated sent SMS records to JSON file."""  
    with open(SENT_SMS_FILE, "w") as file:  
        json.dump(sent_sms, file, indent=4)  

def fetch_and_store_events():  
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

            # Load sent SMS records  
            sent_sms = load_sent_sms()  

            for event in events:  
                user = User.query.filter_by(email=event["user_email"]).first()  
                if not user:  
                    print(f"[WARNING] User {event['user_email']} not found. Skipping event: {event['title']}")  
                    continue  

                event_id = event["id"]  
                user_email = user.email  

                #Check if SMS was already sent for this event-user pair (so we can avoid duplicate)
                if event_id in sent_sms and user_email in sent_sms[event_id]:  
                    print(f"[INFO] SMS already sent for event '{event['title']}' to {user_email}. Skipping.")  
                    continue  

                print(f"\n[INFO] Processing event '{event['title']}' for user: {user_email}")  

                # Format event details  
                formatted_time = datetime.strptime(event["start"][:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")  
                sms_text = f"Reminder: {event['title']} at {event.get('location', 'Unknown location')} on {formatted_time}"  
                phone_number = user.phone_number.replace("+", "%2B")  # Ensure proper formatting  
                at_time = (datetime.now() + timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S")  

                print(f"[INFO] Preparing SMS for {user_email} ({user.phone_number})")  
                print(f"[SMS CONTENT]: {sms_text}")  

                # Construct cURL command to send SMS  
                curl_command = f"""curl -X POST "{RASPI_SMS_URL}" \
-H 'X-Api-Key: {RASPI_SMS_API_KEY}' \
-d 'text={sms_text}' \
-d 'numbers={phone_number}' \
-d 'id_phone={ID_PHONE}' \
-d 'at={at_time}'"""  

                #Execute cURL  (we couldve used requests python lib, but i just felt like it)
                process = subprocess.run(curl_command, shell=True, capture_output=True, text=True)  

                #logs stuff
                print(f"[SUCCESS] SMS sent to {user_email} ({user.phone_number})")  
                print(f"[SMS API RESPONSE]: {process.stdout.strip()}")  
                if process.stderr.strip():  
                    print(f"[ERROR] SMS API Error: {process.stderr.strip()}")  

                #Update the "sent" SMS records  
                if event_id not in sent_sms:  
                    sent_sms[event_id] = []  
                sent_sms[event_id].append(user_email)  
                save_sent_sms(sent_sms)  # Save updated record  

        except Exception as e:  
            print(f"[FATAL ERROR] Exception occurred: {e}")  

#launch the scheduler stuff
scheduler = BackgroundScheduler()  
scheduler.add_job(fetch_and_store_events, "interval", minutes=2)  

if scheduler.state != 1:  
    scheduler.start()  
    print("Scheduler started.")  
else:  
    print("Scheduler is already running.")  
