import json
import os
from datetime import datetime, time, timedelta
from typing import Dict, List, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot


class ScheduleManager:
    """
    Керує:
    - графіком ON/OFF (з попередженнями за 5 хв)
    - інформаційними повідомленнями (text/photo)
    - паузами (глобально і по каналах)
    - історією (не більше 100 записів)
    """

    def __init__(
        self,
        bot: Bot,
        channels: Dict[int, List[Dict[str, time]]],
        schedule_file: str = "schedule.json",
        info_file: str = "info_schedule.json",
        history_file: str = "message_history.json",
        timezone: str = "Europe/Kyiv",
    ):
        self.bot = bot
        self.channels = channels  # {channel_id: [{"on": time, "off": time}, ...]}
        self.schedule_file = schedule_file
        self.info_file = info_file
        self.history_file = history_file
        self.tz = timezone
        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self.paused: bool = False
        self.paused_channels: Dict[int, bool] = {}
        self.max_history = 100
        self.history = self._load_history()
        self.info_schedule: List[Dict[str, Any]] = self._load_info_schedule()
        self.last_reload: str = "-"

    # ---------- Загальне керування ----------
    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
        self._schedule_all()
        print("🕒 Планувальник запущено")

    def clear_jobs(self):
        self.scheduler.remove_all_jobs()

    def _schedule_all(self):
        self.clear_jobs()
        self._schedule_on_off_jobs()
        self._schedule_info_jobs()

    def pause_notifications(self):
        self.paused = True
        print("⏸ Глобальні сповіщення призупинено")

    def resume_notifications(self):
        self.paused = False
        print("▶️ Глобальні сповіщення відновлено")

    # ---------- Історія ----------
    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def add_to_history(self, channel_id: int, msg_type: str, text: str):
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "channel": channel_id,
            "type": msg_type,
            "text": (text or "")[:300],
        }
        self.history.append(entry)
        self._save_history()

    # ---------- Пауза каналів ----------
    def pause_channel(self, channel_id: int):
        self.paused_channels[channel_id] = True
        print(f"⏸ Канал {channel_id} призупинено")

    def resume_channel(self, channel_id: int):
        if channel_id in self.paused_channels:
            del self.paused_channels[channel_id]
        print(f"▶️ Канал {channel_id} відновлено")

    def is_channel_paused(self, channel_id: int) -> bool:
        return self.paused_channels.get(channel_id, False)

    # ---------- Завантаження/збереження графіка ON/OFF ----------
    def load_schedule(self):
        if not os.path.exists(self.schedule_file):
            self._save_schedule_file()
            return

        with open(self.schedule_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        parsed = {}
        for ch_str, intervals in data.items():
            ch_id = int(ch_str)
            parsed[ch_id] = []
            for it in intervals:
                on_t = datetime.strptime(it["on"], "%H:%M").time()
                off_t = datetime.strptime(it["off"], "%H:%M").time()
                parsed[ch_id].append({"on": on_t, "off": off_t})
        self.channels = parsed
        print("✅ schedule.json завантажено")

    def _save_schedule_file(self):
        serializable = {}
        for ch, intervals in self.channels.items():
            serializable[str(ch)] = [
                {"on": t["on"].strftime("%H:%M"), "off": t["off"].strftime("%H:%M")}
                for t in intervals
            ]
        with open(self.schedule_file, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)

    def update_schedule(self, channels: Dict[int, List[Dict[str, time]]]):
        self.channels = channels
        self._save_schedule_file()
        self._schedule_all()
        print("🔁 Переплановано ON/OFF")

    # ---------- Планування ON/OFF ----------
    def _schedule_on_off_jobs(self):
        for ch_id, intervals in self.channels.items():
            for idx, t in enumerate(intervals):
                # попередження за 5 хв до OFF
                warn_dt = (datetime.combine(datetime.now().date(), t["off"]) - timedelta(minutes=5)).time()
                self.scheduler.add_job(
                    self._send_warning_message,
                    "cron",
                    hour=warn_dt.hour,
                    minute=warn_dt.minute,
                    args=[ch_id, idx],
                    id=f"warn_{ch_id}_{idx}",
                    replace_existing=True,
                )
                # OFF
                self.scheduler.add_job(
                    self._send_off_message,
                    "cron",
                    hour=t["off"].hour,
                    minute=t["off"].minute,
                    args=[ch_id, idx],
                    id=f"off_{ch_id}_{idx}",
                    replace_existing=True,
                )
                # ON
                self.scheduler.add_job(
                    self._send_on_message,
                    "cron",
                    hour=t["on"].hour,
                    minute=t["on"].minute,
                    args=[ch_id, idx],
                    id=f"on_{ch_id}_{idx}",
                    replace_existing=True,
                )

    async def _send_warning_message(self, channel_id: int, index: int):
        if self.paused or self.is_channel_paused(channel_id):
            return
        text = f"⚠️ Через 5 хвилин заплановане відключення (інтервал {index + 1})."
        await self.bot.send_message(channel_id, text)
        self.add_to_history(channel_id, "warning", text)

    async def _send_off_message(self, channel_id: int, index: int):
        if self.paused or self.is_channel_paused(channel_id):
            return
        text = f"⚡ Відключення електроенергії (інтервал {index + 1})."
        await self.bot.send_message(channel_id, text)
        self.add_to_history(channel_id, "off", text)

    async def _send_on_message(self, channel_id: int, index: int):
        if self.paused or self.is_channel_paused(channel_id):
            return
        text = f"💡 Електропостачання відновлено (інтервал {index + 1})."
        await self.bot.send_message(channel_id, text)
        self.add_to_history(channel_id, "on", text)

    # ---------- Інформаційні повідомлення ----------
    def _load_info_schedule(self):
        if os.path.exists(self.info_file):
            try:
                with open(self.info_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"❌ Помилка читання {self.info_file}: {e}")
        return []

    def save_info_schedule(self):
        with open(self.info_file, "w", encoding="utf-8") as f:
            json.dump(self.info_schedule, f, ensure_ascii=False, indent=2)

    def _schedule_info_jobs(self):
        for i, msg in enumerate(self.info_schedule):
            t = datetime.strptime(msg["time"], "%H:%M").time()
            self.scheduler.add_job(
                self._send_info_message,
                "cron",
                hour=t.hour,
                minute=t.minute,
                args=[msg],
                id=f"info_{i}_{t.hour}{t.minute}",
                replace_existing=False,
            )

    async def _send_info_message(self, msg: Dict[str, Any]):
        if self.paused:
            return
        # розсилка у всі канали
        for ch_id in self.channels.keys():
            if self.is_channel_paused(ch_id):
                continue
            try:
                if msg["type"] == "text":
                    await self.bot.send_message(ch_id, msg["text"])
                    self.add_to_history(ch_id, "info_text", msg["text"])
                elif msg["type"] == "photo":
                    await self.bot.send_photo(ch_id, photo=msg["photo"], caption=msg.get("caption", ""))
                    self.add_to_history(ch_id, "info_photo", msg.get("caption", ""))
            except Exception as e:
                print(f"⚠️ Помилка info для {ch_id}: {e}")

    def add_info_message(self, time_str: str, msg_type: str, text: str = None, photo: str = None, caption: str = None):
        item = {"time": time_str, "type": msg_type}
        if msg_type == "text":
            item["text"] = text or ""
        else:
            item["photo"] = photo
            item["caption"] = caption or ""
        self.info_schedule.append(item)
        self.save_info_schedule()
        # додати job для тільки-що доданого повідомлення
        t = datetime.strptime(time_str, "%H:%M").time()
        self.scheduler.add_job(
            self._send_info_message, "cron", hour=t.hour, minute=t.minute, args=[item]
        )
        print(f"✅ Додано інфо на {time_str}")

    # ---------- Допоміжне ----------
    def touch_reload_timestamp(self):
        self.last_reload = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
