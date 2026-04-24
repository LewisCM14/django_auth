## Transition Plan: wfastcgi → HttpPlatformHandler with Uvicorn (No Legacy Compatibility)

### 1. Overview
Replace wfastcgi with IIS HttpPlatformHandler, running Django via Uvicorn (ASGI). IIS will handle Windows Authentication and inject the authenticated username as an HTTP header (X-Remote-User) for Django to consume. No support for legacy REMOTE_USER or wfastcgi is required.

---

### 2. IIS & Infrastructure Changes

1. **Enable Windows Authentication** on the IIS site.
2. **Configure URL Rewrite** (or similar IIS module) to:
	- Set the `X-Remote-User` HTTP header to the value of `{REMOTE_USER}` for authenticated requests.
	- Remove any incoming `X-Remote-User` header from client requests to prevent spoofing.
3. **Install and configure HttpPlatformHandler**:
	- Set the process path to launch Uvicorn (e.g., `python -m uvicorn config.asgi:application --host 127.0.0.1 --port %HTTP_PLATFORM_PORT%`).
	- Ensure the backend listens on the port provided by HttpPlatformHandler.
4. **Remove all wfastcgi configuration** from IIS and deployment scripts.

---

### 3. Django Codebase Changes

1. **Authentication Middleware**
	- Update the authentication middleware to extract the username from `request.META["HTTP_X_REMOTE_USER"]`.
	- Do not use `REMOTE_USER` for production.
	- Example:
	  ```python
	  remote_user = request.META.get("HTTP_X_REMOTE_USER")
	  ```
2. **Security**
	- Only trust `X-Remote-User` when set by IIS. Document that IIS must strip this header from incoming requests.
3. **Testing**
	- Update tests to inject `X-Remote-User` as the user identity header.
4. **Documentation**
	- Update all deployment and architecture docs to reference HttpPlatformHandler, Uvicorn, and the new header-based identity flow.
	- Remove all references to wfastcgi and REMOTE_USER.

---

### 4. Deployment Pipeline

1. **Update environment.yml** and deployment scripts to:
	- Remove wfastcgi.
	- Add Uvicorn as a dependency.
	- Ensure the app is started with Uvicorn in production.
2. **Document the new process startup** (e.g., `python -m uvicorn config.asgi:application ...`).

---

### 5. End-to-End Validation

1. **Test authentication flow:**
	- IIS authenticates user, injects `X-Remote-User`, proxies to Uvicorn.
	- Django receives the correct username in `request.META["HTTP_X_REMOTE_USER"]`.
2. **Test all endpoints and error cases** (401, 403, etc.) with and without the header.
3. **Review logs and security events** to ensure correct user correlation.

---

### 6. Risks & Mitigations

- **Header spoofing:** IIS must strip `X-Remote-User` from incoming requests before setting it from Windows Authentication.
- **Process management:** Ensure Uvicorn is robustly managed (restarts, logging, etc.).
- **Testing:** Validate the new flow in dev, staging, and production environments.

---

### 7. Summary

- All production identity is now sourced from `X-Remote-User` set by IIS.
- Uvicorn is the only supported backend process manager.
- No legacy or wfastcgi compatibility is maintained.
