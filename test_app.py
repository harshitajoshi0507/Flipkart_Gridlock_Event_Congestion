"""Comprehensive test suite for the Event Congestion Intelligence app."""
import sys
import urllib.request
import json
from urllib.parse import urlencode

sys.stdout.reconfigure(encoding='utf-8')
import os
os.environ['NO_PROXY'] = '127.0.0.1,localhost'
os.environ['no_proxy'] = '127.0.0.1,localhost'

BASE = 'http://127.0.0.1:8501'
passed = 0
failed = 0

def test(name, url, method='GET', data=None):
    global passed, failed
    try:
        if method == 'POST' and data:
            encoded = urlencode(data).encode()
            req = urllib.request.Request(BASE + url, data=encoded, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            r = urllib.request.urlopen(req, timeout=10)
        else:
            r = urllib.request.urlopen(BASE + url, timeout=10)
        body = r.read().decode()
        passed += 1
        return r.status, body
    except Exception as e:
        failed += 1
        print(f'  FAIL {name}: {e}')
        return None, None

print('='*60)
print('EVENT CONGESTION INTELLIGENCE - FULL TEST SUITE')
print('='*60)

# 1. Page Tests
print('\n--- PAGE TESTS ---')
for url, name in [('/', 'Dashboard'), ('/map', 'Map'), ('/predict', 'Predict'), ('/analytics', 'Analytics')]:
    code, body = test(name, url)
    if code:
        print(f'  PASS {name} page [{code}] ({len(body)} bytes)')

# 2. Stats API
print('\n--- STATS API ---')
code, body = test('Stats', '/api/stats')
if code:
    stats = json.loads(body)
    print(f'  PASS Stats API [{code}]')
    print(f'    Total events: {stats["total"]}')
    print(f'    Planned: {stats["planned"]} | Unplanned: {stats["unplanned"]}')
    print(f'    Road Closures: {stats["closures"]} | High Impact: {stats["high_impact"]}')
    print(f'    Avg Impact Score: {stats["avg_impact"]}')

# 3. Analytics APIs
print('\n--- ANALYTICS APIs ---')
for url, name in [
    ('/api/analytics/by-cause', 'By Cause'),
    ('/api/analytics/by-zone', 'By Zone'),
    ('/api/analytics/by-hour', 'By Hour'),
    ('/api/analytics/by-corridor', 'By Corridor'),
    ('/api/analytics/by-day', 'By Day'),
    ('/api/analytics/event-driven', 'Event Driven'),
]:
    code, body = test(name, url)
    if code:
        data = json.loads(body)
        print(f'  PASS {name} [{code}] ({len(data)} records)')

# 4. Dropdowns
print('\n--- DROPDOWNS API ---')
code, body = test('Dropdowns', '/api/dropdowns')
if code:
    dd = json.loads(body)
    print(f'  PASS Dropdowns [{code}]')
    print(f'    Causes: {len(dd["causes"])} | Zones: {len(dd["zones"])} | Corridors: {len(dd["corridors"])} | Junctions: {len(dd["junctions"])}')

# 5. Map Events with filters
print('\n--- MAP EVENTS API (with filters) ---')
for params, name in [
    ('', 'All Events'),
    ('?event_cause=public_event', 'Public Events Only'),
    ('?event_cause=procession', 'Processions Only'),
    ('?event_type=planned', 'Planned Only'),
    ('?event_type=unplanned', 'Unplanned Only'),
    ('?zone=North+Zone+1', 'North Zone 1'),
    ('?event_cause=vip_movement', 'VIP Movement'),
]:
    code, body = test(name, '/api/events/map' + params)
    if code:
        data = json.loads(body)
        print(f'  PASS {name} [{code}] ({len(data)} events)')

# 6. Predict API - multiple scenarios
print('\n--- PREDICT API (multiple scenarios) ---')
scenarios = [
    ('IPL Cricket Match', {'event_cause': 'public_event', 'event_type': 'planned', 'zone': 'Central Zone 1', 'corridor': 'Non-corridor', 'hour_of_day': 20, 'estimated_crowd': 30000, 'requires_road_closure': 'true', 'description': 'IPL Match at Chinnaswamy Stadium'}),
    ('Religious Procession', {'event_cause': 'procession', 'event_type': 'planned', 'zone': 'East Zone 1', 'corridor': 'Old Madras Road', 'hour_of_day': 18, 'estimated_crowd': 2000, 'requires_road_closure': 'true', 'description': 'Brahma Rathotsava procession'}),
    ('VIP Movement', {'event_cause': 'vip_movement', 'event_type': 'planned', 'zone': 'North Zone 1', 'corridor': 'Bellary Road 1', 'hour_of_day': 10, 'estimated_crowd': 100, 'requires_road_closure': 'true', 'description': 'VIP convoy movement'}),
    ('Political Protest', {'event_cause': 'protest', 'event_type': 'unplanned', 'zone': 'Central Zone 2', 'corridor': 'Non-corridor', 'hour_of_day': 14, 'estimated_crowd': 5000, 'requires_road_closure': 'false', 'description': 'Political rally at Town Hall'}),
    ('Road Construction', {'event_cause': 'construction', 'event_type': 'planned', 'zone': 'West Zone 1', 'corridor': 'Mysore Road', 'hour_of_day': 22, 'estimated_crowd': 0, 'requires_road_closure': 'true', 'description': 'Metro construction work'}),
    ('Sudden Congestion', {'event_cause': 'congestion', 'event_type': 'unplanned', 'zone': 'South Zone 2', 'corridor': 'Hosur Road', 'hour_of_day': 9, 'estimated_crowd': 0, 'requires_road_closure': 'false', 'description': 'Heavy traffic near Silk Board'}),
    ('Small Village Festival', {'event_cause': 'public_event', 'event_type': 'planned', 'zone': '', 'corridor': 'Non-corridor', 'hour_of_day': 16, 'estimated_crowd': 200, 'requires_road_closure': 'false', 'description': 'Local village festival'}),
]

for name, params in scenarios:
    code, body = test(name, '/api/predict', method='POST', data=params)
    if code:
        result = json.loads(body)
        i = result['impact']
        r = result['resources']
        print(f'  PASS {name} [{code}]')
        print(f'    Impact: {i["score"]}/10 | Risk: {i["risk_level"]} | Duration: {i["duration_hours"]}h')
        print(f'    Personnel: {r["personnel"]} | Barricades: {len(r["barricades"])} | Diversions: {len(r["diversions"])} | Equipment: {len(r["equipment"])}')
        print(f'    Similar events found: {len(result["similar_events"])}')

# Summary
print('\n' + '='*60)
print(f'RESULTS: {passed} PASSED | {failed} FAILED')
print('='*60)
