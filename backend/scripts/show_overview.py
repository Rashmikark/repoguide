import json
import sys

import psycopg

from backend.app.config import settings
from backend.app.onboarding.facts import load_repo_facts
from backend.app.onboarding.overview import make_overview
from backend.app.tracing import langfuse

repo_id = int(sys.argv[1])
with psycopg.connect(settings.database_url) as conn:
    facts = load_repo_facts(conn, repo_id)
    overview = make_overview(conn, facts)

print(json.dumps(overview, indent=2))
langfuse.flush()