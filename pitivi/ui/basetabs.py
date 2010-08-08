# PiTiVi , Non-linear video editor
#
#       ui/basetabs.py
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

import gtk

from pitivi.ui.common import SPACING
from pitivi.ui.sourcelist import SourceList
from pitivi.ui.effectlist import EffectList
from pitivi.ui.clipproperties import ClipProperties

class NotebookManager(gtk.HBox):
    def __init__(self, app, uimanager, project):
        gtk.HBox.__init__(self)

        #Notebooks
        self.left_notebook = BaseTabs(app, True)
        self.right_notebook = BaseTabs(app, True)

        #Tabs
        self.sourcelist = SourceList(app, uimanager)
        self.effectlist = EffectList(app)
        self.clipconfig = ClipProperties(app)
        self.clipconfig.project = project

        self.wins = []
        self.hpaned = None

        windows, left_tabs, right_tabs = self._getSettings(app)

        self._updateUi(windows, left_tabs, right_tabs)

    def _getSettings(self, app):
        windows = []
        left_tabs = []
        right_tabs = []
        if not app.settings.effectLibraryHasWindow:
            left_tabs.append(self.effectlist)
        if not app.settings.mediaLibraryHasWindow:
            left_tabs.append(self.sourcelist)
        if not app.settings.clipPropertiesHasWindow:
            if not app.settings.clipPropertiesGroupedWithOther:
                right_tabs.append(self.clipconfig)
            else:
                left_tabs.append(self.clipconfig)

        return windows, left_tabs, right_tabs

    def _updateUi(self, windows, left_tabs, right_tabs):
        for window in windows:
            self._createWindow(window)
        if left_tabs and right_tabs:
            self._createHPaned(left_tabs, right_tabs)
        else:
            left_tabs.extend(right_tabs)
            self._addTabs(left_tabs)

    def _createWindow(self, tabs):
        pass

    def _createHPaned(self, left_tabs, right_tabs):
        if not self.hpaned:
            self.hpaned = gtk.HPaned()

        for tab in left_tabs:
            self.left_notebook.append_page(tab,
                                           tab.label)
        for tab in right_tabs:
            self.right_notebook.append_page(tab,
                                            tab.label)

        self.hpaned.pack1(self.left_notebook, resize=False, shrink=False)
        self.hpaned.pack2(self.right_notebook, resize=False, shrink=False)
        self.pack_start(self.hpaned)

    def _addTabs(self, tabs):
        for tab in tabs:
            self.left_notebook.append_page(tab,
                                           tab.label)

        self.pack_start(self.left_notebook)

class BaseTabs(gtk.Notebook):
    def __init__(self, app, hide_hpaned=False):
        """ initialize """
        gtk.Notebook.__init__(self)
        self.set_border_width(SPACING)

        self.connect("create-window", self._createWindowCb)
        self._hide_hpaned = hide_hpaned
        self.app = app
        self._createUi()

    def _createUi(self):
        """ set up the gui """
        settings = self.get_settings()
        settings.props.gtk_dnd_drag_threshold = 1
        self.set_tab_pos(gtk.POS_TOP)

    def append_page(self, child, label):
        gtk.Notebook.append_page(self, child, label)
        self._set_child_properties(child, label)
        child.show()
        label.show()

    def _set_child_properties(self, child, label):
        self.child_set_property(child, "detachable", True)
        self.child_set_property(child, "tab-expand", False)
        self.child_set_property(child, "tab-fill", True)
        label.props.xalign = 0.0

    def _detachedComponentWindowDestroyCb(self, window, child,
            original_position, label):
        notebook = window.child
        position = notebook.child_get_property(child, "position")
        notebook.remove_page(position)
        label = gtk.Label(label)
        self.insert_page(child, label, original_position)
        self._set_child_properties(child, label)
        self.child_set_property(child, "detachable", True)

        if self._hide_hpaned:
            self._showHpanedInMainWindow()

    def _createWindowCb(self, from_notebook, child, x, y):
        original_position = self.child_get_property(child, "position")
        label = self.child_get_property(child, "tab-label")
        window = gtk.Window()
        window.set_title(label)
        window.set_default_size(600, 400)
        window.connect("destroy", self._detachedComponentWindowDestroyCb,
                child, original_position, label)
        notebook = gtk.Notebook()
        window.add(notebook)

        window.show_all()
        # set_uposition is deprecated but what should I use instead?
        window.set_uposition(x, y)

        return notebook
