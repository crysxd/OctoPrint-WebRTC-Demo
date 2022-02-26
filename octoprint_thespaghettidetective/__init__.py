# coding=utf-8
from __future__ import absolute_import
import logging
import threading
import sarge
import json
import re
import os
import sys
import time
import requests

try:
    import queue
except ImportError:
    import Queue as queue

from .ws import WebSocketClient, WebSocketConnectionException
from .commander import Commander
from .utils import (
    ExpoBackoff, SentryWrapper, pi_version,
    get_tags, not_using_pi_camera, OctoPrintSettingsUpdater, server_request)
from .lib.error_stats import error_stats
from .print_event import PrintEventTracker
from .janus import JanusConn
from .webcam_stream import WebcamStreamer
from .remote_status import RemoteStatus
from .webcam_capture import JpegPoster
from .file_download import FileDownloader
from .tunnel import LocalTunnel
from . import plugin_apis
from .client_conn import ClientConn
import zlib
from .printer_discovery import PrinterDiscovery

import octoprint.plugin

__python_version__ = 3 if sys.version_info >= (3, 0) else 2

_logger = logging.getLogger('octoprint.plugins.thespaghettidetective')

POST_STATUS_INTERVAL_SECONDS = 50.0

DEFAULT_LINKED_PRINTER = {'is_pro': False}

_print_event_tracker = PrintEventTracker()


class TheSpaghettiDetectivePlugin(
        octoprint.plugin.StartupPlugin,
        octoprint.plugin.ShutdownPlugin,
        ):

    def __init__(self):
        self.ss = None
        self.status_posted_to_server_ts = 0
        self.message_queue_to_server = queue.Queue(maxsize=1000)
        self.status_update_booster = 0    # update status at higher frequency when self.status_update_booster > 0
        self.status_update_lock = threading.RLock()
        self.remote_status = RemoteStatus()
        self.commander = Commander()
        self.octoprint_settings_updater = OctoPrintSettingsUpdater(self)
        self.jpeg_poster = JpegPoster(self)
        self.file_downloader = FileDownloader(self, _print_event_tracker)
        self.webcam_streamer = None
        self.linked_printer = DEFAULT_LINKED_PRINTER
        self.local_tunnel = None
        self.janus = JanusConn(self)
        self.client_conn = ClientConn(self)
        self.discovery = None
        self.sentry = SentryWrapper(self)

    # ~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
        # for details.
        return dict(
            TheSpaghettiDetective=dict(
                displayName="Access Anywhere - The Spaghetti Detective",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="TheSpaghettiDetective",
                repo="OctoPrint-TheSpaghettiDetective",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/TheSpaghettiDetective/OctoPrint-TheSpaghettiDetective/archive/{target_version}.zip"
            )
        )
 
    # ~~Shutdown Plugin

    def on_shutdown(self):
        if self.ss is not None:
            self.ss.close()
        if self.janus:
            self.janus.shutdown()
        if self.webcam_streamer:
            self.webcam_streamer.restore()

        not_using_pi_camera()

    # ~~Startup Plugin

    def on_startup(self, host, port):
        self.octoprint_port = port if port else self._settings.getInt(["server", "port"])

    def on_after_startup(self):
        not_using_pi_camera()

        # main_thread = threading.Thread(target=self.main_loop)
        main_thread = threading.Thread(target=self.simplified_startup)
        main_thread.daemon = True
        main_thread.start()

    # Private methods

    def auth_headers(self, auth_token=None):
        return {"Authorization": "Token " + self.auth_token(auth_token)}

    def simplified_startup(self):
        _logger.info('Simplified startup')
        # Janus may take a while to start, or fail to start. Put it in thread to make sure it does not block
        janus_thread = threading.Thread(target=self.janus.start)
        janus_thread.daemon = True
        janus_thread.start()

        _logger.info('Starting webcam streamer')
        self.webcam_streamer = WebcamStreamer(self, self.sentry)
        stream_thread = threading.Thread(target=self.webcam_streamer.video_pipeline)
        stream_thread.daemon = True
        stream_thread.start()
        _logger.info('Simplified startup done')


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "TSD based WebRTC"
__plugin_author__ = "Not the TSD Team"
__plugin_url__ = "https://thespaghettidetective.com"
__plugin_description__ = "WebRTC dummy"
__plugin_license__ = "AGPLv3"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = TheSpaghettiDetectivePlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
    }
