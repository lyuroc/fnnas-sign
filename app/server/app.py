"""飞牛论坛打卡 - HTTP 服务（零外部依赖，仅使用 Python 内置模块）"""

import http.server
import json
import os
import sys
import logging
from urllib.parse import urlparse, parse_qs
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from signer import Signer
from notifier import Notifier
from scheduler_manager import SignScheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('app')

config_mgr = ConfigManager()
config_mgr.ensure_defaults()
signer = Signer()
notifier = Notifier(config_mgr)
cfg = config_mgr.load()
scheduler = SignScheduler(config_mgr, signer, notifier)
scheduler.start()

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'www')
MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.ico': 'image/x-icon',
    '.svg': 'image/svg+xml',
}


def json_response(data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    return (status, {'Content-Type': 'application/json; charset=utf-8'}, body)


def read_post_body(rfile, content_length):
    if content_length <= 0:
        return {}
    body = rfile.read(content_length).decode('utf-8')
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


class RequestHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        logger.debug(f'{self.client_address[0]} - {format % args}')

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'
        if path == '/editor':
            self._serve_editor()
        elif path.startswith('/api/editor-'):
            self._serve_editor_api()
        elif path.startswith('/api/'):
            self._handle_api('GET', path, parsed)
        else:
            self._serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'
        content_length = int(self.headers.get('Content-Length', 0))
        data = read_post_body(self.rfile, content_length)
        if path.startswith('/api/editor-'):
            self._serve_editor_api(data)
        else:
            self._handle_api('POST', path, parsed, data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    # ===== 可视化编辑器 =====
    def _serve_editor(self):
        editor = '''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Flydev - Editor</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui;display:flex;height:100vh;background:#1e1e1e;color:#ccc;overflow:hidden}
#side{width:180px;background:#252526;border-right:1px solid #333;display:flex;flex-direction:column}
#side h2{padding:10px 12px;font-size:11px;color:#888;border-bottom:1px solid #333}
#fl{flex:1;overflow:auto;font-size:12px}
.f{padding:4px 12px;cursor:pointer;color:#aaa}
.f:hover{background:#2a2d2e;color:#eee}
.f.a{background:#094771;color:#fff}
#ac{padding:5px;display:flex;gap:3px;border-top:1px solid #333}
#ac button{flex:1;padding:4px;border:none;border-radius:3px;cursor:pointer;font-size:10px;font-weight:600;background:#0e639c;color:#fff}
#ac .b{background:#2d8a2d}
#main{flex:1;display:flex;flex-direction:column}
#sp{flex:1;display:flex}
#cp{flex:1;display:flex;flex-direction:column;min-width:0}
#tx{flex:1;width:100%;border:none;outline:none;resize:none;padding:10px;font-family:Consolas,monospace;font-size:13px;background:#1e1e1e;color:#d4d4d4;tab-size:2}
#pp{flex:1;display:flex;flex-direction:column;border-left:2px solid #333;min-width:0}
#pb{height:26px;background:#333;display:flex;align-items:center;padding:0 8px;font-size:10px;color:#888;gap:6px}
#pb button{padding:2px 6px;border:none;border-radius:2px;cursor:pointer;font-size:9px;background:#555;color:#ddd}
#ifr{flex:1;border:none;background:#fff;width:100%}
#st{height:20px;background:#007acc;color:#fff;font-size:10px;display:flex;align-items:center;padding:0 8px;justify-content:space-between}
#st .u{color:#ffa;display:none}
</style></head><body>
<div id="side"><h2>Files</h2><div id="fl"></div><div id="ac"><button onclick="sv()">Save</button><button class="b" onclick="bd()">Build</button></div></div>
<div id="main">
<div id="sp">
<div id="cp"><textarea id="tx" spellcheck="false"></textarea></div>
<div id="pp"><div id="pb"><span>Preview</span><button onclick="rf()">Reload</button></div><iframe id="ifr" src="/"></iframe></div>
</div>
<div id="st"><span id="m">Ready</span><span class="u" id="u">*unsaved</span></div>
</div>
<script>
var c,h=0,f=document.getElementById('fl'),tx=document.getElementById('tx');
tx.addEventListener('input',function(){if(!h){h=1;document.getElementById('u').style.display='inline'}});
function m(t,x){var el=document.getElementById('m');el.textContent=t;el.style.color=x?'red':'white';document.getElementById('st').style.background=x?'#c33':'#007acc';}
function ld(){fetch('/api/editor-files').then(function(r){return r.json()}).then(function(d){
f.innerHTML='';d.items.forEach(function(n){var el=document.createElement('div');el.className='f';
el.textContent=n.name;el.onclick=function(){op(n.name)};f.appendChild(el)});
}).catch(function(e){m(e.message,1)})}
function op(n){if(h&&!confirm('Unsaved changes. Switch?'))return;c=n;
fetch('/api/editor-read?file='+encodeURIComponent(n)).then(function(r){return r.json()}).then(function(d){
tx.value=d.content;h=0;document.getElementById('u').style.display='none';m('Editing: '+n);
var as=document.querySelectorAll('.f');as.forEach(function(el){el.classList.remove('a')});
as.forEach(function(el){if(el.textContent===n)el.classList.add('a')});
}).catch(function(e){m(e.message,1)})}
function sv(){if(!c)return;
fetch('/api/editor-save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file:c,content:tx.value})})
.then(function(r){return r.json()}).then(function(d){if(d.ok){h=0;document.getElementById('u').style.display='none';m('Saved!');rf()}else{m('Save failed',1)}})
.catch(function(e){m(e.message,1)})}
function rf(){document.getElementById('ifr').src='/';setTimeout(function(){m('Preview reloaded')},300)}
function bd(){m('Building...');fetch('/api/editor-build').then(function(r){return r.json()}).then(function(d){m(d.ok?'Build OK':'Build FAILED',!d.ok)}).catch(function(e){m(e.message,1)})}
document.addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key==='s'){e.preventDefault();sv()}});
ld();m('Ready - select a file');
</script></body></html>
'''
        body = editor.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_editor_api(self, post_data=None):
        import os
        from urllib.parse import parse_qs
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        www = os.path.join(base, 'www')
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == '/api/editor-files':
            try:
                items = []
                for f in sorted(os.listdir(www)):
                    if f.startswith('.'): continue
                    fp = os.path.join(www, f)
                    if os.path.isdir(fp): continue
                    if not f.endswith(('.html','.css','.js','.cjs','.json')): continue
                    items.append({'name': f})
                self._send_json(200, {'items': items})
            except Exception as e:
                self._send_json(500, {'error': str(e)})
            return

        if parsed.path == '/api/editor-read':
            fn = qs.get('file', [''])[0]
            if not fn:
                self._send_json(400, {'error': 'no file'})
                return
            fp = os.path.normpath(os.path.join(www, fn))
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    self._send_json(200, {'content': f.read()})
            except Exception as e:
                self._send_json(500, {'error': str(e)})
            return

        if parsed.path == '/api/editor-save':
            data = post_data or {}
            fn = data.get('file', '')
            content = data.get('content', '')
            if not fn:
                self._send_json(400, {'error': 'no file'})
                return
            fp = os.path.normpath(os.path.join(www, fn))
            logger.info(f'Editor save: {fn} -> {fp}')
            if not fp.startswith(os.path.normpath(www)):
                self._send_json(403, {'error': 'bad path'})
                return
            try:
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(content)
                self._send_json(200, {'ok': True})
            except Exception as e:
                logger.error(f'Editor save error: {e}')
                self._send_json(500, {'error': str(e)})
            return

        if parsed.path == '/api/editor-build':
            import subprocess
            try:
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                logger.info(f'Editor build in: {project_root}')
                r = subprocess.run(['/tmp/fnpack', 'build', '--directory', '.'],
                                   capture_output=True, text=True, cwd=project_root, timeout=60)
                self._send_json(200, {'ok': r.returncode == 0, 'output': r.stdout + r.stderr})
            except subprocess.TimeoutExpired:
                self._send_json(500, {'error': 'build timeout'})
            except Exception as e:
                logger.error(f'Build error: {e}')
                self._send_json(500, {'error': str(e)})
            return

        self._send_json(404, {'error': 'not found'})

    # ===== 原始 API =====
    def _handle_api(self, method, path, parsed=None, data=None):
        try:
            if method == 'GET' and path == '/api/config':
                self._api_get_config()
            elif method == 'POST' and path == '/api/config':
                self._api_save_config(data)
            elif method == 'GET' and path == '/api/status':
                self._api_status()
            elif method == 'POST' and path == '/api/sign-now':
                self._api_sign_now()
            elif method == 'POST' and path == '/api/reload':
                self._api_reload()
            elif method == 'GET' and path == '/api/logs':
                self._api_logs()
            elif method == 'GET' and path == '/api/latest-info':
                self._api_latest_info()
            elif method == 'POST' and path == '/api/test-email':
                self._api_test_email(data)
            else:
                self._send_json(404, {'code': -1, 'msg': '接口不存在'})
        except Exception as e:
            logger.error(f'API 异常: {str(e)}')
            self._send_json(500, {'code': -1, 'msg': f'服务器错误: {str(e)}'})

    def _api_get_config(self):
        cfg = config_mgr.load()
        safe_cfg = dict(cfg)
        safe_cfg.pop('forum_password', None)
        if safe_cfg.get('smtp_password'):
            pwd = safe_cfg['smtp_password']
            if len(pwd) > 8:
                safe_cfg['smtp_password'] = pwd[:4] + '****' + pwd[-4:]
            else:
                safe_cfg['smtp_password'] = '****'
        secret = safe_cfg.get('webhook_secret', '')
        if not secret:
            safe_cfg['webhook_secret'] = ''
        elif '****' in str(secret):
            safe_cfg['webhook_secret'] = ''
        elif len(secret) > 8:
            safe_cfg['webhook_secret'] = secret[:4] + '****' + secret[-4:]
        else:
            safe_cfg['webhook_secret'] = '****'
        self._send_json(200, {'code': 0, 'data': safe_cfg})

    def _api_save_config(self, data):
        if not data:
            self._send_json(400, {'code': -1, 'msg': '请求体为空'})
            return
        config_mgr.merge(data)
        self._send_json(200, {'code': 0, 'msg': '配置已保存'})

    def _api_status(self):
        cfg = config_mgr.load()
        target_time = scheduler.get_today_target_time() if scheduler.is_running else '--:--'
        self._send_json(200, {
            'code': 0, 'data': {
                'scheduler_running': scheduler.is_running,
                'today_signed': cfg.get('today_signed', False),
                'last_sign_time': cfg.get('last_sign_time', ''),
                'total_sign_days': cfg.get('total_sign_days', 0),
                'current_streak': cfg.get('current_streak', 0),
                'today_target_time': target_time,
                'sign_period': f"{cfg['sign_start_hour']:02d}:{cfg['sign_start_minute']:02d} - "
                              f"{cfg['sign_end_hour']:02d}:{cfg['sign_end_minute']:02d}",
            }
        })

    def _api_sign_now(self):
        cfg = config_mgr.load()
        if not cfg.get('cookie_saltkey') or not cfg.get('cookie_auth'):
            self._send_json(400, {'code': -1, 'msg': '请先配置论坛 Cookie'})
            return
        if not cfg.get('sign_value'):
            self._send_json(400, {'code': -1, 'msg': '请先填写打卡 sign 参数'})
            return
        now = datetime.now()
        result = signer.sign_in(cfg['cookie_saltkey'], cfg['cookie_auth'], cfg['sign_value'])
        if result['success']:
            info = signer.get_sign_info(cfg['cookie_saltkey'], cfg['cookie_auth'])
            config_mgr.set('today_signed', True)
            config_mgr.set('last_sign_time', now.strftime('%Y-%m-%d %H:%M:%S'))
            import re
            total_str = info.get('total_days', '0')
            match = re.search(r'\d+', total_str)
            if match:
                config_mgr.set('total_sign_days', int(match.group()))
            cont_str = info.get('continuous_days', '0')
            match = re.search(r'\d+', cont_str)
            if match:
                config_mgr.set('current_streak', int(match.group()))
            config_mgr.set('sign_info', info)
            config_mgr.save()
            config_mgr.add_log({'time': now.strftime('%Y-%m-%d %H:%M:%S'), 'status': 'success',
                                'message': result['message'], 'info': info})
            notifier.notify_all(result['message'], info)
            self._send_json(200, {'code': 0, 'data': {'message': result['message'], 'info': info}})
        else:
            self._send_json(400, {'code': -1, 'msg': result.get('error', '打卡失败')})

    def _api_reload(self):
        from datetime import datetime
        config_mgr.reload()
        scheduler.reload()
        config_mgr.add_log({'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'status': 'refresh', 'message': '手动刷新打卡时间'})
        self._send_json(200, {'code': 0, 'msg': '调度器已重载'})

    def _api_logs(self):
        from urllib.parse import parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        limit = int(params.get('limit', [30])[0])
        logs = config_mgr.get_logs(limit=limit)
        self._send_json(200, {'code': 0, 'data': logs})

    def _api_latest_info(self):
        cfg = config_mgr.load()
        sk = cfg.get('cookie_saltkey', '')
        ak = cfg.get('cookie_auth', '')
        if sk and ak:
            try:
                data = signer.get_sign_info(sk, ak)
                config_mgr.set('sign_info', data)
                config_mgr.save()
            except Exception as e:
                logger.warning(f'获取打卡信息失败: {e}')
                data = cfg.get('sign_info', {})
        else:
            data = cfg.get('sign_info', {})
        self._send_json(200, {'code': 0, 'data': data})

    def _api_test_email(self, data=None):
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header
        if not data:
            data = {}
        cfg = dict(config_mgr.load())
        cfg.update({k: v for k, v in data.items() if v})
        try:
            msg = MIMEText('这是一封来自飞牛论坛打卡的测试邮件，如果收到说明 SMTP 配置正确 ✅', 'plain', 'utf-8')
            msg['Subject'] = Header('【飞牛论坛打卡】SMTP 测试', 'utf-8')
            msg['From'] = cfg.get('smtp_user', '')
            msg['To'] = cfg.get('notify_email', '')
            if cfg.get('smtp_ssl', True):
                server = smtplib.SMTP_SSL(cfg['smtp_server'], cfg['smtp_port'], timeout=15)
            else:
                server = smtplib.SMTP(cfg['smtp_server'], cfg['smtp_port'], timeout=15)
                server.starttls()
            pwd = cfg.get('smtp_password', '')
            if not pwd:
                self._send_json(400, {'code': -1, 'msg': '请先填写邮箱授权码'})
                return
            server.login(cfg['smtp_user'], pwd)
            server.send_message(msg)
            server.quit()
            self._send_json(200, {'code': 0, 'msg': '测试邮件发送成功！请检查收件箱'})
        except smtplib.SMTPAuthenticationError:
            self._send_json(400, {'code': -1, 'msg': '邮箱登录失败，授权码错误'})
        except smtplib.SMTPException as e:
            self._send_json(400, {'code': -1, 'msg': f'邮件发送失败: {str(e)[:60]}'})
        except Exception as e:
            self._send_json(500, {'code': -1, 'msg': f'发送异常: {str(e)[:60]}'})

    def _serve_static(self, path):
        if path == '/':
            path = '/index.html'
        file_path = os.path.join(STATIC_DIR, path.lstrip('/'))
        file_path = os.path.normpath(file_path)
        if not file_path.startswith(os.path.normpath(STATIC_DIR)):
            self._send_json(403, {'code': -1, 'msg': '禁止访问'})
            return
        if not os.path.isfile(file_path):
            fallback = os.path.join(STATIC_DIR, 'index.html')
            if os.path.isfile(fallback):
                file_path = fallback
            else:
                self._send_json(404, {'code': -1, 'msg': '文件不存在'})
                return
        ext = os.path.splitext(file_path)[1].lower()
        content_type = MIME_TYPES.get(ext, 'application/octet-stream')
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content)
        except IOError:
            self._send_json(404, {'code': -1, 'msg': '文件读取失败'})

    def _send_json(self, status, data):
        code, headers, body = json_response(data, status)
        self.send_response(code)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)


# ===== 启动入口 =====
if __name__ == '__main__':
    port = config_mgr.load().get('web_port', 7654)
    var_dir = os.environ.get('TRIM_PKGVAR', '') or os.environ.get('TRIM_PKGHOME', '')
    if var_dir:
        port_file = os.path.join(var_dir, 'port.txt')
        try:
            os.makedirs(var_dir, exist_ok=True)
            with open(port_file, 'w') as f:
                f.write(str(port))
        except Exception:
            pass
    server = http.server.HTTPServer(('0.0.0.0', port), RequestHandler)
    logger.info(f'🚀 飞牛论坛打卡服务启动，端口: {port}')
    logger.info(f'🌐 访问 http://127.0.0.1:{port} 打开管理界面')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('服务停止')
        server.server_close()
        scheduler.stop()
