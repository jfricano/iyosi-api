"""Set a non-production signing key before test modules import the application."""
import os

os.environ.setdefault('IYOSI_SECRET','test-secret-0123456789-0123456789')
