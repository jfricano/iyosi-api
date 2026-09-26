import json
from api.main import app
with open('docs/openapi.json','w') as file:
    json.dump(app.openapi(),file,indent=2)
    file.write('\n')
