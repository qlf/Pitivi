#!/usr/bin/python
# PiTiVi , Non-linear video editor
#
#       playground.py
#
# Copyright (c) 2005, Edward Hervey <bilboed@bilboed.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

"""
Where all gstreamer pipelines play.
"""

import gobject
import gst
from bin import SmartBin, SmartDefaultBin, SmartFileBin
from utils import bin_contains

class PlayGround(gobject.GObject):
    """
    Holds all the applications pipelines.
    Multimedia sinks can be shared amongst the various pipelines, to offer
    seamless pipeline switching.
    Only one pipeline uses those sinks at any given time, but other pipelines
    can be in a PLAYED state (because they can be encoding).

    Only SmartBin can be added to the PlayGround.

    Signals:
      current-changed : There's a new bin playing
      current-state : The state of the current bin has changed
      bin-added : The given bin was added to the playground
      bin-removed : The given bin was removed from the playground
      error : An error was seen (two strings : reason, details)
    """

    __gsignals__ = {
        "current-changed" : ( gobject.SIGNAL_RUN_LAST,
                              gobject.TYPE_NONE,
                              (gobject.TYPE_PYOBJECT, )),
        "current-state" : ( gobject.SIGNAL_RUN_LAST,
                            gobject.TYPE_NONE,
                            (gobject.TYPE_PYOBJECT, )),
        "bin-added" : ( gobject.SIGNAL_RUN_LAST,
                       gobject.TYPE_NONE,
                       ( gobject.TYPE_PYOBJECT, )),
        "bin-removed" : ( gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          ( gobject.TYPE_PYOBJECT, )),
        "error" : ( gobject.SIGNAL_RUN_LAST,
                    gobject.TYPE_NONE,
                    ( gobject.TYPE_STRING, gobject.TYPE_STRING ))
        }

    def __init__(self):
        gst.log("Starting up playground")
        gobject.GObject.__init__(self)
        # List of used pipelines
        self.pipelines = []
        
        self.vsinkthread = None
        self.asinkthread = None
        
        # Defaut pipeline if no other pipeline is playing
        self.default = SmartDefaultBin()
        bus = self.default.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._busMessageCb, self.default)

        # Current playing pipeline
        self.current = None
        self.currentstart = 0
        self.currentlength = 0
        self.currentpos = 0
        self.tempsmartbin = None
        self.cur_state_signal = None
        self.cur_eos_signal = None
        
        self.state = gst.STATE_READY

        if self.switchToDefault():
            if self.current.set_state(self.state) == gst.STATE_CHANGE_FAILURE:
                gst.warning("Couldn't set default bin to READY")

    def addPipeline(self, pipeline):
        """
        Adds the given pipeline to the playground.
        Returns True if the pipeline was added to the playground.
        """
        gst.debug("pipeline : %s" % pipeline)
        if not isinstance(pipeline, SmartBin):
            return False

        self.pipelines.append(pipeline)
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._busMessageCb, pipeline)
        self.emit("bin-added", pipeline)
        return True

    def removePipeline(self, pipeline):
        """
        Removes the given pipeline from the playground.
        Return True if everything went well.
        """
        gst.debug("pipeline : %s" % pipeline)
        if not pipeline in self.pipelines:
            return True

        bus = pipeline.get_bus()
        bus.remove_signal_watch()

        if pipeline.set_state(gst.STATE_READY) == gst.STATE_CHANGE_FAILURE:
            return False
        if self.current == pipeline:
            if not self.switchToDefault():
                return False
        self.pipelines.remove(pipeline)
        self.emit("bin-removed", pipeline)
        return True

    def switchToPipeline(self, pipeline):
        """
        Switch to the given pipeline for play output.        
        Returns True if the switch was possible.
        """
        if self.current == pipeline:
            return True
        if not pipeline in self.pipelines and not pipeline == self.default:
            return True
        if self.current:
            self.current.info("setting to READY")
            self.current.set_state(gst.STATE_READY)
            self.current.removeAudioSinkThread()
            self.current.removeVideoSinkThread()
            if self.cur_state_signal:
                self.current.disconnect(self.cur_state_signal)
            if self.cur_eos_signal:
                self.current.disconnect(self.cur_eos_signal)
            #self.playthread.remove(self.current)
            # remove the tempsmartbin if it's the current
            if self.current == self.tempsmartbin:
                self.tempsmartbin = None

        self.current = None

        if pipeline.has_video and self.vsinkthread:
            if not pipeline.setVideoSinkThread(self.vsinkthread):
                return False
        if pipeline.has_audio and self.asinkthread:
            if not pipeline.setAudioSinkThread(self.asinkthread):
                return False
        if not pipeline == self.default:
            pipeline.log("Setting the new pipeline to PAUSED so it prerolls")
            if pipeline.set_state(gst.STATE_PAUSED) == gst.STATE_CHANGE_FAILURE:
                return False
        self.current = pipeline
        self.emit("current-changed", self.current)

    def switchToDefault(self):
        """ switch to the default pipeline """
        gst.debug("switching to default")
        return self.switchToPipeline(self.default)

    def setVideoSinkThread(self, vsinkthread):
        """ sets the video sink thread """
        gst.debug("video sink thread : %s" % vsinkthread)
        if self.vsinkthread and self.current.has_video:
            self.current.set_state(gst.STATE_READY)
            self.current.removeVideoSinkThread()
        self.vsinkthread = vsinkthread
        if self.current and self.current.has_video:
            self.current.setVideoSinkThread(self.vsinkthread)

    def setAudioSinkThread(self, asinkthread):
        """ sets the audio sink thread """
        gst.debug("set audio sink thread : %s" % asinkthread)
        if self.asinkthread and self.current.asinkthread:
            self.current.set_state(gst.STATE_READY)
            self.current.removeAudioSinkThread()
        self.asinkthread = asinkthread
        if self.current and self.current.has_audio:
            self.current.setAudioSinkThread(self.asinkthread)

    def _playTemporaryBin(self, tempbin):
        """
        Temporarely play a smartbin.
        Return False if there was a problem.
        """
        gst.debug("BEGINNING tempbin : %s" % tempbin)
        self.pause()
        self.addPipeline(tempbin)
        self.switchToPipeline(tempbin)
        if self.tempsmartbin:
            self.removePipeline(self.tempsmartbin)
        self.tempsmartbin = tempbin
        if self.play() == gst.STATE_CHANGE_FAILURE:
            return False
        gst.debug("END tempbin : %s" % tempbin)
        return True

    def playTemporaryFilesourcefactory(self, factory):
        """
        Temporarely play a FileSourceFactory.
        Returns False if there was a problem.
        """
        gst.debug("factory : %s" % factory)
        if isinstance(self.current, SmartFileBin) and self.current.factory == factory:
            gst.info("Already playing factory : %s" % factory)
            return True
        tempbin = SmartFileBin(factory)
        return self._playTemporaryBin(tempbin)

    def seekInCurrent(self, value, format=gst.FORMAT_TIME):
        """
        Seek to the given position in the current playing bin.
        Returns True if the seek was possible.
        """
        if format == gst.FORMAT_TIME:
            gst.debug("value : %s" % gst.TIME_ARGS (value))
        else:
            gst.debug("value : %d , format:%d" % (value, format))
        if not self.current:
            return False
        target = self.current

        # actual seeking
        res = target.seek(1.0, format, gst.SEEK_FLAG_FLUSH,
                          gst.SEEK_TYPE_SET, value,
                          gst.SEEK_TYPE_NONE, -1)
        if not res:
            gst.warning ("Seeking in current failed !");
            return False
        gst.debug("Seeking to %s succeeded" % gst.TIME_ARGS (value))
        return True

    def shutdown(self):
        """ shutdown the playground and all pipelines """
        for pipeline in self.pipelines:
            gst.debug("Setting pipeline to NULL : %r" % pipeline)
            pipeline.set_state(gst.STATE_NULL)
        gst.debug("Setting DefaultBin to NULL")
        self.default.set_state(gst.STATE_NULL)

    #
    # Bus handler
    #
    def _busMessageCb(self, unused_bus, message, unused_pipeline):
        """ handler for messages from the pipelines' buses """
        gst.info("%s [%s]" % (message.type, message.src))
        if message.type == gst.MESSAGE_STATE_CHANGED:
            oldstate, newstate, pending = message.parse_state_changed()
            message.src.debug("old:%s, new:%s, pending:%s" %
                               (oldstate, newstate, pending))
            if message.src == self.current:
                if pending == gst.STATE_VOID_PENDING:
                    self.emit("current-state", newstate)
        elif message.type == gst.MESSAGE_ERROR:
            error, detail = message.parse_error()
            self._handleError(error, detail, message.src)
        elif message.type == gst.MESSAGE_WARNING:
            error, detail = message.parse_warning()
            self._handleError(error, detail, message.src)


    #
    # Error handling
    #

    def _handleError(self, gerror, detail, source):
        """
        Uses the information from the Gerror, detail and source to
        create meaningful error messages for the User Interface.
        """
        gst.warning("gerror:%s , detail:%s , source:%s" % (gerror, detail, source))
        gst.warning("GError : code:%s, domain:%s (%s), message:%s" % (gerror.code, gerror.domain,
                                                                      type(gerror.domain), gerror.message))
        if bin_contains(self.vsinkthread, source):
            if gerror.domain == 'gst-resource-error-quark' and gerror.code == gst.RESOURCE_ERROR_BUSY:
                self.emit("error", "Video output is busy",
                          "Please check that your video output device isn't already used by another application")
            else:
                self.emit("error", "Video output problem",
                          "There is a problem with your video output device")
        elif bin_contains(self.asinkthread, source):
            if gerror.domain == 'gst-resource-error-quark' and gerror.code == gst.RESOURCE_ERROR_BUSY:
                self.emit("error", "Audio output device is busy",
                          "Please check that your audio output device isn't already used by another application.")
            else:
                self.emit("error", "Audio output problem"<
                          "There is a problem with your audio output device")
        else:
            self.emit("error", gerror.message, detail)
            
        

    def _handleWarning(self, error, detail, source):
        """
        Uses the information from the Gerror, detail and source to
        create meaningful warning messages for the User Interface.
        """
        gst.warning("gerror:%s , detail:%s , source:%s" % (gerror, detail, source))
        gst.warning("GError : code:%s, domain:%s, message:%s" % (gerror.code, gerror.domain, gerror.message))
        

    #
    # playing proxy functions
    #

    def play(self):
        """
        Set the current Pipeline to Play.
        Returns the state transition result (gst.StateChangeResult).
        """
        gst.debug("play")
        if not self.current or not self.asinkthread or not self.vsinkthread:
            gst.warning("returning ???")
            return gst.STATE_CHANGE_FAILURE
        self.state = gst.STATE_PLAYING
        ret = self.current.set_state(self.state)
        gst.debug("change state returned %s" % ret)
        return ret
 
    def pause(self):
        """
        Set the current Pipeline to Pause.
        Returns the state change transition result (gst.StateChangeResult).
        """
        gst.debug("pause")
        if not self.current or self.current == self.default:
            return gst.STATE_CHANGE_SUCCESS
        self.state = gst.STATE_PAUSED
        return self.current.set_state(self.state)

    def fast_forward(self):
        """ fast forward the current pipeline """
        pass

    def rewind(self):
        """ play the current pipeline backwards """
        pass

    def forward_one(self):
        """ forward the current pipeline by one video frame """
        pass

    def backward_one(self):
        """ rewind the current pipeline by one video frame """
        pass

    def seek(self, time):
        """ seek in the current pipeline """
        pass

