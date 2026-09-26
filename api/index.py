import sys
import os

# Add parent directory to path so modules in root can be imported
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Support selecting which application to serve via APP_CHOICE environment variable
# Defaults to happiness_server.py (HappyBorough), or set APP_CHOICE=server for PlanPulse
app_choice = os.environ.get('APP_CHOICE', 'happiness').strip().lower()

if 'happiness' in app_choice:
    from happiness_server import HappinessHandler as SelectedHandler
else:
    from server import PlanPulseHandler as SelectedHandler

class handler(SelectedHandler):
    """Vercel Python Serverless Function entry point."""
    pass
