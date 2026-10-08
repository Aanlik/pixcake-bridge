import os
import urllib.request
for port in ([int(os.environ.get('PORT', '3000')), 8080] if os.environ.get('BRIDGE_ENABLED') == 'true' else [int(os.environ.get('PORT', '3000'))]):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as response:
        if response.status != 200:
            raise SystemExit(1)
