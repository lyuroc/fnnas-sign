"""配置管理模块 - 读写持久化配置"""

import json
import os
import logging
import copy
from datetime import datetime


class ConfigManager:
    """配置文件管理器"""

    DEFAULT_CONFIG = {
        'web_port': 7654,
        'sign_start_hour': 8,
        'sign_start_minute': 0,
        'sign_end_hour': 22,
        'sign_end_minute': 0,
        'forum_username': '',
        'forum_password': '',
        'cookie_saltkey': '',
        'cookie_auth': '',
        'enable_wechat': True,
        'enable_qq': True,
        'enable_email': False,
        'webhook_url_wechat': 'http://127.0.0.1:8644/webhooks/fnnas-sign-wechat',
        'webhook_url_qq': 'http://127.0.0.1:8644/webhooks/fnnas-sign-qq',
        'webhook_secret': '',
        'smtp_server': 'smtp.qq.com',
        'smtp_port': 465,
        'smtp_ssl': True,
        'smtp_user': '',
        'smtp_password': '',
        'notify_email': '',
        'last_sign_time': '',
        'today_signed': False,
        'total_sign_days': 0,
        'current_streak': 0,
        'sign_info': {},
        'wechat_chat_id': '',
        'qq_chat_id': '',
        'bgm_enabled': True,
        'bgm_pos_x': 700,
        'bgm_pos_y': 20,
    }

    def __init__(self):
        self.config_path = self._get_config_path()
        self._config = {}
        self.logger = logging.getLogger('config')

    def _get_config_path(self):
        """获取配置文件路径，按优先级查找"""
        for env_var in ['TRIM_PKGVAR', 'TRIM_PKGHOME', 'TRIM_APPDEST']:
            var_dir = os.environ.get(env_var, '')
            if var_dir:
                target = os.path.join(var_dir, 'config.json')
                os.makedirs(var_dir, exist_ok=True)
                return target
        # 兜底：使用当前目录的 data 子目录
        fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
        os.makedirs(fallback, exist_ok=True)
        return os.path.join(fallback, 'config.json')

    def _get_var_dir(self):
        """获取变量目录路径"""
        return os.path.dirname(self.config_path)

    def ensure_defaults(self):
        """确保配置文件存在且包含默认值"""
        if os.path.exists(self.config_path):
            self.load()
        else:
            self._config = copy.deepcopy(self.DEFAULT_CONFIG)
            self.save()
            self.logger.info(f'已创建默认配置: {self.config_path}')

    def load(self):
        """加载配置"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                self._config = {**self.DEFAULT_CONFIG, **loaded}
            else:
                self._config = copy.deepcopy(self.DEFAULT_CONFIG)
        except Exception as e:
            self.logger.error(f'加载配置失败: {e}')
            self._config = copy.deepcopy(self.DEFAULT_CONFIG)
        return copy.deepcopy(self._config)

    def save(self):
        """保存配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            self.logger.debug(f'配置已保存: {self.config_path}')
        except Exception as e:
            self.logger.error(f'保存配置失败: {e}')

    def set(self, key, value):
        """设置单个配置项"""
        self._config[key] = value

    def merge(self, data):
        """合并配置（来自前端 API）"""
        allowed_keys = set(self.DEFAULT_CONFIG.keys())
        for key, value in data.items():
            if key in allowed_keys:
                expected_type = type(self.DEFAULT_CONFIG[key])
                if expected_type == bool and not isinstance(value, bool):
                    value = str(value).lower() in ('true', '1', 'yes')
                elif expected_type == int and not isinstance(value, int):
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        pass
                # smtp_password 为空时不覆盖已保存的值
                if key == 'smtp_password' and not value and self._config.get('smtp_password'):
                    continue
                # webhook_secret 为空时不覆盖已保存的值
                if key == 'webhook_secret' and not value and self._config.get('webhook_secret'):
                    continue
                # 掩码值（含 ****）不覆盖已保存
                if key in ('webhook_secret', 'smtp_password') and isinstance(value, str) and '****' in value:
                    continue
                self._config[key] = value
        self.save()

    def reload(self):
        """重新从磁盘加载配置"""
        return self.load()

    def add_log(self, entry):
        """添加一条打卡日志（每次打卡操作都会记录）"""
        log_path = os.path.join(self._get_var_dir(), 'sign_logs.json')
        try:
            logs = []
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            logs.append(entry)
            # 只保留最近 200 条
            if len(logs) > 200:
                logs = logs[-200:]
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f'写入日志失败: {e}')

    def get_logs(self, limit=20):
        """获取最近的打卡日志"""
        log_path = os.path.join(self._get_var_dir(), 'sign_logs.json')
        try:
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                return logs[-limit:]
        except Exception as e:
            self.logger.error(f'读取日志失败: {e}')
        return []
