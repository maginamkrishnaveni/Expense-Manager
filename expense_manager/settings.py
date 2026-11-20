import os
from pathlib import Path

# Load .env only if it exists (local dev) — not required on PythonAnywhere
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-flat-expense-manager-secret-key-2024')
DEBUG = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'django.contrib.sessions',
    'expenses',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Session stored in signed cookies (no DB needed for sessions)
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7   # 7 days
SESSION_COOKIE_HTTPONLY = True

ROOT_URLCONF = 'expense_manager.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'expenses.context_processors.flat_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'expense_manager.wsgi.application'

# Database — SQLite by default (works everywhere, no setup needed).
# To use PostgreSQL (recommended in production / on PaaS where the
# filesystem is ephemeral), set the DATABASE_URL env var, e.g.
#   postgres://user:pass@host:5432/dbname
# dj_database_url is optional: if the package isn't installed we simply
# keep SQLite, so local dev still works without reinstalling deps.
try:
    import dj_database_url
except ImportError:
    dj_database_url = None

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

_db_url = os.getenv('DATABASE_URL')
if _db_url and dj_database_url is not None:
    DATABASES['default'] = dj_database_url.parse(_db_url, conn_max_age=600)

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
