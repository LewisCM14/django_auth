"""ASGI application for production deployment.

Creates the ASGI application object used by ASGI servers (e.g., Uvicorn).
On Windows Server 2022, this is served via IIS using HttpPlatformHandler and Uvicorn.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

# Serve bundled static assets from Django in every mode so the Swagger UI
# sidecar files are available even when deployment does not offload /static/*.
application = ASGIStaticFilesHandler(django_asgi_app)
