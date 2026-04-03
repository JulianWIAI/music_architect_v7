"""
═══════════════════════════════════════════════════════════════════════════════
COPY THESE METHODS INTO composition_engine.py
═══════════════════════════════════════════════════════════════════════════════

Add these methods to the CompositionEngine class, 
AFTER the _section_energy method and BEFORE the compose method.

Location: Around line 850-900 in composition_engine.py
"""

# ═══════════════════════════════════════════════════════════════════════════════
# METHOD 1: _generate_fused_drums - Add to CompositionEngine class
# ═══════════════════════════════════════════════════════════════════════════════

    def _generate_fused_drums(self, fusion_config, structure, config):
        """Generate drums using fused patterns from multiple genres."""
        KICK = 36
        SNARE = 38
        HIHAT_CLOSED = 42
        HIHAT_OPEN = 46
        CRASH = 49
        
        notes = []
        total_bars = sum(bars for _, bars in structure)
        complexity_float = config.complexity / 10.0
        h_amt = config.humanize_amount
        bpm = config.bpm or 120
        
        # Get fused patterns for each drum instrument
        kick_patterns = self.fusion_engine.get_fused_patterns(
            fusion_config, 'kick', total_bars, complexity_float
        )
        snare_patterns = self.fusion_engine.get_fused_patterns(
            fusion_config, 'snare', total_bars, complexity_float
        )
        hihat_patterns = self.fusion_engine.get_fused_patterns(
            fusion_config, 'hihat', total_bars, complexity_float
        )
        
        bar_idx = 0
        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)
            
            for local_bar in range(section_bars):
                if bar_idx >= len(kick_patterns):
                    break
                
                bar_time = bar_idx * 4
                
                # Get patterns for this bar
                kick_pat = kick_patterns[bar_idx] if bar_idx < len(kick_patterns) else [0]*16
                snare_pat = snare_patterns[bar_idx] if bar_idx < len(snare_patterns) else [0]*16
                hihat_pat = hihat_patterns[bar_idx] if bar_idx < len(hihat_patterns) else [0]*16
                
                # Section-specific modifications
                if section_type == 'intro':
                    fade = (local_bar + 1) / max(1, section_bars)
                    kick_pat = [int(v * fade) for v in kick_pat]
                    snare_pat = [int(v * (fade * 0.5)) for v in snare_pat]
                    
                elif section_type == 'outro':
                    fade = 1.0 - (local_bar / max(1, section_bars))
                    kick_pat = [int(v * fade) for v in kick_pat]
                    snare_pat = [int(v * fade) for v in snare_pat]
                    hihat_pat = [int(v * fade) for v in hihat_pat]
                    
                elif section_type == 'break':
                    kick_pat = [0] * 16
                    snare_pat = [0] * 16
                    hihat_pat = [v if i % 8 == 0 else 0 for i, v in enumerate(hihat_pat)]
                    
                elif section_type == 'build':
                    build_pct = (local_bar + 1) / section_bars
                    if build_pct > 0.7:
                        for i in range(16):
                            if i % 2 == 0 and random.random() < build_pct * 0.5:
                                snare_pat[i] = 1
                
                # Convert patterns to MIDI events
                for step in range(16):
                    step_time = bar_time + (step / 4)
                    h_offset = (random.random() - 0.5) * 0.02 * h_amt
                    
                    # Kick
                    if kick_pat[step] > 0:
                        vel = int(80 + random.randint(-8, 8) * h_amt)
                        vel = int(vel * energy)
                        notes.append((step_time + h_offset, 0.25, KICK, max(40, min(127, vel))))
                    
                    # Snare
                    if snare_pat[step] > 0:
                        vel = int(90 + random.randint(-10, 10) * h_amt)
                        vel = int(vel * energy)
                        notes.append((step_time + h_offset, 0.25, SNARE, max(40, min(127, vel))))
                    
                    # Hi-hat
                    if hihat_pat[step] > 0:
                        vel = int(70 + random.randint(-6, 6) * h_amt)
                        vel = int(vel * energy)
                        hat = HIHAT_OPEN if random.random() < 0.08 else HIHAT_CLOSED
                        dur = 0.4 if hat == HIHAT_OPEN else 0.15
                        notes.append((step_time + h_offset, dur, hat, max(30, min(127, vel))))
                
                # Crash on first bar of chorus/drop
                if local_bar == 0 and section_type in ('chorus', 'drop', 'climax'):
                    notes.append((bar_time, 1.0, CRASH, int(100 * energy)))
                
                bar_idx += 1
        
        return notes


# ═══════════════════════════════════════════════════════════════════════════════
# METHOD 2: _generate_fused_bass - Add to CompositionEngine class
# ═══════════════════════════════════════════════════════════════════════════════

    def _generate_fused_bass(self, fusion_config, chord_progression, structure, config):
        """Generate bass using fused patterns from multiple genres."""
        notes = []
        total_bars = sum(bars for _, bars in structure)
        complexity_float = config.complexity / 10.0
        volume = config.tracks.get('bass', {}).get('volume', 0.8)
        base_vel = int(90 * volume)
        h_amt = config.humanize_amount
        
        # Get fused bass rhythm patterns
        bass_patterns = self.fusion_engine.get_fused_patterns(
            fusion_config, 'bass', total_bars, complexity_float
        )
        
        bar_idx = 0
        chord_idx = 0
        
        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)
            
            for local_bar in range(section_bars):
                if bar_idx >= len(bass_patterns):
                    break
                
                bar_time = bar_idx * 4
                
                # Get current chord
                if chord_idx < len(chord_progression):
                    chord_str = chord_progression[chord_idx]
                else:
                    chord_str = chord_progression[chord_idx % len(chord_progression)] if chord_progression else 'Cmaj7'
                
                root, quality = parse_chord_string(chord_str)
                root_midi = note_name_to_midi(root, 2)  # Bass octave
                fifth = root_midi + 7
                
                # Get bass pattern for this bar
                rhythm = bass_patterns[bar_idx] if bar_idx < len(bass_patterns) else [1] + [0] * 15
                
                # Section energy adjustments
                section_energy = energy
                if section_type == 'intro':
                    fade = (local_bar + 1) / max(1, section_bars)
                    section_energy *= fade
                elif section_type == 'outro':
                    fade = 1.0 - (local_bar / max(1, section_bars))
                    section_energy *= fade
                elif section_type == 'break':
                    section_energy *= 0.3
                elif section_type == 'build':
                    build_pct = (local_bar + 1) / section_bars
                    section_energy *= (0.5 + build_pct * 0.5)
                
                # Convert rhythm pattern to MIDI events
                for step in range(16):
                    if rhythm[step] == 1:
                        step_time = bar_time + (step / 4)
                        
                        # Choose note based on position
                        if step == 0:
                            midi_note = root_midi  # Root on beat 1
                        elif step == 8:
                            midi_note = random.choice([root_midi, fifth])  # Root or fifth on beat 3
                        elif step in [4, 12]:
                            midi_note = random.choice([root_midi, fifth, root_midi + 3])
                        else:
                            midi_note = random.choice([root_midi, fifth])
                        
                        # Keep in bass range
                        while midi_note > 60:
                            midi_note -= 12
                        while midi_note < 28:
                            midi_note += 12
                        
                        # Calculate duration until next hit
                        next_hit = None
                        for future_step in range(step + 1, 16):
                            if rhythm[future_step] == 1:
                                next_hit = future_step
                                break
                        
                        if next_hit:
                            duration = (next_hit - step) / 4 - 0.05
                        else:
                            duration = (16 - step) / 4 - 0.1
                        
                        duration = max(0.1, min(duration, 3.8))
                        
                        # Humanize
                        h_offset = (random.random() - 0.5) * 0.02 * h_amt
                        vel_variation = random.randint(-8, 8) * h_amt
                        
                        velocity = int(base_vel * section_energy + vel_variation)
                        velocity = max(40, min(127, velocity))
                        
                        # Accent beat 1
                        if step == 0:
                            velocity = min(127, velocity + 10)
                        
                        notes.append((
                            step_time + h_offset,
                            duration,
                            midi_note,
                            velocity
                        ))
                
                bar_idx += 1
                chord_idx += 1
        
        return notes


# ═══════════════════════════════════════════════════════════════════════════════
# METHOD 3: _generate_fused_lead - Add to CompositionEngine class
# ═══════════════════════════════════════════════════════════════════════════════

    def _generate_fused_lead(self, fusion_config, chord_progression, structure, config):
        """Generate lead melody using fused patterns from multiple genres."""
        notes = []
        total_bars = sum(bars for _, bars in structure)
        complexity_float = config.complexity / 10.0
        volume = config.tracks.get('lead', {}).get('volume', 0.75)
        base_vel = int(85 * volume)
        h_amt = config.humanize_amount
        
        # Get fused synth/lead patterns
        lead_patterns = self.fusion_engine.get_fused_patterns(
            fusion_config, 'synth', total_bars, complexity_float
        )
        
        # If no synth patterns, try pad patterns
        if not lead_patterns or all(sum(p) == 0 for p in lead_patterns):
            lead_patterns = self.fusion_engine.get_fused_patterns(
                fusion_config, 'pad', total_bars, complexity_float
            )
        
        # Parse key for scale
        key = config.key or 'C major'
        key_parts = key.split()
        key_root = key_parts[0] if key_parts else 'C'
        is_minor = 'minor' in key.lower()
        
        bar_idx = 0
        chord_idx = 0
        prev_note = None
        
        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)
            
            # Lead plays less in intro/outro
            if section_type in ('intro', 'outro') and config.complexity < 7:
                if random.random() < 0.5:
                    bar_idx += section_bars
                    chord_idx += section_bars
                    continue
            
            for local_bar in range(section_bars):
                if bar_idx >= len(lead_patterns):
                    break
                
                bar_time = bar_idx * 4
                
                # Get current chord
                if chord_idx < len(chord_progression):
                    chord_str = chord_progression[chord_idx]
                else:
                    chord_str = chord_progression[chord_idx % len(chord_progression)] if chord_progression else 'Cmaj7'
                
                root, quality = parse_chord_string(chord_str)
                root_midi = note_name_to_midi(root, 5)  # Lead in octave 5
                
                # Get scale notes
                if 'min' in quality.lower() or is_minor:
                    scale_intervals = [0, 2, 3, 5, 7, 8, 10]  # Minor scale
                else:
                    scale_intervals = [0, 2, 4, 5, 7, 9, 11]  # Major scale
                scale = [root_midi + i for i in scale_intervals]
                
                # Get lead pattern for this bar
                rhythm = lead_patterns[bar_idx] if bar_idx < len(lead_patterns) else [0] * 16
                
                # Section energy
                section_energy = energy
                if section_type == 'break':
                    section_energy *= 0.4
                elif section_type in ('chorus', 'drop', 'climax'):
                    section_energy *= 1.1
                
                # Convert to MIDI events
                for step in range(16):
                    if rhythm[step] == 1:
                        step_time = bar_time + (step / 4)
                        
                        # Choose note from scale with melodic motion
                        if prev_note is None:
                            midi_note = root_midi
                        else:
                            # Prefer stepwise motion
                            candidates = [n for n in scale if abs(n - prev_note) <= 4]
                            if not candidates:
                                candidates = scale
                            midi_note = random.choice(candidates)
                        
                        # Keep in playable range
                        while midi_note > 84:
                            midi_note -= 12
                        while midi_note < 60:
                            midi_note += 12
                        
                        # Duration
                        next_hit = None
                        for future_step in range(step + 1, 16):
                            if rhythm[future_step] == 1:
                                next_hit = future_step
                                break
                        
                        if next_hit:
                            duration = (next_hit - step) / 4 - 0.05
                        else:
                            duration = (16 - step) / 4 - 0.1
                        
                        duration = max(0.1, min(duration, 2.0))
                        
                        # Humanize
                        h_offset = (random.random() - 0.5) * 0.025 * h_amt
                        vel_variation = random.randint(-10, 10) * h_amt
                        
                        velocity = int(base_vel * section_energy + vel_variation)
                        velocity = max(40, min(127, velocity))
                        
                        notes.append((
                            step_time + h_offset,
                            duration,
                            midi_note,
                            velocity
                        ))
                        
                        prev_note = midi_note
                
                bar_idx += 1
                chord_idx += 1
        
        return notes


# ═══════════════════════════════════════════════════════════════════════════════
# NOW UPDATE THE compose() METHOD TO USE THESE
# ═══════════════════════════════════════════════════════════════════════════════

"""
In the compose() method, update the track generation sections:

FOR DRUMS - Replace:
    if config.tracks.get('drums', {}).get('enabled', True):
        if self.pattern_generator and self.pattern_generator.global_patterns.get('kick'):
            ...

WITH:
    if config.tracks.get('drums', {}).get('enabled', True):
        fusion_config = getattr(config, 'fusion', None)
        if fusion_config and self.fusion_engine:
            tracks['drums'] = self._generate_fused_drums(fusion_config, structure, config)
        elif self.pattern_generator and self.pattern_generator.global_patterns.get('kick'):
            tracks['drums'] = generate_drums_from_learned_patterns(...)
        else:
            tracks['drums'] = self.generate_drum_track(config, structure, total_bars)
        track_info['drums'] = {'channel': 9, 'program': 0}


FOR BASS - Replace similarly:
    if config.tracks.get('bass', {}).get('enabled', True):
        fusion_config = getattr(config, 'fusion', None)
        if fusion_config and self.fusion_engine:
            tracks['bass'] = self._generate_fused_bass(fusion_config, chord_progression, structure, config)
        elif self.bass_generator and isinstance(self.bass_generator.global_patterns, dict) and self.bass_generator.global_patterns.get('rhythms'):
            tracks['bass'] = generate_bass_from_learned_patterns(...)
        else:
            tracks['bass'] = self.generate_bass_track(config, chord_progression, structure)
        inst = config.tracks['bass'].get('instrument') or GENRE_INSTRUMENTS.get(config.genre, {}).get('bass', 33)
        track_info['bass'] = {'channel': 1, 'program': inst}


FOR LEAD - Replace similarly:
    if config.tracks.get('lead', {}).get('enabled', True):
        fusion_config = getattr(config, 'fusion', None)
        if fusion_config and self.fusion_engine:
            tracks['lead'] = self._generate_fused_lead(fusion_config, chord_progression, structure, config)
        elif self.lead_generator and isinstance(self.lead_generator.global_patterns, dict) and self.lead_generator.global_patterns.get('rhythms'):
            tracks['lead'] = generate_lead_from_learned_patterns(...)
        else:
            tracks['lead'] = self.generate_lead_track(config, chord_progression, structure)
        inst = config.tracks['lead'].get('instrument') or GENRE_INSTRUMENTS.get(config.genre, {}).get('lead', 80)
        track_info['lead'] = {'channel': 3, 'program': inst}
"""
