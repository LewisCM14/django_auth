"""ASGI application for production deployment.

Creates the ASGI application object used by ASGI servers (e.g., Uvicorn).
On Windows Server 2022, this is served via IIS using HttpPlatformHandler and Uvicorn.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

# In local development with Uvicorn, serve /static/* directly from Django so
# Swagger UI sidecar assets load without requiring collectstatic + external web server.
application = (
    ASGIStaticFilesHandler(django_asgi_app) if settings.DEBUG else django_asgi_app
)
