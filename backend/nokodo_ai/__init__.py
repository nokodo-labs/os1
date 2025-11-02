"""
Template SDK/Service Layer Package.

IMPORTANT: Rename this package from 'project_slug' to your actual project name.

This package contains business logic, services, and utilities that are independent
of the FastAPI application layer. It can be packaged separately and distributed
via pip, allowing other projects to import and use this logic without the web layer.

Example usage after renaming to 'myproject':
	from myproject import some_service
	result = some_service.do_something()

Structure:
	services/ - Business logic and service layer
	utils/ - Utility functions and helpers
	types/ - Type definitions and protocols
"""

__version__ = "0.1.0"
