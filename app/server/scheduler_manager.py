"""定时调度模块 - 基于 threading 的每日随机时间打卡调度器"""

import threading
import time
import random
import logging
from datetime import datetime, timedelta


class SignScheduler:
    """打卡调度器 - 每天在用户设定的时间段内随机选一个时间执行"""

    def __init__(self, config_mgr, signer, notifier):
        self.config_mgr = config_mgr
        self.signer = signer
        self.notifier = notifier
        self._thread = None
        self._stop_event = threading.Event()
        self.is_running = False
        self._today_random_minute = None
        self._today_seed = None
        self._refresh_count = 0
        self.logger = logging.getLogger('scheduler')

    def _get_today_seed(self):
        """基于日期和刷新次数生成种子，刷新时改变"""
        return int(datetime.now().strftime('%Y%m%d')) + self._refresh_count

    def _calc_random_minute(self, cfg):
        """计算今日打卡的随机分钟偏移量（从00:00开始算）"""
        seed = self._get_today_seed()
        if self._today_seed != seed:
            self._today_seed = seed
            rng = random.Random(seed)
            start_total = cfg['sign_start_hour'] * 60 + cfg['sign_start_minute']
            end_total = cfg['sign_end_hour'] * 60 + cfg['sign_end_minute']
            if end_total <= start_total:
                end_total += 1440  # 跨天处理

            # 未签到 + 窗口还在开放 → 从当前时间+1分钟到结束时间之间随机
            if not cfg.get('today_signed', False):
                now = datetime.now()
                cur = now.hour * 60 + now.minute
                if cur < end_total:
                    start_total = max(start_total, cur + 1)
                    if end_total <= start_total:
                        start_total = cur  # 兜底，至少留1分钟
                    # 跨天窗口且当前时间在白天（08:00-22:00）→ 只生成今天部分
                    if end_total > 1440 and 480 < cur < 1320:
                        end_total = 1440

            self._today_random_minute = rng.randint(start_total, end_total)
            h, m = divmod(self._today_random_minute % 1440, 60)
            self.logger.debug(f'打卡目标时间: {h:02d}:{m:02d}')
        return self._today_random_minute

    def get_today_target_time(self):
        """获取目标打卡时间字符串 HH:MM"""
        cfg = self.config_mgr.load()
        now = datetime.now()
        current_minute = now.hour * 60 + now.minute
        start_total = cfg['sign_start_hour'] * 60 + cfg['sign_start_minute']
        end_total = cfg['sign_end_hour'] * 60 + cfg['sign_end_minute']
        if end_total <= start_total:
            end_total += 1440

        today_signed = cfg.get('today_signed', False)
        # 已签到 → 重新生成明天的随机时间
        if today_signed:
            tomorrow = now + timedelta(days=1)
            seed = int(tomorrow.strftime('%Y%m%d')) + self._refresh_count
            rng = random.Random(seed)
            minute = rng.randint(start_total, end_total) % 1440
            h, m = divmod(minute, 60)
            self.logger.debug(f'明日打卡目标时间: {h:02d}:{m:02d}')
            return f'{h:02d}:{m:02d}'

        # 窗口已关闭 → 明天的随机时间
        window_closed = current_minute >= end_total
        if window_closed:
            tomorrow = now + timedelta(days=1)
            seed = int(tomorrow.strftime('%Y%m%d')) + self._refresh_count
            rng = random.Random(seed)
            minute = rng.randint(start_total, end_total) % 1440
            h, m = divmod(minute, 60)
            self.logger.debug(f'明日打卡目标时间: {h:02d}:{m:02d}')
            return f'{h:02d}:{m:02d}'

        # 未签到 + 窗口开放 → 今天当前时间到结束之间
        minute = self._calc_random_minute(cfg) % 1440
        # 保存到配置（仅值变化时才写磁盘）
        if cfg.get('today_random_minute') != self._today_random_minute:
            self.config_mgr.set('today_random_minute', self._today_random_minute)
            self.config_mgr.set('today_random_date', now.strftime('%Y-%m-%d'))
            self.config_mgr.set('last_refresh_count', self._refresh_count)
            self.config_mgr.save()
        h, m = divmod(minute, 60)
        return f'{h:02d}:{m:02d}'

    def start(self):
        """启动调度器线程"""
        cfg = self.config_mgr.load()

        # 从配置恢复今天的随机时间（重启后保持之前刷新的时间不变）
        saved_minute = cfg.get('today_random_minute')
        saved_date = cfg.get('today_random_date', '')
        today_str = datetime.now().strftime('%Y-%m-%d')
        if saved_minute is not None and saved_date == today_str and not cfg.get('today_signed', False):
            self._today_random_minute = saved_minute
            # 恢复保存时的 _refresh_count，使种子匹配
            self._refresh_count = cfg.get('last_refresh_count', 0)
            self._today_seed = self._get_today_seed()
            h, m = divmod(saved_minute % 1440, 60)
            self.logger.debug(f'已恢复保存的打卡时间: {h:02d}:{m:02d}')

        # 启动时立即重置过期的签到标记
        if cfg.get('today_signed', False):
            last_sign = cfg.get('last_sign_time', '')
            if last_sign:
                last_date = last_sign[:10]
                today = datetime.now().strftime('%Y-%m-%d')
                if last_date != today:
                    self.config_mgr.set('today_signed', False)
                    self.config_mgr.set('last_sign_time', '')
                    self.config_mgr.save()
                    self.logger.info('启动时重置了昨日签到标记')

        if self._thread and self._thread.is_alive():
            self.logger.warning('调度器已在运行')
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='sign-scheduler')
        self._thread.start()
        self.is_running = True
        self.logger.info('调度器已启动')

    def _run_loop(self):
        """后台循环，每分钟检查一次"""
        while not self._stop_event.is_set():
            try:
                self._check_and_sign()
            except Exception as e:
                self.logger.error(f'检查异常: {str(e)}')
            # 等待 60 秒，但可被 stop 中断
            self._stop_event.wait(60)

    def _check_and_sign(self):
        """检查是否到达今日随机打卡时间"""
        cfg = self.config_mgr.load()

        # 必要条件检查
        if not cfg.get('cookie_saltkey') or not cfg.get('cookie_auth'):
            return

        # 检查今天是否已签到，如果是昨天的标记则重置
        if cfg.get('today_signed', False):
            last_sign = cfg.get('last_sign_time', '')
            if last_sign:
                last_date = last_sign[:10]
                today = datetime.now().strftime('%Y-%m-%d')
                if last_date != today:
                    # 昨天的签到标记，自动重置
                    self.config_mgr.set('today_signed', False)
                    self.config_mgr.set('last_sign_time', '')
                    self.config_mgr.save()
                    self.logger.info('检测到昨日签到标记，已自动重置')
                    cfg = self.config_mgr.load()  # 重新加载配置
                else:
                    return  # 今天的已签到
            else:
                # 没有签到时间但标记了已签到，可能是脏数据
                self.config_mgr.set('today_signed', False)
                self.config_mgr.save()
                self.logger.info('签到标记异常，已重置')
                cfg = self.config_mgr.load()
        # 已签到且在当天 → 跳过（已在上面return）

        now = datetime.now()
        target_minute = self._calc_random_minute(cfg)
        current_minute = now.hour * 60 + now.minute

        # 目标时间到达或在过去10分钟内，自动签到（解决循环定时偏差）
        # % 1440 处理跨天情况
        target_today = target_minute % 1440
        diff = current_minute - target_today
        self.logger.debug(f'自动签到检查: 当前={current_minute}, 目标={target_today}, 差={diff}')
        if 0 <= diff <= 10:
            self.logger.info('到达随机打卡时间，开始执行签到')
            self._execute_sign(cfg, now)

    def _execute_sign(self, cfg, now):
        """执行签到流程"""
        try:
            result = self.signer.sign_in(
                cfg['cookie_saltkey'],
                cfg['cookie_auth'],
                cfg['sign_value']
            )

            sign_time = now.strftime('%Y-%m-%d %H:%M:%S')

            if result['success']:
                info = self.signer.get_sign_info(
                    cfg['cookie_saltkey'],
                    cfg['cookie_auth']
                )

                config_mgr = self.config_mgr
                config_mgr.set('today_signed', True)
                config_mgr.set('last_sign_time', sign_time)
                config_mgr.set('sign_info', info)  # 缓存打卡信息

                # 解析总打卡天数
                total_days_str = info.get('total_days', '0')
                import re
                match = re.search(r'\d+', total_days_str)
                if match:
                    config_mgr.set('total_sign_days', int(match.group()))

                continuous_str = info.get('continuous_days', '0')
                match = re.search(r'\d+', continuous_str)
                if match:
                    config_mgr.set('current_streak', int(match.group()))

                config_mgr.save()

                config_mgr.add_log({
                    'time': sign_time,
                    'status': 'success',
                    'message': result['message'],
                    'info': info,
                })

                self.notifier.notify_all(result['message'], info)
                self.logger.info(f'✅ 打卡成功: {result["message"]}')

            else:
                error = result.get('error', '未知错误')
                self.logger.error(f'❌ 打卡失败: {error}')
                self.config_mgr.add_log({
                    'time': sign_time,
                    'status': 'failed',
                    'message': error,
                })
                self.notifier.notify_error(error)

        except Exception as e:
            self.logger.error(f'签到执行异常: {str(e)}')

    def reload(self):
        """重载调度器（清除缓存，下次获取时重新生成随机时间）"""
        self._today_random_minute = None
        self._today_seed = None
        self._refresh_count += 1
        # 保留今日签到状态，仅重新生成随机时间
        # self.config_mgr.set('today_signed', False)  # 不再重置已签到状态
        self.config_mgr.set('last_refresh_count', self._refresh_count)
        self.config_mgr.save()
        self.logger.info(f'调度器已重载 (refresh #{self._refresh_count})')

    def stop(self):
        """停止调度器"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.is_running = False
        self.logger.info('调度器已停止')
