"""ASGI application for production deployment.

Creates the ASGI application object used by ASGI servers (e.g., Uvicorn).
On Windows Server 2022, this is served via IIS using HttpPlatformHandler and Uvicorn.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
