"""
app/core/collection_runner.py

Newman-style collection runner.

Features:
- Resolves {{variable}} placeholders from collection variables
- Executes pre_request_script (sandboxed JS via Python eval substitute)
- Runs the HTTP request
- Executes tests_script with pm.test() / pm.expect()
- Returns structured report per request + summary

Script sandbox provides a `pm` object with:
  pm.variables.get/set
  pm.environment.get/set  (alias)
  pm.request  {method, url, headers, body}
  pm.response {code, status, responseTime, headers, json(), text()}
  pm.test(name, fn)        → records pass/fail
  pm.expect(val)           → Chai-like (basic)
"""
import re
import json
import time
from app.core.http_client import HttpClient


def _resolve(text: str, variables: dict) -> str:
    """Replace {{var}} placeholders with variable values."""
    if not text or not variables:
        return text
    def replacer(m):
        return str(variables.get(m.group(1), m.group(0)))
    return re.sub(r'\{\{(\w+)\}\}', replacer, text)


def _resolve_dict(d, variables: dict):
    if isinstance(d, str):  return _resolve(d, variables)
    if isinstance(d, dict): return {k: _resolve_dict(v, variables) for k, v in d.items()}
    if isinstance(d, list): return [_resolve_dict(i, variables) for i in d]
    return d


def _run_script(script: str, context: dict) -> tuple[list, list]:
    """
    Run a script string in a safe Python context.
    Returns (test_results, console_logs).

    The script can use:
      pm.test("name", lambda: pm.expect(pm.response.code).to_equal(200))
      pm.variables.set("token", pm.response.json()["token"])
      console.log("msg")
    """
    if not script or not script.strip():
        return [], []

    test_results = []
    console_logs = []

    class _Expect:
        def __init__(self, val):
            self._val = val

        def to_equal(self, expected):
            ok = self._val == expected
            return {'pass': ok, 'expected': expected, 'actual': self._val}

        def to_include(self, s):
            ok = str(s) in str(self._val)
            return {'pass': ok, 'expected': f'includes {s!r}', 'actual': self._val}

        def to_be_truthy(self):
            ok = bool(self._val)
            return {'pass': ok, 'expected': 'truthy', 'actual': self._val}

        def to_be_below(self, n):
            ok = self._val < n
            return {'pass': ok, 'expected': f'< {n}', 'actual': self._val}

        def to_be_above(self, n):
            ok = self._val > n
            return {'pass': ok, 'expected': f'> {n}', 'actual': self._val}

        def to_have_status(self, code):
            ok = self._val == code
            return {'pass': ok, 'expected': code, 'actual': self._val}

        # Aliases
        equal = to_equal
        include = to_include
        eql = to_equal

    class _Response:
        def __init__(self, resp: dict):
            self._r = resp
            self.code         = resp.get('status', 0)
            self.status       = resp.get('status_text', '')
            self.responseTime = resp.get('response_ms', 0)
            self.headers      = resp.get('resp_headers', {})

        def json(self):
            try: return json.loads(self._r.get('body', '{}'))
            except: return {}

        def text(self):
            return self._r.get('body', '')

    class _Variables:
        def __init__(self, store: dict):
            self._s = store
        def get(self, k, default=None): return self._s.get(k, default)
        def set(self, k, v): self._s[k] = v
        def has(self, k): return k in self._s
        def unset(self, k): self._s.pop(k, None)

    class _PM:
        def __init__(self, resp_dict: dict, var_store: dict):
            self.response    = _Response(resp_dict)
            self.variables   = _Variables(var_store)
            self.environment = self.variables   # alias
            self.globals     = self.variables   # alias
            self._tests      = test_results

        def test(self, name: str, fn):
            try:
                result = fn()
                if isinstance(result, dict):
                    passed = result.get('pass', bool(result))
                else:
                    passed = bool(result)
                self._tests.append({'name': name, 'passed': passed, 'error': None})
            except Exception as exc:
                self._tests.append({'name': name, 'passed': False, 'error': str(exc)})

        def expect(self, val):
            return _Expect(val)

    class _Console:
        def log(self, *args):   console_logs.append({'level': 'log',   'msg': ' '.join(str(a) for a in args)})
        def warn(self, *args):  console_logs.append({'level': 'warn',  'msg': ' '.join(str(a) for a in args)})
        def error(self, *args): console_logs.append({'level': 'error', 'msg': ' '.join(str(a) for a in args)})

    pm      = _PM(context.get('response', {}), context.get('variables', {}))
    console = _Console()

    try:
        exec(script, {
            'pm': pm,
            'console': console,
            'json': json,
            '__builtins__': {
                'print': console.log,
                'len': len, 'str': str, 'int': int, 'float': float,
                'bool': bool, 'list': list, 'dict': dict,
                'range': range, 'isinstance': isinstance,
                'Exception': Exception,
            }
        })
    except SyntaxError as exc:
        console_logs.append({'level': 'error', 'msg': f'Script syntax error: {exc}'})
    except Exception as exc:
        console_logs.append({'level': 'error', 'msg': f'Script error: {exc}'})

    return test_results, console_logs


def run_collection(collection: dict, requests: list) -> dict:
    """
    Execute all requests in a collection sequentially.
    Returns a full report.
    """
    # Build shared variable store from collection variables
    variables: dict = {}
    for var in (collection.get('variables') or []):
        if var.get('key'):
            variables[var['key']] = var.get('value', '')

    # Resolve collection-level auth
    col_auth_type     = collection.get('auth_type', 'none')
    col_auth_token    = collection.get('auth_token', '')
    col_auth_key_name = collection.get('auth_key_name', 'X-API-Key')

    results         = []
    total_time_ms   = 0
    passed_count    = 0
    failed_count    = 0
    request_passed  = 0
    request_failed  = 0
    skipped_count   = 0

    for req in requests:
        req_name = req.get('name', req.get('url', 'Request'))
        req_url  = _resolve(req.get('url', ''), variables)

        if not req_url:
            results.append({
                'name':       req_name,
                'url':        '',
                'method':     req.get('method', 'GET'),
                'skipped':    True,
                'error':      'No URL — skipped',
                'tests':      [],
                'console':    [],
                'status':     None,
                'response_ms':0,
            })
            skipped_count += 1
            continue

        # Resolve headers + params + body
        headers = _resolve_dict(dict(req.get('headers') or {}), variables)
        params  = _resolve_dict(dict(req.get('params')  or {}), variables)
        body    = _resolve_dict(req.get('body'), variables)

        # Apply auth: inherit from collection or use request-level
        auth_type     = req.get('auth_type', 'inherit')
        auth_token    = req.get('auth_token', '')
        auth_key_name = req.get('auth_key_name', 'X-API-Key')
        if auth_type == 'inherit':
            auth_type     = col_auth_type
            auth_token    = col_auth_token
            auth_key_name = col_auth_key_name

        if   auth_type == 'bearer' and auth_token: headers['Authorization'] = f'Bearer {auth_token}'
        elif auth_type == 'basic'  and auth_token: headers['Authorization'] = f'Basic {auth_token}'
        elif auth_type == 'apikey' and auth_token: headers[auth_key_name]   = auth_token

        # Run collection pre-request script
        col_pre_logs = []
        if collection.get('pre_request_script'):
            _, col_pre_logs = _run_script(collection['pre_request_script'],
                                          {'variables': variables, 'response': {}})

        # Run request pre-request script
        pre_logs = []
        if req.get('pre_request_script'):
            _, pre_logs = _run_script(req['pre_request_script'],
                                      {'variables': variables, 'response': {}})
            # Re-resolve after pre-script (script may have set vars)
            req_url = _resolve(req.get('url', ''), variables)
            headers = _resolve_dict(dict(req.get('headers') or {}), variables)
            params  = _resolve_dict(dict(req.get('params')  or {}), variables)
            body    = _resolve_dict(req.get('body'), variables)

        # Send request
        body_type = req.get('body_type', 'none')
        if body is None: body_type = 'none'

        response = HttpClient.send(
            method=req.get('method', 'GET'),
            url=req_url,
            headers=headers,
            params=params,
            body_type=body_type,
            body=body,
            timeout=30,
        )

        total_time_ms += response.get('response_ms', 0)

        # Run tests script (collection-level + request-level)
        all_tests = []
        test_logs = []

        if collection.get('tests_script'):
            t, l = _run_script(collection['tests_script'],
                               {'variables': variables, 'response': response})
            all_tests.extend(t); test_logs.extend(l)

        if req.get('tests_script'):
            t, l = _run_script(req['tests_script'],
                               {'variables': variables, 'response': response})
            all_tests.extend(t); test_logs.extend(l)

        # Count
        req_pass = all(t['passed'] for t in all_tests) if all_tests else response['ok']
        passed_count  += sum(1 for t in all_tests if     t['passed'])
        failed_count  += sum(1 for t in all_tests if not t['passed'])
        if req_pass: request_passed += 1
        else:        request_failed += 1

        results.append({
            'name':        req_name,
            'url':         req_url,
            'method':      req.get('method', 'GET'),
            'skipped':     False,
            'status':      response.get('status'),
            'status_text': response.get('status_text'),
            'response_ms': response.get('response_ms', 0),
            'size':        response.get('size', 0),
            'body':        response.get('body', ''),
            'resp_headers':response.get('resp_headers', {}),
            'error':       response.get('error'),
            'ok':          response.get('ok', False),
            'tests':       all_tests,
            'console':     col_pre_logs + pre_logs + test_logs,
            'request_passed': req_pass,
        })

    total_requests = len([r for r in results if not r.get('skipped')])
    total_tests    = passed_count + failed_count

    return {
        'summary': {
            'total_requests':  total_requests,
            'request_passed':  request_passed,
            'request_failed':  request_failed,
            'skipped':         skipped_count,
            'total_tests':     total_tests,
            'tests_passed':    passed_count,
            'tests_failed':    failed_count,
            'total_time_ms':   round(total_time_ms, 2),
            'pass_rate':       round(request_passed / total_requests * 100, 1) if total_requests else 0,
        },
        'results': results,
    }
