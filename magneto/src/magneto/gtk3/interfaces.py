# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Updates Notification Applet (Magneto) GTK3 application}

"""

# sys imports
import os
import sys
import time
import subprocess

# applet imports
from magneto.core import config
from magneto.core.interfaces import MagnetoCore
from magneto.gtk3.components import AppletNoticeWindow

# Entropy imports
from entropy.i18n import _
import entropy.dep

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')

from gi.repository import Gtk, GObject, GLib, Gdk, Notify


def setup_icon_theme(datadir):
    icons = Gtk.IconTheme.get_default()
    search_paths = [config.ICON_PATH,
                    os.path.join(datadir, "icons"),
                    os.path.join(datadir, "emblems")]
    for path in search_paths:
        icons.append_search_path(path)


class Magneto(MagnetoCore):

    def __init__(self):
        from dbus.mainloop.glib import DBusGMainLoop
        super(Magneto, self).__init__(
            main_loop_class = DBusGMainLoop)

        setup_icon_theme(config.DATA_DIR)
        self._setup_gtk_app()

    def _setup_gtk_app(self):
        self.menu = Gtk.Menu()
        self.menu_items = {}
        for item in self._menu_item_list:
            if item is None:
                self.menu.add(Gtk.SeparatorMenuItem())
                continue
            icon_id, title, desc, cb = item

            if icon_id == "exit":
                w = Gtk.ImageMenuItem.new_from_stock("gtk-quit", None)
            else:
                w = Gtk.ImageMenuItem(title)
                w.set_use_underline(True)
                icon_name = self.get_menu_image(icon_id)
                img = Gtk.Image()
                img.set_from_icon_name(icon_name, -1)
                w.set_image(img)

            self.menu_items[icon_id] = w
            w.connect('activate', cb)
            w.show()
            self.menu.add(w)

        self.menu.show_all()

        okay_icon_name = self.icons.get("okay")
        self._status_icon = Gtk.StatusIcon.new_from_icon_name(
            okay_icon_name)
        self._status_icon.connect("popup-menu", self.applet_context_menu)
        self._status_icon.connect("activate", self.applet_doubleclick)

    def _first_check(self):
        def _do_check():
            self.send_check_updates_signal(startup_check = True)
            return False

        if self._dbus_service_available:
            # after 10 seconds, let the system fully start
            GObject.timeout_add_seconds(10, _do_check)

    def startup(self):
        self._dbus_service_available = self.setup_dbus()
        if config.settings['APPLET_ENABLED'] and \
            self._dbus_service_available:
            self.enable_applet(do_check = False)
        else:
            self.disable_applet()
        if not self._dbus_service_available:
            GObject.timeout_add(30000, self.show_service_not_available)
        else:
            self._first_check()

        # Notice Window instance
        self._notice_window = AppletNoticeWindow(self)

        # enter main loop
        GLib.threads_init()
        Gdk.threads_enter()
        Gtk.main()
        Gdk.threads_leave()

    def close_service(self):
        super(Magneto, self).close_service()
        GObject.timeout_add(0, Gtk.main_quit)

    def change_icon(self, icon_name):
        name = self.icons.get(icon_name)
        self._status_icon.set_from_icon_name(name)

    def disable_applet(self, *args):
        super(Magneto, self).disable_applet()
        self.menu_items['disable_applet'].hide()
        self.menu_items['enable_applet'].show()

    def enable_applet(self, w = None, do_check = True):
        done = super(Magneto, self).enable_applet(do_check = do_check)
        if done:
            self.menu_items['disable_applet'].show()
            self.menu_items['enable_applet'].hide()

    def applet_doubleclick(self, widget):
        super(Magneto, self).applet_doubleclick()

    def show_alert(self, title, text, urgency = None, force = False,
                   buttons = None):

        def do_show():
            if ((title, text) == self.last_alert) and not force:
                return False
            Notify.init(_("System Updates"))
            n = Notify.Notification.new(
                title, text, self._status_icon.get_icon_name())

            # Keep a reference or the callback of the actions added
            # below will never work.
            # See: https://bugzilla.redhat.com/show_bug.cgi?id=241531
            self.__last_notification = n

            if urgency == 'critical':
                n.set_urgency(Notify.Urgency.CRITICAL)
            elif urgency == 'low':
                n.set_urgency(Notify.Urgency.LOW)
            self.last_alert = (title, text)

            if buttons:
                for action_id, button_name, button_callback in buttons:
                    n.add_action(action_id, button_name, button_callback, None)

            n.show()
            return False

        GObject.timeout_add(0, do_show)

    def update_tooltip(self, tip):
        self.tooltip_text = tip
        self._status_icon.set_tooltip_markup(tip)

    def applet_context_menu(self, icon, button, activate_time):
        if button == 3:
            self.menu.popup(None, None, None, None, 0, activate_time)
            return

    def hide_notice_window(self):
        self.notice_window_shown = False
        self._notice_window.hide()

    def show_notice_window(self):

        if self.notice_window_shown:
            return
        if not self.package_updates:
            return

        entropy_ver = None
        packages = []
        for atom in self.package_updates:

            key = entropy.dep.dep_getkey(atom)
            avail_rev = entropy.dep.dep_get_entropy_revision(atom)
            avail_tag = entropy.dep.dep_gettag(atom)
            my_pkg = entropy.dep.remove_entropy_revision(atom)
            my_pkg = entropy.dep.remove_tag(my_pkg)
            pkgcat, pkgname, pkgver, pkgrev = entropy.dep.catpkgsplit(
                my_pkg)
            ver = pkgver
            if pkgrev != "r0":
                ver += "-%s" % (pkgrev,)
            if avail_tag:
                ver += "#%s" % (avail_tag,)
            if avail_rev:
                ver += "~%s" % (avail_tag,)

            if key == "sys-apps/entropy":
                entropy_ver = ver

            packages.append((key, ver,))

        critical_txt = ''
        if entropy_ver is not None:
            critical_txt = "%s <b>sys-apps/entropy</b> %s, %s <b>%s</b>. %s."
            txt = critical_txt % (
                _("Your system currently has an outdated version of"),
                _("installed"),
                _("the latest available version is"),
                entropy_ver,
                _("It is recommended that you upgrade to"
                  " the latest before updating any other packages")
                )

        self._notice_window.populate(packages, txt)
        self._notice_window.show()
        self.notice_window_shown = True
