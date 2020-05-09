"""
analyses audio and talks osc
"""
import logging

logging.basicConfig(level=logging.DEBUG)
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from auditraq import cli
import asyncio
import sys
import os
import soundcard as sc


class auditraq(toga.App):
    def startup(self):
        """
        Construct and show the Toga application.

        Usually, you would add your application to a main content box.
        We then create a main window (with a name matching the app), and
        show the main window.
        """
        self.audio_inputs = {e.name: e for e in sc.all_microphones()}
        default_mic = sc.default_microphone()

        self.audio_input_label = toga.Label("audio input:", style=Pack(padding=10))
        self.audio_input_selection = toga.Selection(items=self.audio_inputs.keys())
        self.audio_input_selection.value = default_mic.name

        self.ip_label = toga.Label("OSC server ip address:", style=Pack(padding=10))

        self.ip_field = toga.TextInput(
            initial="127.0.0.1", placeholder="ip address", style=Pack(padding=10)
        )

        self.port_label = toga.Label("port:", style=Pack(padding=10))
        self.port_field = toga.TextInput(
            initial="8000", placeholder="port", style=Pack(padding=10)
        )
        self.process = None

        self.btn_start = toga.Button(
            "Start", on_press=self.do_start, style=Pack(flex=1)
        )
        self.btn_stop = toga.Button("Stop", on_press=self.do_stop, style=Pack(flex=1))
        self.btn_stop.enabled = False

        main_box = toga.Box(
            children=[
                self.audio_input_selection,
                self.ip_label,
                self.ip_field,
                self.port_label,
                self.port_field,
                self.btn_start,
                self.btn_stop,
            ]
        )

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = main_box
        self.main_window.show()

    def do_start(self, widget, **kwargs):
        # Disable all the text inputs
        self.ip_field.enabled = False
        self.port_field.enabled = False
        self.btn_start.enabled = False
        self.btn_stop.enabled = True
        self.audio_input_selection.enabled = False

        if self.process is not None:
            self.process.terminate()

        self.add_background_task(self.do_background_task)
        yield 1

    def do_stop(self, widget, **kwargs):
        # Disable all the text inputs
        self.ip_field.enabled = True
        self.port_field.enabled = True
        self.btn_stop.enabled = False
        self.btn_start.enabled = True

        if self.process is not None:
            self.process.terminate()
        yield 1

    async def do_background_task(self, widget, **kwargs):
        "A background task"
        # This task runs in the background, without blocking the main event loop
        path = os.path.abspath(cli.__file__)
        args = (
            sys.executable,
            path,
            self.ip_field.value,
            self.port_field.value,
            str(self.audio_inputs[str(self.audio_input_selection.value)].id),
        )
        logging.info(f"starting task: {args}")
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            env={"OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES"},
        )
        logging.info("task started")

    def on_exit(self):
        """ Quit the application gracefully.
        """
        self.shutdown_event.set()
        self.osc_worker.join()
        self.bpm_worker.join()


def main():
    return auditraq()
