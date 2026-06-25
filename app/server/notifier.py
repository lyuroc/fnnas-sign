"""消息推送模块 - Webhook + SMTP 推送打卡结果"""

import smtplib
import hmac
import hashlib
import json
import logging
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime


class Notifier:
    """消息推送器，支持 Webhook（微信/QQ）和 SMTP 邮件"""

    def __init__(self, config_mgr):
        self.config_mgr = config_mgr
        self.logger = logging.getLogger('notifier')

    def _build_markdown(self, sign_message, info):
        """构建 Markdown 格式推送消息"""
        recent_time = info.get('recent_checkin', datetime.now().strftime('%Y-%m-%d %H:%M'))
        lines = [
            f'**飞牛论坛打卡** {sign_message}',
            '---',
            f'📅 打卡时间: {recent_time}',
            f'📊 累计打卡: {info.get("total_days", "?")}',
            f'📈 本月打卡: {info.get("monthly_days", "?")}',
            f'⏱ 连续打卡: {info.get("continuous_days", "?")}',
            f'🏆 打卡等级: {info.get("level", "?")}',
            f'💰 本次奖励: {info.get("recent_reward", "?")}',
            f'💰 累计奖励: {info.get("total_reward", "?")}',
            '---',
            '*由 飞牛NAS · 飞牛论坛打卡 自动执行*',
        ]
        return '\n'.join(lines)

    def _build_error_markdown(self, error_msg):
        """构建 Markdown 格式错误通知"""
        lines = [
            '**飞牛论坛打卡** 打卡失败 ❌',
            '---',
            f'错误信息: {error_msg}',
            '',
            '请检查：',
            '1. Cookie 是否已过期 → 重新登录',
            '2. 论坛是否可访问',
        ]
        return '\n'.join(lines)

    def _md_to_html(self, md_text):
        """Markdown → HTML（供邮件使用）"""
        try:
            import markdown
            return markdown.markdown(md_text, extensions=['nl2br'])
        except Exception:
            return md_text.replace('\n', '<br>\n')

    def notify_all(self, sign_message, info):
        """向所有启用的渠道推送签到结果"""
        cfg = self.config_mgr.load()
        md_message = self._build_markdown(sign_message, info)
        errors = []

        # 推送到微信（通过 Hermes Webhook）
        if cfg.get('enable_wechat', True) and cfg.get('webhook_url_wechat'):
            try:
                self._push_webhook(
                    cfg['webhook_url_wechat'],
                    cfg.get('webhook_secret', ''),
                    md_message
                )
                self.logger.info('✅ 微信推送成功')
            except Exception as e:
                errors.append(f'微信推送失败: {str(e)}')
                self.logger.error(f'❌ 微信推送失败: {str(e)}')

        # 推送到 QQ（通过 Hermes Webhook）
        if cfg.get('enable_qq', True) and cfg.get('webhook_url_qq'):
            try:
                self._push_webhook(
                    cfg['webhook_url_qq'],
                    cfg.get('webhook_secret', ''),
                    md_message
                )
                self.logger.info('✅ QQ推送成功')
            except Exception as e:
                errors.append(f'QQ推送失败: {str(e)}')
                self.logger.error(f'❌ QQ推送失败: {str(e)}')

        # 邮件推送（Markdown → HTML）
        if cfg.get('enable_email', False) and cfg.get('smtp_server') and cfg.get('notify_email'):
            try:
                html = self._md_to_html(md_message)
                self._push_email_html(cfg, sign_message, html)
                self.logger.info(f'✅ 邮件推送成功: {cfg["notify_email"]}')
            except Exception as e:
                errors.append(f'邮件推送失败: {str(e)}')
                self.logger.error(f'❌ 邮件推送失败: {str(e)}')

        return errors

    def notify_error(self, error_msg):
        """打卡失败时推送错误通知"""
        cfg = self.config_mgr.load()
        md_message = self._build_error_markdown(error_msg)

        if cfg.get('enable_wechat', True) and cfg.get('webhook_url_wechat'):
            try:
                self._push_webhook(cfg['webhook_url_wechat'], cfg.get('webhook_secret', ''), md_message)
            except Exception:
                pass

        if cfg.get('enable_qq', True) and cfg.get('webhook_url_qq'):
            try:
                self._push_webhook(cfg['webhook_url_qq'], cfg.get('webhook_secret', ''), md_message)
            except Exception:
                pass

        if cfg.get('enable_email', False) and cfg.get('smtp_server') and cfg.get('notify_email'):
            try:
                html = self._md_to_html(md_message)
                self._push_email_html(cfg, '打卡失败 ❌', html)
            except Exception:
                pass

    def _push_webhook(self, url, secret, message):
        """向 Hermes Webhook 发送推送 (deliver-only)"""
        import requests as req

        payload = json.dumps({'message': message, 'event_type': 'sign_push'}, ensure_ascii=False)

        headers = {'Content-Type': 'application/json'}
        if secret:
            signature = hmac.new(
                secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            headers['X-Webhook-Signature'] = signature
        headers['X-Webhook-Event'] = 'sign_push'

        resp = req.post(url, data=payload.encode('utf-8'), headers=headers, timeout=10)
        resp.raise_for_status()

    def _push_email_html(self, cfg, title, html):
        """通过 SMTP 发送 HTML 邮件"""
        msg = MIMEText(html, 'html', 'utf-8')
        msg['Subject'] = Header(f'【飞牛论坛打卡】{title}', 'utf-8')
        msg['From'] = cfg['smtp_user']
        msg['To'] = cfg['notify_email']

        server = None
        try:
            if cfg.get('smtp_ssl', True):
                server = smtplib.SMTP_SSL(cfg['smtp_server'], cfg['smtp_port'], timeout=15)
            else:
                server = smtplib.SMTP(cfg['smtp_server'], cfg['smtp_port'], timeout=15)
                server.starttls()

            server.login(cfg['smtp_user'], cfg['smtp_password'])
            server.send_message(msg)

        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
