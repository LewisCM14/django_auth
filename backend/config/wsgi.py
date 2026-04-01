"""WSGI application for production deployment.

Creates the WSGI application object used by production web servers.
On Windows Server 2022, this is served via IIS using wfastcgi. On Unix/Linux,
alternatives include Gunicorn or uWSGI.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
