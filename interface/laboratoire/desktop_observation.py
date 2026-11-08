"""Resource observation worker; dependencies are supplied by the desktop entry point."""

def observe(self, pc_tools, time):
    monitor = pc_tools.Monitor()
    next_gpu = 0
    gpu_text = 'GPU : mesure en preparation'
    while not self.finished.is_set():
        try:
            data = monitor.sample()
            children=list(self.session.children.items()) if self.session else []
            alive=sum(p.poll() is None for _,p in children)
            guard=getattr(self.session,'frame_guard',None)
            report=guard.report if guard else {}
            samples=report.get('samples',[])
            sample=samples[-1] if samples else {}
            from datetime import datetime
            fps_at=datetime.fromisoformat(sample['utc']).timestamp() if sample.get('utc') else None
            self.observation.sample(ram_free_gib=data['ram_free_gib'],cpu_percent=data['cpu_percent'],
                cpu_ram_at=time.time(),
                game_present=bool(data['games']),process_count=len(data['programs']),
                fps_protection=bool(self.session and self.session.fps_protection),
                ram_protection=bool(self.session and self.session.ram_protection),
                alive_children=alive,dead_children=len(children)-alive,
                guard_stopped=bool(getattr(self.session,'reason',None) or report.get('stop_reason')),
                guard_reason=report.get('stop_reason'),
                fps_available=bool(sample),fps_at=fps_at,
                fps=sample.get('frames',{}).get('average_fps'),
                displayed_fps=sample.get('display_frames',{}).get('average_fps'),
                game_foreground=(sample.get('game_focus') or {}).get('foreground'),
                child_states={name:('running' if p.poll() is None else 'stopped') for name,p in children})
            if time.monotonic() >= next_gpu:
                try:
                    row = next(r for r in pc_tools.gpu_memory() if r['alice_gpu'])
                    self.observation.sample(gpu_used_gib=row['dedicated_used_gib'],gpu_capacity_gib=row['capacity_gib'],gpu_at=time.time())
                    gpu_text = f"GPU Alice : {row['dedicated_used_gib']}/{row['capacity_gib']} Gio utilises"
                except Exception as error:
                    self.observation.emit('resource.gpu_error',{'error_type':type(error).__name__})
                    gpu_text = 'Mesure de memoire GPU indisponible'
                next_gpu = time.monotonic() + 15
            cpu = '?' if data['cpu_percent'] is None else str(data['cpu_percent'])
            self.events.put(('resources', f"RAM libre : {data['ram_free_gib']} Gio | CPU : {cpu} % | "
                + gpu_text))
        except Exception as error:
            self.observation.emit('resource.error',{'error_type':type(error).__name__})
            self.events.put(('resources', 'Mesure des ressources indisponible.'))
        self.finished.wait(2)
