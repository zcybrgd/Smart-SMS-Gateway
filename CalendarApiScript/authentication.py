import os
import pickle
from datetime import timedelta
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from flask import session, redirect, url_for, request

class Auth:
    def __init__(self, app):
        self.app = app
        self.SCOPES = [
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
            'https://www.googleapis.com/auth/calendar.readonly',
            'https://www.googleapis.com/auth/calendar.events.readonly'
        ]
        self.CLIENT_SECRETS_FILE = os.environ.get("CLIENT_SECRETS_PATH")
        self.TOKEN_DIR = os.environ.get("TOKEN_DIR")
        self.REDIRECT_URI = os.environ.get("REDIRECT_URI")

        if not os.path.exists(self.TOKEN_DIR):
            os.makedirs(self.TOKEN_DIR)

        self.init_auth()
        self.setup_auth_routes()

    def init_auth(self):
        """Initialise les paramètres d'authentification"""
        self.app.secret_key = os.environ.get('FLASK_SECRET_KEY')
        self.app.config['SESSION_COOKIE_SECURE'] = True
        self.app.config['SESSION_COOKIE_HTTPONLY'] = True
        self.app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        self.app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

        @self.app.before_request
        def make_session_permanent():
            session.permanent = True

    def check_token_validity(self, user_email):
        """Vérifie si le token existe et est valide"""
        token_path = os.path.join(self.TOKEN_DIR, f"{user_email}.pickle")

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

    def require_auth(self, f):
        """Décorateur pour protéger les routes"""
        def wrapper(*args, **kwargs):
            if 'user_email' not in session:
                return redirect(url_for('authorize'))

            credentials = self.check_token_validity(session['user_email'])
            if not credentials:
                return redirect(url_for('authorize'))

            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper

    def setup_auth_routes(self):
        """Configure les routes d'authentification"""
        @self.app.route("/")
        def index():
            if 'user_email' in session:
                credentials = self.check_token_validity(session['user_email'])
                if credentials:
                    return redirect(url_for('events_page'))
            return "Bienvenue ! <a href='/authorize'>Connecte-toi avec Google</a>"

        @self.app.route("/authorize")
        def authorize():
            if 'user_email' in session:
                credentials = self.check_token_validity(session['user_email'])
                if credentials:
                    return redirect(url_for('events_page'))

            flow = Flow.from_client_secrets_file(
                self.CLIENT_SECRETS_FILE,
                scopes=self.SCOPES,
                redirect_uri=self.REDIRECT_URI
            )

            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )

            session['state'] = state
            return redirect(authorization_url)

        @self.app.route("/callback")
        def callback():
            try:
                flow = Flow.from_client_secrets_file(
                    self.CLIENT_SECRETS_FILE,
                    scopes=self.SCOPES,
                    redirect_uri=self.REDIRECT_URI,
                    state=session['state']
                )

                flow.fetch_token(authorization_response=request.url)
                credentials = flow.credentials

                oauth_service = build('oauth2', 'v2', credentials=credentials)
                user_info = oauth_service.userinfo().get().execute()
                user_email = user_info.get('email', 'unknown')

                session['user_email'] = user_email
                session['user_name'] = user_info.get('name', 'Utilisateur')
                session.modified = True

                token_path = os.path.join(self.TOKEN_DIR, f"{user_email}.pickle")
                with open(token_path, 'wb') as token_file:
                    pickle.dump(credentials, token_file)

                return redirect(url_for('events_page'))

            except Exception as e:
                return f"Erreur callback: {str(e)}", 500