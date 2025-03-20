import os
import json
import pickle
from datetime import datetime, timedelta
import pytz
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class CalendarBackgroundTasks:
    def __init__(self):
        self.TOKEN_DIR = "/home/sciproject/mysite/tokens"
        self.EVENTS_DIR = "/home/sciproject/mysite/events"
        self.EVENTS_FILE = os.path.join(self.EVENTS_DIR, "all_events.json")
        self.TIMEZONE = pytz.timezone('Europe/Paris')
        
        # Mots-clés pour filtrer les événements pertinents
        self.KEYWORDS = [
            "Devoir", "homework", "soutenance", "Contrôle", "examen", "Deadline",
            "Reunion", "session", "meet", "à remettre", "Test", "interrogation",
            "Démonstration", "obligatoire", "Présentation", "Demo", "interro", "à rendre"
        ]
        
        # Période pour chercher les événements (7 jours dans le futur par défaut)
        self.LOOKUP_DAYS = 7

    def load_stored_events(self):
        """Charge les événements stockés"""
        if os.path.exists(self.EVENTS_FILE):
            with open(self.EVENTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_events(self, events_data):
        """Sauvegarde les événements"""
        with open(self.EVENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(events_data, f, ensure_ascii=False, indent=4)

    def get_user_credentials(self, token_file):
        """Récupère les credentials d'un utilisateur"""
        try:
            with open(token_file, 'rb') as token:
                return pickle.load(token)
        except Exception as e:
            print(f"Erreur de chargement du token: {str(e)}")
            return None

    def is_relevant_event(self, event):
        """Vérifie si l'événement est pertinent selon les mots-clés"""
        title = event.get('summary', '').lower()
        description = event.get('description', '').lower() if event.get('description') else ''
        
        return any(keyword.lower() in title or keyword.lower() in description 
                  for keyword in self.KEYWORDS)

    def clean_event(self, event):
        """Nettoie et formate un événement"""
        if not self.is_relevant_event(event):
            return None

        start = event.get('start', {})
        end = event.get('end', {})
        
        return {
            'id': event.get('id'),
            'title': event.get('summary', 'Sans titre'),
            'start': start.get('dateTime') or start.get('date'),
            'end': end.get('dateTime') or end.get('date'),
            'description': event.get('description'),
            'calendar_id': event.get('calendarId'),
            'calendar_name': event.get('calendarName', 'Calendrier principal'),
            'last_updated': datetime.now(self.TIMEZONE).isoformat()
        }

    def process_user_events(self, user_email, credentials):
        """Traite les événements d'un utilisateur"""
        try:
            service = build('calendar', 'v3', credentials=credentials)
            
            # Calcul des dates de début et fin
            now = datetime.now(self.TIMEZONE)
            end_date = now + timedelta(days=self.LOOKUP_DAYS)
            
            # Récupération des calendriers de l'utilisateur
            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            all_events = []
            for calendar in calendars:
                try:
                    events_result = service.events().list(
                        calendarId=calendar['id'],
                        timeMin=now.isoformat(),
                        timeMax=end_date.isoformat(),
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    
                    # Ajoute les informations du calendrier à chaque événement
                    events = events_result.get('items', [])
                    for event in events:
                        event['calendarId'] = calendar['id']
                        event['calendarName'] = calendar.get('summary', 'Calendrier inconnu')
                        
                    all_events.extend(events)
                    
                except Exception as e:
                    print(f"Erreur pour le calendrier {calendar['id']}: {str(e)}")
                    continue
            
            return all_events
            
        except Exception as e:
            print(f"Erreur de traitement pour {user_email}: {str(e)}")
            return []

    def update_events(self):
        """Met à jour les événements pour tous les utilisateurs"""
        all_stored_events = self.load_stored_events()
        
        # Parcours des tokens utilisateurs
        for filename in os.listdir(self.TOKEN_DIR):
            if filename.endswith('.pickle'):
                user_email = filename[:-7]  # Retire '.pickle'
                token_path = os.path.join(self.TOKEN_DIR, filename)
                
                credentials = self.get_user_credentials(token_path)
                if not credentials or not credentials.valid:
                    print(f"Token invalide pour {user_email}")
                    continue
                
                # Récupération et traitement des événements
                raw_events = self.process_user_events(user_email, credentials)
                
                # Nettoyage et filtrage des événements
                cleaned_events = []
                for event in raw_events:
                    cleaned_event = self.clean_event(event)
                    if cleaned_event:
                        cleaned_events.append(cleaned_event)
                
                # Mise à jour des événements stockés
                if cleaned_events:
                    all_stored_events[user_email] = {
                        'last_update': datetime.now(self.TIMEZONE).isoformat(),
                        'events': cleaned_events
                    }
                elif user_email in all_stored_events:
                    # Si pas d'événements pertinents, on peut soit supprimer l'entrée
                    # soit garder une entrée vide avec la date de dernière mise à jour
                    all_stored_events[user_email] = {
                        'last_update': datetime.now(self.TIMEZONE).isoformat(),
                        'events': []
                    }
        
        # Sauvegarde des mises à jour
        self.save_events(all_stored_events)
        print("Mise à jour des événements terminée")

def main():
    """Point d'entrée pour la tâche planifiée"""
    task = CalendarBackgroundTasks()
    task.update_events()

if __name__ == "__main__":
    main()