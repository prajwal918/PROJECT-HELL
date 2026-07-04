import time
import datetime
import os

def set_volume_max():
    os.system('pactl set-sink-mute @DEFAULT_SINK@ 0 2>/dev/null')
    os.system('pactl set-sink-volume @DEFAULT_SINK@ 100% 2>/dev/null')
    os.system('amixer -D pulse sset Master 100% unmute 2>/dev/null')
    os.system('amixer sset Master 100% unmute 2>/dev/null')

def play_alarm(alarm_num):
    set_volume_max()
    print(f"[{datetime.datetime.now()}] ALARM {alarm_num} TRIGGERED!")
    for _ in range(15):
        os.system(f'spd-say -t female1 -r 10 -p 50 "WAKE UP! ALARM {alarm_num}! OVERSEER is running."')
        os.system('aplay /usr/share/sounds/alsa/Noise.wav 2>/dev/null')
        os.system('aplay /usr/share/sounds/alsa/Front_Center.wav 2>/dev/null')
        time.sleep(1.5)

def schedule_alarms():
    alarms = [(7, 0), (7, 5)] # 7:00 AM and 7:05 AM
    print(f"[{datetime.datetime.now()}] Alarm Engine started. Target: {alarms} IST every day.")
    
    while True:
        now = datetime.datetime.now()
        trigger_times = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in alarms]
        
        for idx, t_time in enumerate(trigger_times, 1):
            # If time has passed today, target tomorrow
            if now > t_time and (now - t_time).total_seconds() > 60:
                continue
                
            if now.hour == t_time.hour and now.minute == t_time.minute:
                play_alarm(idx)
                time.sleep(65) # Prevent re-trigger in same minute
        
        time.sleep(30)
            
if __name__ == "__main__":
    schedule_alarms()
