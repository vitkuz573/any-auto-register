import time
from fastapi.testclient import TestClient
import main

with TestClient(main.app) as client:
    # Create register task for Kiro with mailtm
    resp = client.post('/api/tasks/register', json={
        'platform': 'kiro',
        'count': 1,
        'executor_type': 'protocol',
        'extra': {
            'mail_provider': 'mailtm_api',
        }
    })
    task = resp.json()
    print('Task created:', task['task_id'])
    
    # Wait and check progress
    for i in range(12):
        time.sleep(10)
        resp = client.get('/api/tasks')
        tasks = resp.json()
        item = next((t for t in tasks['items'] if t['task_id'] == task['task_id']), None)
        if item:
            print(f'After {10*(i+1)}s: status={item["status"]}, progress={item["progress"]}')
            if item['status'] in ('succeeded', 'failed', 'cancelled'):
                # Get logs
                log_resp = client.get(f'/api/tasks/{task["task_id"]}/logs')
                logs = log_resp.json()
                print('Logs:', logs.get('items', [])[:5])
                break
        else:
            print(f'Task not found after {10*(i+1)}s')
    else:
        print('Task still running after 120s')
        # Get logs anyway
        log_resp = client.get(f'/api/tasks/{task["task_id"]}/logs')
        logs = log_resp.json()
        print('Logs:', logs.get('items', [])[:5])
