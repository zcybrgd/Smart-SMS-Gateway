import os
import pickle
import glob
import json
from datetime import datetime, timedelta
import pytz
from flask import Flask, redirect, url_for, session, request, render_template_string
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
import warnings

warnings.filterwarnings('ignore', message='file_cache is only supported with oauth2client<4.0.0')

# Configuration
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Mots-clés pour le filtrage des événements
KEYWORDS = [
    "Devoir", "homework", "soutenance", "Contrôle", "examen", "Deadline",
    "Reunion", "session", "meet", "à remettre", "Test", "interrogation",
    "Démonstration", "obligatoire", "Présentation", "Demo","interro", "à rendre"
]

SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events.readonly'
]

CLIENT_SECRETS_FILE = "/home/sciproject/mysite/credentials.json"
TOKEN_DIR = "/home/sciproject/mysite/tokens"
EVENTS_DIR = "/home/sciproject/mysite/events"
EVENTS_FILE = os.path.join(EVENTS_DIR, "all_events.json")
REDIRECT_URI = "https://sciproject.pythonanywhere.com/callback"
TIMEZONE = pytz.timezone('Europe/Paris')

for directory in [TOKEN_DIR, EVENTS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

app = Flask(__name__)
app.secret_key = '7a9e6d4b3f2c1a8d5b7e9f4c2a1d8b3e6f4c2a9d7b5e3f1c8a6d4b2e9f7c3a5'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

def clean_event(event):
    """Nettoie et filtre les données d'un événement.
    Ne garde que les événements contenant les mots-clés définis."""
    title = event.get('summary', '').lower()
    description = event.get('description', '').lower() if event.get('description') else ''

    # Vérifie si l'événement contient un des mots-clés
    has_keywords = any(keyword.lower() in title or keyword.lower() in description
                      for keyword in KEYWORDS)

    # Si pas de mot-clé, on ignore l'événement
    if not has_keywords:
        return None

    # Extraction de la date
    start_info = event.get('start', {})
    start_datetime = start_info.get('dateTime') or start_info.get('date')

    event_date = None
    if start_datetime:
        try:
            if 'T' in start_datetime:
                event_date = start_datetime.split('T')[0]
            else:
                event_date = start_datetime
        except:
            event_date = None

    # Construction de l'événement filtré sans calendar_id et calendar_name
    cleaned_event = {
        'id': event.get('id'),
        'title': event.get('summary', 'Sans titre'),
        'date': event_date,
        'start': start_datetime,
        'end': event.get('end', {}).get('dateTime') or event.get('end', {}).get('date'),
        'description': event.get('description'),
        'location': event.get('location')
    }

    return cleaned_event

def is_duplicate_event(event1, event2):
    """Vérifie si deux événements sont des doublons"""
    return (
        event1['title'] == event2['title'] and
        event1['start'] == event2['start'] and
        event1['end'] == event2['end']
    )
def get_calendar_list(service):
    """Récupère la liste des calendriers de l'utilisateur"""
    try:
        calendar_list = service.calendarList().list().execute()
        return calendar_list.get('items', [])
    except Exception as e:
        print(f"Erreur lors de la récupération des calendriers: {str(e)}")
        return []

def get_all_calendar_events(service, date_obj):
    """Récupère les événements de tous les calendriers de l'utilisateur."""
    all_events = []

    try:
        calendars = get_calendar_list(service)
        print(f"Calendriers récupérés: {len(calendars)}")

        # Définir la plage horaire en UTC
        start = date_obj.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
        end = date_obj.replace(hour=23, minute=59, second=59).isoformat() + 'Z'

        for calendar in calendars:
            calendar_id = calendar['id']
            calendar_name = calendar.get('summary', 'Calendrier inconnu')

            try:
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=start,
                    timeMax=end,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()

                events = events_result.get('items', [])

                for event in events:
                    event['calendarId'] = calendar_id
                    event['calendarName'] = calendar_name
                    all_events.append(event)

            except HttpError as e:
                continue

        return all_events

    except Exception as e:
        return []

def update_user_events(user_email, date, events):
    """Met à jour les événements d'un utilisateur en évitant les doublons"""

    all_events = load_all_events()
    cleaned_events = []

    # Filtrage des événements
    for event in events:
        cleaned_event = clean_event(event)
        if cleaned_event is not None:
            # Vérifier si l'événement est un doublon
            is_duplicate = any(
                is_duplicate_event(cleaned_event, existing_event)
                for existing_event in cleaned_events
            )
            if not is_duplicate:
                cleaned_events.append(cleaned_event)


    # Mise à jour du stockage
    if cleaned_events:
        if user_email not in all_events:
            all_events[user_email] = {}

        all_events[user_email][date] = {
            'last_update': datetime.now().isoformat(),
            'events': cleaned_events
        }

        print(f"Stored {len(cleaned_events)} events for {user_email} on {date}")
    else:
        # Supprimer la date si aucun événement
        if user_email in all_events and date in all_events[user_email]:
            del all_events[user_email][date]
            if not all_events[user_email]:
                del all_events[user_email]

    save_all_events(all_events)

def load_all_events():
    """Charge tous les événements depuis le fichier JSON"""
    if os.path.exists(EVENTS_FILE):
        try:
            with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Erreur chargement événements: {str(e)}")
            return {}
    return {}

def save_all_events(events_data):
    """Sauvegarde tous les événements dans le fichier JSON"""
    try:
        with open(EVENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(events_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Erreur sauvegarde événements: {str(e)}")

def check_token_validity(token_path):
    """Vérifie si le token existe et est valide"""
    if not os.path.exists(token_path):
        return None

    try:
        with open(token_path, 'rb') as token_file:
            credentials = pickle.load(token_file)

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            with open(token_path, 'wb') as token_file:
                pickle.dump(credentials, token_file)
            return credentials

    except Exception as e:
        print(f"Erreur token: {str(e)}")
        return None

    return None

def auto_authenticate():

    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_email' in session:
                token_path = os.path.join(TOKEN_DIR, f"{session['user_email']}.pickle")
                credentials = check_token_validity(token_path)

                if credentials:
                    return f(*args, **kwargs)

            return redirect(url_for('authorize'))
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route("/")
def index():
    if 'user_email' in session:
        token_path = os.path.join(TOKEN_DIR, f"{session['user_email']}.pickle")
        credentials = check_token_validity(token_path)
        if credentials:
            return redirect(url_for('events_page'))

    return "Bienvenue ! <a href='/authorize'>Connecte-toi avec Google</a>"

@app.route("/authorize")
def authorize():
    if 'user_email' in session:
        token_path = os.path.join(TOKEN_DIR, f"{session['user_email']}.pickle")
        credentials = check_token_validity(token_path)
        if credentials:
            return redirect(url_for('events_page'))

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    session['state'] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
            state=session['state']
        )

        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials

        oauth_service = build('oauth2', 'v2', credentials=credentials)
        calendar_service = build('calendar', 'v3', credentials=credentials)

        calendars = get_calendar_list(calendar_service)

        user_info = oauth_service.userinfo().get().execute()
        user_email = user_info.get('email', 'unknown')

        session['user_email'] = user_email
        session['user_name'] = user_info.get('name', 'Utilisateur')
        session.modified = True

        token_path = os.path.join(TOKEN_DIR, f"{user_email}.pickle")
        with open(token_path, 'wb') as token_file:
            pickle.dump(credentials, token_file)

        return redirect(url_for('events_page'))

    except Exception as e:
        return f"Erreur callback: {str(e)}", 500
@app.route("/events", methods=['GET', 'POST'])
@auto_authenticate()
def events_page():
    try:
        user_email = session['user_email']
        token_path = os.path.join(TOKEN_DIR, f"{user_email}.pickle")
        credentials = check_token_validity(token_path)

        test_date = "2024-12-12"

        # Get date from request or use test date
        if request.method == 'POST':
            date = request.form.get('date', test_date)
        else:
            date = request.args.get('date', test_date)

        # Build calendar service
        service = build('calendar', 'v3', credentials=credentials)
        date_obj = datetime.strptime(date, '%Y-%m-%d')

        # Get and update events
        all_events = get_all_calendar_events(service, date_obj)
        update_user_events(user_email, date, all_events)

        # Get stored events
        all_stored_events = load_all_events()
        user_events = all_stored_events.get(user_email, {}).get(date, {}).get('events', [])

        # Return JSON response with events and user info
        response_data = {
            'user': {
                'email': session.get('user_email', ''),
                'name': session.get('user_name', 'Utilisateur')
            },
            'date': date,
            'events': user_events
        }

        return json.dumps(response_data, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            'error': str(e)
        }), 500
