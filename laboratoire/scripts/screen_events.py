"""Short transient event counter: sustained banner != repeated deaths."""
from collections import deque


class DeathEvents:
    def __init__(self):
        self.events=deque(maxlen=12);self.present=False;self.absent_frames=0

    def update(self,detected,now):
        while self.events and now-self.events[0]>180:self.events.popleft()
        if detected is None:return False
        if not detected:
            self.absent_frames+=1
            if self.absent_frames>=2:self.present=False
            return False
        self.absent_frames=0
        if self.present:return False
        self.present=True
        if self.events and now-self.events[-1]<20:return False
        self.events.append(now)
        return len(self.events)>=3
