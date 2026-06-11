import time
from fastapi.testclient import TestClient
import main

client = TestClient(main.app)

# Check task list
resp = client.get('/api/tasks')
tasks = resp.json()
print('Tasks type:', type(tasks))
print('Tasks keys:', tasks.keys() if isinstance(tasks, dict) else 'list')
if isinstance(tasks, dict):
    print('Tasks items:', list(tasks.keys())[:5])
    if 'items' in tasks:
        print('Items count:', len(tasks['items']))
        for t in tasks['items']:
            if t.get('task_id') == 'task_1781169883515_2aa66b':
                print('Found task:', t['status'], t['progress'])
                break
