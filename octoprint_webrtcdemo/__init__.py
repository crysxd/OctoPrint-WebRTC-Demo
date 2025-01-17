# coding=utf-8
from __future__ import absolute_import
import logging
import threading
import sys

from .utils import (
    not_using_pi_camera, OctoPrintSettingsUpdater, server_request
)
from .janus import JanusConn
from .turn import startTurnReigistry, stopTurnRegistry
from .webcam_stream import WebcamStreamer

import octoprint.plugin

__python_version__ = 3 if sys.version_info >= (3, 0) else 2

_logger = logging.getLogger('octoprint.plugins.webrtcdemo')

POST_STATUS_INTERVAL_SECONDS = 50.0


class WebRtcDemoPlugin(
        octoprint.plugin.SettingsPlugin,
        octoprint.plugin.StartupPlugin,
        octoprint.plugin.ShutdownPlugin,
        octoprint.plugin.AssetPlugin,
        octoprint.plugin.TemplatePlugin,
        ):

    def __init__(self):
        self.octoprint_settings_updater = OctoPrintSettingsUpdater(self)
        self.webcam_streamer = None
        self.janus = JanusConn(self)

    # ~~Asset Plugin

    def get_assets(self):
        return dict(
            js=["js/adapter.js","js/janus.js","js/webrtc_demo.js"],
            less=["less/webrtc_demo.less"]
        )

    def get_template_configs(self):
        return [
            dict(type="tab", template="webrtcdemo_tab.jinja2", custom_bindings=True),
        ]
    
    # ~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return dict(
            pi_cam_resolution='medium',
            video_streaming_compatible_mode='auto',
        )

    # ~~Shutdown Plugin

    def on_shutdown(self):
        if self.janus:
            self.janus.shutdown()
        if self.webcam_streamer:
            self.webcam_streamer.restore()
        
        stopTurnRegistry()
        not_using_pi_camera()

    # ~~Startup Plugin

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

        _logger.info('Starting TURN registry server')
        turn_thread = threading.Thread(target=startTurnReigistry)
        turn_thread.daemon = True
        turn_thread.start()

        # Janus may take a while to start, or fail to start. Put it in thread to make sure it does not block
        _logger.info('Starting Janus server')
        janus_thread = threading.Thread(target=self.janus.start)
        janus_thread.daemon = True
        janus_thread.start()

        _logger.info('Starting webcam streamer')
        self.webcam_streamer = WebcamStreamer(self)
        stream_thread = threading.Thread(target=self.webcam_streamer.video_pipeline)
        stream_thread.daemon = True
        stream_thread.start()
        _logger.info('Simplified startup done')


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "WebRTC Demo"
__plugin_author__ = "crysxd"
__plugin_url__ = "https://github.com/crysxd/OctoPrint-WebRTC-Demo"
__plugin_description__ = "WebRTC demo based on TSD implementation"
__plugin_license__ = "AGPLv3"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = WebRtcDemoPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
    }
