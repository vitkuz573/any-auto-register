from application.config import ConfigService
import json

cs = ConfigService()
opts = cs.get_options()
with open('config_options.json', 'w', encoding='utf-8') as f:
    json.dump(opts['mailbox_providers'], f, ensure_ascii=False, indent=2)
print('Saved to config_options.json')
