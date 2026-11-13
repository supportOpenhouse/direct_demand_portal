"""Print the 99acres login as JSON on stdout, from backend/.env. Never writes it anywhere.
Run from backend/ (acres_call.sh does). Refuses to print blanks — an empty login is a
failed attempt at 99acres and counts toward any lockout."""
import json
import sys

from dotenv import dotenv_values

v = dotenv_values(".env")
user, password = v.get("ACRES_DASHBOARD_USERNAME") or "", v.get("ACRES_DASHBOARD_PASSWORD") or ""
if not (user and password):
    sys.exit("ACRES_DASHBOARD_USERNAME / ACRES_DASHBOARD_PASSWORD missing in backend/.env")
sys.stdout.write(json.dumps({"username": user, "password": password}))
