import ctypes
import dearpygui.dearpygui as dpg
import uart_comm
import lorentzian_fit
import synthetic

def main():
    dpg.create_context()
    dpg.create_viewport(title="Ramsey", width=1000, height=720)

    # ── Font ──────────────────────────────────────────────────────────────────
    with dpg.font_registry():
        default_font = dpg.add_font("C:/Windows/Fonts/segoeui.ttf", 16)

    # ── Global theme ──────────────────────────────────────────────────────────
    with dpg.theme(tag="global_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,    10, 10)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,      6,  4)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,        8,  6)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,     4)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,      4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,    4)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,          (45, 45, 48))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,   (60, 60, 65))

    # ── Button themes ─────────────────────────────────────────────────────────
    with dpg.theme(tag="btn_red"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (160, 35,  35))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (200, 55,  55))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (120, 20,  20))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)

    with dpg.theme(tag="btn_green"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (35,  140, 35))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (55,  175, 55))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (20,  110, 20))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)

    with dpg.theme(tag="fit_series_theme"):
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Line, (255, 160, 30),
                                category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, 2.5,
                                category=dpg.mvThemeCat_Plots)

    with dpg.theme(tag="contrast_series_theme"):
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_color(dpg.mvPlotCol_Line, (100, 180, 255),
                                category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, 1.2,
                                category=dpg.mvThemeCat_Plots)

    with dpg.theme(tag="btn_accent"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (0,   100, 180))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (0,   130, 210))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (0,    80, 150))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)

    # ── State shared between callbacks ────────────────────────────────────────
    # Populated in on_config, read in on_packet to label the x-axis correctly.
    last_freqs_mhz   = []   # original (non-interleaved) sweep frequencies
    last_lock_in_en  = [False]  # wrapped in list so nonlocal assignment isn't needed

    sweep_history  = []   # list of contrast arrays, newest last
    MAX_SWEEPS     = 60

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def set_status(msg):
        dpg.set_value("status_text", msg if len(msg) < 90 else msg[:87] + "...")

    def refresh_ports():
        ports = uart_comm.list_ports()
        dpg.configure_item("port_combo", items=ports)
        if ports:
            dpg.set_value("port_combo", ports[0])

    def on_connect():
        if uart_comm.is_connected():
            uart_comm.disconnect()
            set_status("Disconnected")
            dpg.configure_item("connect_btn", label="Connect")
            dpg.bind_item_theme("connect_btn", "btn_red")
        else:
            port = dpg.get_value("port_combo")
            try:
                uart_comm.connect(port)
                set_status(f"Connected on {port}")
                dpg.configure_item("connect_btn", label="Disconnect")
                dpg.bind_item_theme("connect_btn", "btn_green")
            except Exception as e:
                set_status(f"Error: {e}")

    def on_init():
        try:
            uart_comm.send_packet(uart_comm.MSG_INIT)
            set_status("Sent INIT")
        except ConnectionError as e:
            set_status(f"Error: {e}")

    def on_config():
        nonlocal last_freqs_mhz

        # Timing parameters (all in clock cycles; 1 cycle = 10 ns at 100 MHz)
        n_shots      = dpg.get_value("n_shots")
        init_dur     = dpg.get_value("init_dur")
        mw_dur       = dpg.get_value("mw_dur")
        dead_time    = dpg.get_value("dead_time")
        readout_dur  = dpg.get_value("readout_dur")
        ref_dur      = dpg.get_value("ref_dur")

        # Lock-in parameters
        lock_in_en  = 1 if dpg.get_value("lock_in_en") else 0
        delta_f_mhz = dpg.get_value("delta_f")
        delta_f_khz = int(round(delta_f_mhz * 1000))

        # Frequency sweep
        freq_start = dpg.get_value("freq_start")  # MHz
        freq_stop  = dpg.get_value("freq_stop")   # MHz
        freq_step  = dpg.get_value("freq_step")   # MHz

        # Build frequency list
        freqs_mhz = []
        f = freq_start
        while f <= freq_stop + 1e-9:
            freqs_mhz.append(round(f, 6))
            f += freq_step
        n_points = len(freqs_mhz)

        last_freqs_mhz.clear()
        last_freqs_mhz.extend(freqs_mhz)
        last_lock_in_en[0] = bool(lock_in_en)

        # Update x-axis to match new sweep range
        dpg.set_axis_limits("x_axis", freq_start, freq_stop)

        # ── Build freq table (interleaved if lock-in) ──────────────────────────
        if lock_in_en and delta_f_khz > 0:
            table_freqs_mhz = []
            for f_mhz in freqs_mhz:
                table_freqs_mhz.append(f_mhz + delta_f_mhz)
                table_freqs_mhz.append(f_mhz - delta_f_mhz)
        else:
            table_freqs_mhz = freqs_mhz
        n_points_table = len(table_freqs_mhz)

        # ── Build CONFIG payload ───────────────────────────────────────────────
        # Header (31 bytes):
        #   [0-1]   n_points_table uint16 big-endian  (2× n_points if lock-in)
        #   [2-5]   n_shots        uint32
        #   [6-9]   init_dur       uint32
        #   [10-13] mw_dur         uint32
        #   [14-17] readout_dur    uint32
        #   [18-21] ref_dur        uint32
        #   [22-25] dead_time      uint32
        #   [26]    lock_in_en     uint8
        #   [27-30] delta_f_khz   uint32
        # Followed by n_points_table × uint32 frequency values in kHz
        payload = []
        payload += list(n_points_table.to_bytes(2, 'big'))
        for val in [n_shots, init_dur, mw_dur, readout_dur, ref_dur, dead_time]:
            payload += list(int(val).to_bytes(4, 'big'))
        payload += [lock_in_en & 0x01]
        payload += list(delta_f_khz.to_bytes(4, 'big'))
        for f_mhz in table_freqs_mhz:
            f_khz = int(round(f_mhz * 1000))
            payload += list(f_khz.to_bytes(4, 'big'))

        mode_str = f"lock-in df={delta_f_mhz:.2f} MHz" if lock_in_en else "standard"
        try:
            uart_comm.send_packet(uart_comm.MSG_CONFIG, payload)
            set_status(f"Sent CONFIG - {n_points} pts {mode_str}, {freq_start:.1f}-{freq_stop:.1f} MHz")
        except ConnectionError as e:
            set_status(f"Error: {e}")

    def on_start():
        try:
            uart_comm.send_packet(uart_comm.MSG_START)
            set_status("Sent START - waiting for data...")
        except ConnectionError as e:
            set_status(f"Error: {e}")

    def on_demo():
        sweep_history.clear()
        freq_start = dpg.get_value("freq_start")
        freq_stop  = dpg.get_value("freq_stop")
        freq_step  = dpg.get_value("freq_step")
        f0_demo = (freq_start + freq_stop) / 2
        freqs, payload = synthetic.default_sweep(
            start=freq_start, stop=freq_stop, step=freq_step,
            f0_mhz=f0_demo, contrast=0.05, gamma_mhz=(freq_stop - freq_start) / 20,
            ref_counts=500000, seed=None,
        )
        last_freqs_mhz.clear()
        last_freqs_mhz.extend(freqs)
        dpg.set_axis_limits("x_axis", freq_start, freq_stop)
        on_packet(uart_comm.MSG_DATA, list(payload))

    def update_heatmap(freqs, contrast):
        sweep_history.append(list(contrast))
        if len(sweep_history) > MAX_SWEEPS:
            sweep_history.pop(0)
        n_sweeps = len(sweep_history)
        n_freqs  = len(freqs)
        flat     = [float(v) for row in sweep_history for v in row]
        vmin     = min(flat)
        vmax     = max(flat)
        if vmin == vmax:
            vmax = vmin + 1e-6
        if dpg.does_item_exist("history_heatmap"):
            dpg.delete_item("history_heatmap")
        dpg.add_heat_series(flat, rows=n_sweeps, cols=n_freqs,
                            scale_min=vmin, scale_max=vmax,
                            bounds_min=(freqs[0],  0),
                            bounds_max=(freqs[-1], n_sweeps),
                            parent="hm_y_axis",
                            tag="history_heatmap",
                            format="")
        dpg.set_axis_limits("hm_x_axis", freqs[0], freqs[-1])
        dpg.set_axis_limits("hm_y_axis", 0,         n_sweeps)
        step = max(1, n_sweeps // 8)
        dpg.set_axis_ticks("hm_y_axis",
                           tuple((str(i), float(i))
                                 for i in range(0, n_sweeps + 1, step)))

    def on_packet(msg_type, payload):
        if msg_type == uart_comm.MSG_ACK:
            set_status("ACK received")

        elif msg_type == uart_comm.MSG_DATA:
            # Each point is 8 bytes: 4 bytes sig (MSB first) + 4 bytes ref (MSB first)
            n_points_rx = len(payload) // 8
            if n_points_rx == 0:
                set_status("DATA received - empty payload")
                return

            sig_counts = []
            ref_counts = []
            for i in range(n_points_rx):
                base = i * 8
                sig = int.from_bytes(payload[base:base+4],   'big')
                ref = int.from_bytes(payload[base+4:base+8], 'big')
                sig_counts.append(sig)
                ref_counts.append(ref)

            # Contrast = (sig - ref) / ref  (negative dip = ODMR resonance)
            contrast = [
                (s - r) / r if r > 0 else 0.0
                for s, r in zip(sig_counts, ref_counts)
            ]

            if last_lock_in_en[0]:
                # ── Lock-in mode: demodulate interleaved pairs ─────────────────
                # Even indices = f+df, odd indices = f-df
                # error[i] = contrast[2i] - contrast[2i+1]  (derivative lineshape)
                n_pairs = n_points_rx // 2
                error = [
                    contrast[2*i] - contrast[2*i + 1]
                    for i in range(n_pairs)
                ]

                if len(last_freqs_mhz) >= n_pairs:
                    x_vals = last_freqs_mhz[:n_pairs]
                else:
                    x_vals = list(range(n_pairs))

                dpg.set_value("contrast_series", [x_vals, error])

                # Zero-crossing fit for f0
                result = lorentzian_fit.zero_crossing(x_vals, error)
                if result:
                    dpg.set_value("fit_series", [x_vals, result["fitted_y"]])
                    fit_info = f"lock-in | f0 = {result['f0']:.2f} MHz"
                else:
                    dpg.set_value("fit_series", [[], []])
                    fit_info = "lock-in | no zero crossing"

                e_min = min(error)
                e_max = max(error)
                margin = max(abs(e_max - e_min) * 0.1, 0.005)
                dpg.set_axis_limits("y_axis", e_min - margin, e_max + margin)
                set_status(f"{n_pairs} pairs | {fit_info}")
                update_heatmap(x_vals, error)

            else:
                # ── Standard mode: Lorentzian fit ──────────────────────────────
                if len(last_freqs_mhz) >= n_points_rx:
                    x_vals = last_freqs_mhz[:n_points_rx]
                else:
                    x_vals = list(range(n_points_rx))

                dpg.set_value("contrast_series", [x_vals, contrast])

                result = lorentzian_fit.fit(x_vals, contrast)
                if result:
                    dpg.set_value("fit_series", [x_vals, result["fitted_y"]])
                    fit_info = (
                        f"f0 = {result['f0']:.2f} +/- {result['f0_err']:.2f} MHz  "
                        f"FWHM = {result['gamma']:.2f} MHz  "
                        f"A = {result['a']*100:.2f}%"
                    )
                else:
                    dpg.set_value("fit_series", [[], []])
                    fit_info = "fit failed"

                c_min = min(contrast)
                c_max = max(contrast)
                margin = max(abs(c_max - c_min) * 0.1, 0.005)
                dpg.set_axis_limits("y_axis", c_min - margin, c_max + margin)
                avg_sig = sum(sig_counts) // max(len(sig_counts), 1)
                avg_ref = sum(ref_counts) // max(len(ref_counts), 1)
                set_status(f"{n_points_rx} pts | {fit_info} | sig={avg_sig} ref={avg_ref}")
                update_heatmap(x_vals, contrast)

    uart_comm.set_packet_callback(on_packet)

    # ── UI ────────────────────────────────────────────────────────────────────
    with dpg.window(tag="Primary Window"):

        # ── Connection bar ────────────────────────────────────────────────────
        with dpg.group(horizontal=True):
            dpg.add_text("Port:")
            dpg.add_combo(uart_comm.list_ports(), tag="port_combo", width=90)
            dpg.add_button(label="↺", callback=refresh_ports, width=26)
            dpg.add_button(label="Connect", tag="connect_btn",
                           callback=on_connect, width=100)
            dpg.add_text("|")
            dpg.add_text("--", tag="status_text")

        dpg.add_separator()

        # ── Main split ───────────────────────────────────────────────────────
        with dpg.group(horizontal=True):

            # ── Control panel ─────────────────────────────────────────────────
            with dpg.child_window(width=230, height=-1, border=False):

                dpg.add_text("TIMING  (clock cycles)", color=(150, 150, 150))
                dpg.add_separator()
                dpg.add_input_int(label="n_shots",       tag="n_shots",
                                  default_value=1000,    width=120)
                dpg.add_input_int(label="init",          tag="init_dur",
                                  default_value=500,     width=120)
                dpg.add_input_int(label="MW",            tag="mw_dur",
                                  default_value=100,     width=120)
                dpg.add_input_int(label="dead",          tag="dead_time",
                                  default_value=0,       width=120)
                dpg.add_input_int(label="readout",       tag="readout_dur",
                                  default_value=300,     width=120)
                dpg.add_input_int(label="ref",           tag="ref_dur",
                                  default_value=300,     width=120)

                dpg.add_spacer(height=6)
                dpg.add_text("FREQUENCY  (MHz)", color=(150, 150, 150))
                dpg.add_separator()
                dpg.add_input_float(label="start", tag="freq_start",
                                    default_value=1300.0, width=120, format="%.1f")
                dpg.add_input_float(label="stop",  tag="freq_stop",
                                    default_value=1400.0, width=120, format="%.1f")
                dpg.add_input_float(label="step",  tag="freq_step",
                                    default_value=1.0,    width=120, format="%.2f")

                dpg.add_spacer(height=6)
                dpg.add_text("LOCK-IN  (FSK mode)", color=(150, 150, 150))
                dpg.add_separator()
                dpg.add_checkbox(label="enable", tag="lock_in_en",
                                 default_value=False)
                dpg.add_input_float(label="df (MHz)", tag="delta_f",
                                    default_value=0.5, width=120, format="%.2f")

                dpg.add_spacer(height=10)
                dpg.add_separator()
                dpg.add_spacer(height=4)
                dpg.add_button(label="INIT",   callback=on_init,   width=-1)
                dpg.add_spacer(height=2)
                dpg.add_button(label="CONFIG", callback=on_config, width=-1)
                dpg.add_spacer(height=2)
                dpg.add_button(label="START",  callback=on_start,  width=-1,
                               tag="start_btn")
                dpg.add_spacer(height=2)
                dpg.add_button(label="DEMO",   callback=on_demo,   width=-1,
                               tag="demo_btn")

            dpg.add_spacer(width=4)

            # ── Plot panel ────────────────────────────────────────────────────
            with dpg.child_window(width=-1, height=-1, border=False):
                with dpg.plot(label="ODMR Spectrum", height=370, width=-1,
                              tag="odmr_plot"):
                    dpg.add_plot_legend()
                    dpg.add_plot_axis(dpg.mvXAxis,
                                      label="Frequency (MHz)",
                                      tag="x_axis")
                    dpg.add_plot_axis(dpg.mvYAxis,
                                      label="Contrast  (dPL/PL)",
                                      tag="y_axis")
                    dpg.add_line_series([], [], label="Contrast",
                                        parent="y_axis",
                                        tag="contrast_series")
                    dpg.add_line_series([], [], label="Fit",
                                        parent="y_axis",
                                        tag="fit_series")
                    dpg.set_axis_limits("x_axis", 1300, 1400)
                    dpg.set_axis_limits("y_axis", -0.1, 0.1)

                dpg.add_spacer(height=4)

                with dpg.plot(label="Sweep History", height=-1, width=-1,
                              tag="history_plot", no_mouse_pos=True):
                    dpg.add_plot_axis(dpg.mvXAxis,
                                      label="Frequency (MHz)",
                                      tag="hm_x_axis", no_gridlines=True)
                    dpg.add_plot_axis(dpg.mvYAxis,
                                      label="Sweep #",
                                      tag="hm_y_axis", no_gridlines=True)
                    dpg.add_heat_series([0.0], rows=1, cols=1,
                                        scale_min=-0.1, scale_max=0.0,
                                        bounds_min=(1300, 0),
                                        bounds_max=(1400, 1),
                                        parent="hm_y_axis",
                                        tag="history_heatmap",
                                        format="")
                    dpg.set_axis_limits("hm_x_axis", 1300, 1400)
                    dpg.set_axis_limits("hm_y_axis", 0, 1)
                dpg.bind_colormap("history_plot", dpg.mvPlotColormap_Plasma)

    # ── Apply themes and font ─────────────────────────────────────────────────
    dpg.bind_font(default_font)
    dpg.bind_theme("global_theme")
    dpg.bind_item_theme("connect_btn",      "btn_red")
    dpg.bind_item_theme("start_btn",        "btn_accent")
    dpg.bind_item_theme("demo_btn",         "btn_accent")
    dpg.bind_item_theme("contrast_series",  "contrast_series_theme")
    dpg.bind_item_theme("fit_series",       "fit_series_theme")

    def on_resize():
        vh       = dpg.get_viewport_height()
        chrome   = 68  # connection bar + separator + window padding
        available = max(400, vh - chrome)
        dpg.configure_item("odmr_plot",    height=int(available * 0.60))
        dpg.configure_item("history_plot", height=int(available * 0.38))

    dpg.set_viewport_resize_callback(on_resize)

    dpg.setup_dearpygui()
    dpg.show_viewport()

    # Centre the viewport on the screen
    user32 = ctypes.windll.user32
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    vw = dpg.get_viewport_width()
    vh = dpg.get_viewport_height()
    dpg.set_viewport_pos([(sw - vw) // 2, (sh - vh) // 2])

    dpg.set_primary_window("Primary Window", True)
    on_resize()
    dpg.start_dearpygui()
    dpg.destroy_context()

if __name__ == "__main__":
    main()
