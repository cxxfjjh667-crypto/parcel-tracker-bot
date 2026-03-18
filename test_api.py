import os
from dotenv import load_dotenv
load_dotenv()
from api.etrackings_client import ETrackingsClient
import json

client = ETrackingsClient()
res = client.track('793378072631', 'jt-express')
print(json.dumps(res, indent=2, ensure_ascii=False))
