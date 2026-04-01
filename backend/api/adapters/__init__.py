"""Adapters package for the API application.

The adapter layer provides a decoupled interface to enterprise data sources (LDAP,
external REST APIs, databases, etc.) before the data is passed to the services layer
for normalization and BFF-style transformation.

Each adapter handles a single external data source and is responsible for:
- Source-specific authentication and connection management
- Protocol-level details (retries, timeouts, error handling)
- Minimal parsing of raw responses into native Python structures
- Validation of required fields

Adapters do not apply business rules or normalization — that responsibility belongs
to the services layer. This separation allows the application to extend and scale
by adding new enterprise data sources without modifying core business logic.

Example adapter structure:

    class LDAPAdapter:
        '''Wraps ldap3 connection and group membership queries.'''
        
        def get_user_groups(self, username: str) -> list[str]:
            '''Query user's AD group memberships. Returns raw group DNs.'''
            # LDAP connection, search, and minimal parsing only
            ...
    
    class UserDirectoryAdapter:
        '''Wraps call to corporate user directory service.'''
        
        def get_user_details(self, employee_id: str) -> dict:
            '''Fetch employee record from directory. Returns raw data.'''
            # HTTP GET, minimal parsing only
            ...

The services layer then:
- Invokes one or more adapters
- Normalizes and joins the data
- Maps external identifiers to application roles/permissions
- Returns a canonical response object for the API view
"""
