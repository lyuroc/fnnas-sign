"""飞牛论坛签到模块 — 零外部依赖版本"""

import sys
import os
import re
import logging

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

from stdlib_http import Session
from soup_mini import from_string as soup


class Signer:
    """论坛签到类"""

    BASE_URL = 'https://club.fnnas.com'
    SIGN_PAGE = f'{BASE_URL}/plugin.php?id=zqlj_sign'

    def __init__(self):
        self.session = Session()
        self.logger = logging.getLogger('signer')

    def login(self, username, password):
        """登录论坛并获取 Cookie"""
        try:
            login_url = f'{self.BASE_URL}/member.php?mod=logging&action=login'
            resp = self.session.get(login_url, timeout=15)
            doc = soup(resp.text)

            formhash = ''
            inp = doc.find('input', {'name': 'formhash'})
            if inp:
                formhash = inp.get('value', '')

            if not formhash:
                m = re.search(r'name="formhash"[^>]+value="([^"]+)"', resp.text)
                if m:
                    formhash = m.group(1)

            if not formhash:
                return {'success': False,
                        'error': '无法获取登录表单，论坛页面可能已更新'}

            data = {
                'formhash': formhash,
                'referer': 'https://club.fnnas.com/forum.php',
                'loginfield': 'username',
                'username': username,
                'password': password,
                'fastloginfield': 'username',
                'cookietime': '2592000',
            }

            LOGIN_POST = (f'{self.BASE_URL}/member.php?mod=logging&action=login'
                          '&loginsubmit=yes&infloat=yes&handlekey=ls&inajax=1')
            login_resp = self.session.post(
                LOGIN_POST, data=data, timeout=15,
                headers={'X-Requested-With': 'XMLHttpRequest'}
            )
            text = login_resp.text

            if 'succeed' in text.lower() or '欢迎' in text:
                saltkey = ''
                auth = ''
                for cookie in self.session.cookiejar:
                    if cookie.name.endswith('_saltkey'):
                        saltkey = cookie.value
                    elif cookie.name.endswith('_auth'):
                        auth = cookie.value
                if saltkey and auth:
                    self.logger.info(f'论坛登录成功: {username}')
                    return {'success': True, 'saltkey': saltkey, 'auth': auth}
                else:
                    return {'success': False,
                            'error': '登录成功但未能获取到Cookie，可能需要手动填写'}

            error_msg = '登录失败'
            for tag in ('div', 'p', 'span'):
                for node in doc.find_all(tag):
                    txt = node.get_text()
                    if '密码' in txt or '错误' in txt:
                        error_msg = txt.strip()[:100]
                        break
                if error_msg != '登录失败':
                    break

            self.logger.warning(f'登录失败: {error_msg}')
            return {'success': False, 'error': error_msg}

        except Exception as e:
            self.logger.error(f'登录异常: {str(e)}')
            return {'success': False, 'error': f'登录异常: {str(e)}'}

    def sign_in(self, saltkey, auth, sign):
        """执行打卡签到"""
        try:
            cookies = {
                'pvRK_2132_saltkey': saltkey,
                'pvRK_2132_auth': auth,
            }

            # 1. 访问签到页面，提取 formhash 和最新 sign
            page_resp = self.session.get(self.SIGN_PAGE, cookies=cookies,
                                         timeout=15)
            doc = soup(page_resp.text)

            formhash = ''
            latest_sign = ''

            for a in doc.find_all('a'):
                href = a.get('href', '')
                if 'sign=' not in href:
                    continue
                qs = href.split('?', 1)[1] if '?' in href else ''
                params = {}
                for p in qs.split('&'):
                    if '=' in p:
                        k, v = p.split('=', 1)
                        params[k] = v
                if 'formhash' in params:
                    formhash = params['formhash']
                if 'sign' in params:
                    latest_sign = params['sign']
                self.logger.info(f'签到按钮链接: {href}')
                self.logger.info(f'提取 sign: {latest_sign}, formhash: {formhash}')
                break

            if not latest_sign:
                latest_sign = sign

            if not formhash:
                inp = doc.find('input', {'name': 'formhash'})
                if inp:
                    formhash = inp.get('value', '')

            self.logger.info(f'使用 formhash: {formhash}')

            # 2. 模拟点击打卡按钮
            post_data = {
                'id': 'zqlj_sign',
                'sign': latest_sign,
                'formhash': formhash,
                'inajax': '1',
            }
            self.logger.info(f'签到POST: {post_data}')

            resp = self.session.post(
                self.BASE_URL + '/plugin.php',
                data=post_data, cookies=cookies, timeout=15,
                headers={'X-Requested-With': 'XMLHttpRequest'}
            )
            text = resp.text
            self.logger.info(f'签到响应: status={resp.status_code}, len={len(text)}')

            # 处理 Discuz! AJAX CDATA
            m = re.search(r'<!\[CDATA\[(.*?)\]\]>', text, re.DOTALL)
            if m:
                text = m.group(1)

            if '恭喜您，打卡成功' in text:
                reward = self._parse_reward(text)
                msg = f'打卡成功 🎉 {reward}' if reward else '打卡成功 🎉'
                self.logger.info(msg)
                return {'success': True, 'message': msg, 'reward': reward}

            elif '您今天已经打过卡了' in text or '请勿重复操作' in text:
                self.logger.info('今日已打卡 ✅')
                return {'success': True, 'message': '今天已经打过卡了 ✅',
                        'reward': ''}

            elif '请先登录' in text:
                return {'success': False,
                        'error': 'Cookie已过期，请重新登录'}

            else:
                self.logger.warning(f'签到响应(前300): {text[:300]}')
                return {'success': False, 'error': '打卡失败，返回内容异常'}

        except Exception as e:
            self.logger.error(f'打卡异常: {str(e)}')
            return {'success': False, 'error': f'打卡异常: {str(e)}'}

    def _parse_reward(self, html_text):
        """从响应中解析奖励信息"""
        doc = soup(html_text)
        for tag in ('li', 'p', 'span', 'div'):
            for node in doc.find_all(tag):
                txt = node.get_text().strip()
                if '奖励' in txt and any(c.isdigit() for c in txt):
                    return txt[:50]
        return ''

    def get_sign_info(self, saltkey, auth):
        """获取签到详情页面信息"""
        cookies = {
            'pvRK_2132_saltkey': saltkey,
            'pvRK_2132_auth': auth,
        }
        try:
            resp = self.session.get(self.SIGN_PAGE, cookies=cookies, timeout=15)
            doc = soup(resp.text)

            info = {}
            patterns = [
                ('recent_checkin', '最近打卡'),
                ('monthly_days', '本月打卡'),
                ('continuous_days', '连续打卡'),
                ('total_days', '累计打卡'),
                ('total_reward', '累计奖励'),
                ('recent_reward', '最近奖励'),
                ('level', '当前打卡等级'),
            ]

            for key, label in patterns:
                for node in doc.find_all('li'):
                    txt = node.get_text().strip()
                    if label in txt:
                        for sep in ('：', ':'):
                            if sep in txt:
                                info[key] = txt.split(sep, 1)[1].strip()
                                break
                        if key in info:
                            break
            return info

        except Exception as e:
            self.logger.error(f'获取签到信息失败: {str(e)}')
            return {}

    def check_today_signed(self, saltkey, auth):
        """检查今天是否已打卡"""
        info = self.get_sign_info(saltkey, auth)
        recent = info.get('recent_checkin', '')
        if recent:
            try:
                sign_date = recent.split(' ')[0] if ' ' in recent else recent
                from datetime import datetime
                return sign_date == datetime.now().strftime('%Y-%m-%d')
            except Exception:
                pass
        return False
