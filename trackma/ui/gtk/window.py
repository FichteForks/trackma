# This file is part of Trackma.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import html
import os
import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango, GObject
from trackma.ui.gtk.accountswindow import AccountsWindow
from trackma.ui.gtk.imagebox import ImageBox
from trackma.ui.gtk.imagetask import ImageTask
from trackma.ui.gtk.imagetask import imaging_available
from trackma.ui.gtk.searchwindow import SearchWindow
from trackma.ui.gtk.settingswindow import SettingsWindow
from trackma.ui.gtk.settingswindow import tray_available
from trackma.ui.gtk.showinfowindow import ShowInfoWindow
from trackma.ui.gtk.showtreeview import ShowTreeView
from trackma.engine import Engine
from trackma.accounts import AccountManager
from trackma import utils
from trackma import messenger


class TrackmaWindow:
    engine = None
    config = None
    show_lists = dict()
    image_thread = None
    close_thread = None
    hidden = False
    quit = False

    statusicon = None

    def __init__(self, debug=False):
        self.debug = debug

        self.configfile = None
        self.accountsel = None
        self.account = None

        self.main_window = None
        self.mb_play = None
        self.mb_play_random = None
        self.mb_folder = None
        self.mb_info = None
        self.mb_web = None
        self.mb_copy = None
        self.mb_alt_title = None
        self.mb_delete = None
        self.mb_exit = None
        self.mb_addsearch = None
        self.mb_sync = None
        self.mb_retrieve = None
        self.mb_send = None
        self.mb_switch_account = None
        self.mb_settings = None
        self.mb_mediatype_menu = None
        self.top_hbox = None
        self.show_image = None
        self.show_title = None
        self.api_icon = None
        self.api_user = None
        self.rem_epp_button = None
        self.show_ep_button = None
        self.show_ep_num = None
        self.add_epp_button = None
        self.play_next_button = None
        self.show_score = None
        self.scoreset_button = None
        self.statusmodel = None
        self.statusbox = None
        self.statusbox_handler = None
        self.notebook = None
        self.statusbar = None

        self.selected_show = None
        self.score_decimal_places = None

    def main(self):
        """Start the Account Selector"""
        self.configfile = utils.to_config_path('ui-Gtk.json')
        self.config = utils.parse_config(self.configfile, utils.gtk_defaults)

        manager = AccountManager()

        # Use the remembered account if there's one
        if manager.get_default():
            self.start(manager.get_default())
        else:
            self.accountsel = AccountsWindow(manager)
            self.accountsel.use_button.connect("clicked", self.use_account)
            self.accountsel.create()

        Gtk.main()

    def __do_switch_account(self, widget, switch=True, forget=False):
        manager = AccountManager()
        if forget:
            manager.set_default(None)
        self.accountsel = AccountsWindow(manager = AccountManager(), switch=switch)
        self.accountsel.use_button.connect("clicked", self.use_account)
        self.accountsel.create()

    def use_account(self, widget):
        """Start the main application with the following account"""
        accountid = self.accountsel.get_selected_id()
        account = self.accountsel.manager.get_account(accountid)
        # If remember box is checked, set as default account
        if self.accountsel.is_remember():
            self.accountsel.manager.set_default(accountid)
        else:
            self.accountsel.manager.set_default(None)

        self.accountsel.destroy()

        # Reload the engine if already started,
        # start it otherwise
        if self.engine and self.engine.loaded:
            self.__do_reload(None, account, None)
        else:
            self.start(account)

    def start(self, account):
        """Create the main window"""
        # Create engine
        self.account = account
        self.engine = Engine(account, self.message_handler)

        self.main_window = Gtk.Window(Gtk.WindowType.TOPLEVEL)
        self.main_window.set_position(Gtk.WindowPosition.CENTER)
        self.main_window.connect('delete_event', self.delete_event)
        self.main_window.connect('destroy', self.on_destroy)
        self.main_window.set_title('Trackma-gtk ' + utils.VERSION)
        Gtk.Window.set_default_icon_from_file(utils.datadir + '/data/icon.png')
        if self.config['remember_geometry']:
            self.main_window.resize(self.config['last_width'], self.config['last_height'])

        # Menus
        mb_show = Gtk.Menu()
        self.mb_play = Gtk.ImageMenuItem('Play Next', Gtk.Image.new_from_icon_name(Gtk.STOCK_MEDIA_PLAY, 0))
        self.mb_play.connect("activate", self.__do_play, True)
        self.mb_play_random = Gtk.MenuItem('Play random')
        self.mb_play_random.connect("activate", self.__do_play_random)
        mb_scanlibrary = Gtk.MenuItem('Re-scan library')
        self.mb_folder = Gtk.MenuItem("Open containing folder")
        self.mb_folder.connect("activate", self.do_containingFolder)
        mb_scanlibrary.connect("activate", self.__do_scanlibrary)
        self.mb_info = Gtk.MenuItem('Show details...')
        self.mb_info.connect("activate", self.__do_info)
        self.mb_web = Gtk.MenuItem("Open web site")
        self.mb_web.connect("activate", self.__do_web)
        self.mb_copy = Gtk.MenuItem("Copy title to clipboard")
        self.mb_copy.connect("activate", self.__do_copytoclip)
        self.mb_alt_title = Gtk.MenuItem("Set alternate title...")
        self.mb_alt_title.connect("activate", self.__do_altname)
        self.mb_delete = Gtk.ImageMenuItem('Delete', Gtk.Image.new_from_icon_name(Gtk.STOCK_DELETE, 0))
        self.mb_delete.connect("activate", self.__do_delete)
        self.mb_exit = Gtk.ImageMenuItem('Quit', Gtk.Image.new_from_icon_name(Gtk.STOCK_QUIT, 0))
        self.mb_exit.connect("activate", self.__do_quit, None)
        self.mb_addsearch = Gtk.ImageMenuItem("Add/Search Shows", Gtk.Image.new_from_icon_name(Gtk.STOCK_ADD, 0))
        self.mb_addsearch.connect("activate", self._do_addsearch)

        mb_show.append(self.mb_addsearch)
        mb_show.append(self.mb_play_random)
        mb_show.append(Gtk.SeparatorMenuItem())
        mb_show.append(self.mb_play)
        mb_show.append(self.mb_info)
        mb_show.append(self.mb_web)
        mb_show.append(self.mb_folder)
        mb_show.append(Gtk.SeparatorMenuItem())
        mb_show.append(self.mb_copy)
        mb_show.append(self.mb_alt_title)
        mb_show.append(Gtk.SeparatorMenuItem())
        mb_show.append(self.mb_delete)
        mb_show.append(Gtk.SeparatorMenuItem())
        mb_show.append(self.mb_exit)

        mb_list = Gtk.Menu()
        self.mb_sync = Gtk.ImageMenuItem('Sync', Gtk.Image.new_from_icon_name(Gtk.STOCK_REFRESH, 0))
        self.mb_sync.connect("activate", self.__do_sync)
        self.mb_retrieve = Gtk.ImageMenuItem("Retrieve list")
        self.mb_retrieve.connect("activate", self.__do_retrieve_ask)
        self.mb_send = Gtk.MenuItem('Send changes')
        self.mb_send.connect("activate", self.__do_send)

        mb_list.append(self.mb_sync)
        mb_list.append(Gtk.SeparatorMenuItem())
        mb_list.append(self.mb_retrieve)
        mb_list.append(self.mb_send)
        mb_list.append(Gtk.SeparatorMenuItem())
        mb_list.append(mb_scanlibrary)

        mb_options = Gtk.Menu()
        self.mb_switch_account = Gtk.MenuItem('Switch Account...')
        self.mb_switch_account.connect("activate", self.__do_switch_account)
        self.mb_settings = Gtk.MenuItem('Global Settings...')
        self.mb_settings.connect("activate", self.__do_settings)

        mb_options.append(self.mb_switch_account)
        mb_options.append(Gtk.SeparatorMenuItem())
        mb_options.append(self.mb_settings)

        self.mb_mediatype_menu = Gtk.Menu()

        mb_help = Gtk.Menu()
        mb_about = Gtk.ImageMenuItem('About', Gtk.Image.new_from_icon_name(Gtk.STOCK_ABOUT, 0))
        mb_about.connect("activate", self.on_about)
        mb_help.append(mb_about)

        # Root menubar
        root_menu1 = Gtk.MenuItem("Show")
        root_menu1.set_submenu(mb_show)
        root_list = Gtk.MenuItem("List")
        root_list.set_submenu(mb_list)
        root_options = Gtk.MenuItem("Options")
        root_options.set_submenu(mb_options)
        mb_mediatype = Gtk.MenuItem("Mediatype")
        mb_mediatype.set_submenu(self.mb_mediatype_menu)
        root_menu2 = Gtk.MenuItem("Help")
        root_menu2.set_submenu(mb_help)

        mb = Gtk.MenuBar()
        mb.append(root_menu1)
        mb.append(root_list)
        mb.append(mb_mediatype)
        mb.append(root_options)
        mb.append(root_menu2)

        # Create vertical box
        vbox = Gtk.VBox(False, 0)
        self.main_window.add(vbox)

        vbox.pack_start(mb, False, False, 0)

        # Toolbar
        #toolbar = Gtk.Toolbar()
        #toolbar.insert_stock(Gtk.STOCK_REFRESH, "Sync", "Sync", None, None, 0)
        #toolbar.insert_stock(Gtk.STOCK_ADD, "Sync", "Sync", None, None, 1)
        #toolbar.insert_stock(Gtk.STOCK_MEDIA_PLAY, "Sync", "Sync", None, None, 2)
        #vbox.pack_start(toolbar, False, False, 0)

        self.top_hbox = Gtk.HBox(False, 10)
        self.top_hbox.set_border_width(5)

        self.show_image = ImageBox(100, 149)
        self.top_hbox.pack_start(self.show_image, False, False, 0)

        # Right box
        top_right_box = Gtk.VBox(False, 0)

        # Line 1: Title
        line1 = Gtk.HBox(False, 5)
        self.show_title = Gtk.Label()
        self.show_title.set_use_markup(True)
        self.show_title.set_alignment(0, 0.5)
        self.show_title.set_ellipsize(Pango.EllipsizeMode.END)

        line1.pack_start(self.show_title, True, True, 0)

        # API info
        api_hbox = Gtk.HBox(False, 5)
        self.api_icon = Gtk.Image()
        self.api_user = Gtk.Label()
        api_hbox.pack_start(self.api_icon, True, True, 0)
        api_hbox.pack_start(self.api_user, True, True, 0)

        alignment1 = Gtk.Alignment(xalign=1, yalign=0, xscale=0)
        alignment1.add(api_hbox)
        line1.pack_start(alignment1, False, False, 0)

        top_right_box.pack_start(line1, True, True, 0)

        # Line 2: Episode
        line2 = Gtk.HBox(False, 5)
        line2_t = Gtk.Label('  Progress')
        line2_t.set_size_request(70, -1)
        line2_t.set_alignment(0, 0.5)
        line2.pack_start(line2_t, False, False, 0)

        # Buttons
        rem_icon = Gtk.Image()
        rem_icon.set_from_stock(Gtk.STOCK_REMOVE, Gtk.IconSize.BUTTON)
        self.rem_epp_button = Gtk.Button()
        self.rem_epp_button.set_image(rem_icon)
        self.rem_epp_button.connect("clicked", self.__do_rem_epp)
        self.rem_epp_button.set_sensitive(False)
        line2.pack_start(self.rem_epp_button, False, False, 0)

        self.show_ep_button = Gtk.Button()
        self.show_ep_button.set_relief(Gtk.ReliefStyle.NONE)
        self.show_ep_button.connect("clicked", self._show_episode_entry)
        self.show_ep_button.set_label("-")
        self.show_ep_button.set_size_request(40, -1)
        line2.pack_start(self.show_ep_button, False, False, 0)

        self.show_ep_num = Gtk.Entry()
        self.show_ep_num.set_sensitive(False)
        self.show_ep_num.connect("activate", self.__do_update)
        self.show_ep_num.connect("focus-out-event", self._hide_episode_entry)
        self.show_ep_num.set_size_request(40, -1)
        line2.pack_start(self.show_ep_num, False, False, 0)

        add_icon = Gtk.Image()
        add_icon.set_from_stock(Gtk.STOCK_ADD, Gtk.IconSize.BUTTON)
        self.add_epp_button = Gtk.Button()
        self.add_epp_button.set_image(add_icon)
        self.add_epp_button.connect("clicked", self._do_add_epp)
        self.add_epp_button.set_sensitive(False)
        line2.pack_start(self.add_epp_button, False, False, 0)

        self.play_next_button = Gtk.Button('Play Next')
        self.play_next_button.connect("clicked", self.__do_play, True)
        self.play_next_button.set_sensitive(False)
        line2.pack_start(self.play_next_button, False, False, 0)

        top_right_box.pack_start(line2, True, False, 0)

        # Line 3: Score
        line3 = Gtk.HBox(False, 5)
        line3_t = Gtk.Label('  Score')
        line3_t.set_size_request(70, -1)
        line3_t.set_alignment(0, 0.5)
        line3.pack_start(line3_t, False, False, 0)
        self.show_score = Gtk.SpinButton()
        self.show_score.set_adjustment(Gtk.Adjustment(upper=10, step_incr=1))
        self.show_score.set_sensitive(False)
        self.show_score.connect("activate", self.__do_score)
        line3.pack_start(self.show_score, False, False, 0)

        self.scoreset_button = Gtk.Button('Set')
        self.scoreset_button.connect("clicked", self.__do_score)
        self.scoreset_button.set_sensitive(False)
        line3.pack_start(self.scoreset_button, False, False, 0)

        top_right_box.pack_start(line3, True, False, 0)

        # Line 4: Status
        line4 = Gtk.HBox(False, 5)
        line4_t = Gtk.Label('  Status')
        line4_t.set_size_request(70, -1)
        line4_t.set_alignment(0, 0.5)
        line4.pack_start(line4_t, False, False, 0)

        self.statusmodel = Gtk.ListStore(str, str)

        self.statusbox = Gtk.ComboBox.new_with_model(self.statusmodel)
        cell = Gtk.CellRendererText()
        self.statusbox.pack_start(cell, True)
        self.statusbox.add_attribute(cell, 'text', 1)
        self.statusbox_handler = self.statusbox.connect("changed", self.__do_status)
        self.statusbox.set_sensitive(False)

        alignment = Gtk.Alignment(xalign=0, yalign=0.5, xscale=0)
        alignment.add(self.statusbox)

        line4.pack_start(alignment, False, False, 0)

        top_right_box.pack_start(line4, True, False, 0)

        self.top_hbox.pack_start(top_right_box, True, True, 0)
        vbox.pack_start(self.top_hbox, False, False, 0)

        # Notebook for lists
        self.notebook = Gtk.Notebook()
        self.notebook.set_tab_pos(Gtk.PositionType.TOP)
        self.notebook.set_scrollable(True)
        self.notebook.set_border_width(3)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_size_request(550, 300)
        sw.set_border_width(5)
        self.notebook.append_page(sw, Gtk.Label("Status"))

        vbox.pack_start(self.notebook, True, True, 0)

        self.statusbar = Gtk.Statusbar()
        self.statusbar.push(0, 'Trackma-gtk ' + utils.VERSION)
        vbox.pack_start(self.statusbar, False, False, 0)

        vbox.show_all()

        # Accelerators
        accelgrp = Gtk.AccelGroup()

        key, mod = Gtk.accelerator_parse("<Control>N")
        self.mb_play.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>R")
        self.mb_play_random.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>A")
        self.mb_addsearch.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>S")
        self.mb_sync.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>E")
        self.mb_send.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>D")
        self.mb_retrieve.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>Right")
        self.add_epp_button.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        self.add_epp_button.set_tooltip_text("Ctrl+Right")
        key, mod = Gtk.accelerator_parse("<Control>Left")
        self.rem_epp_button.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        self.rem_epp_button.set_tooltip_text("Ctrl+Left")
        key, mod = Gtk.accelerator_parse("<Control>L")
        mb_scanlibrary.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>W")
        self.mb_web.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>Delete")
        self.mb_delete.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>Q")
        self.mb_exit.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>O")
        self.mb_settings.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Control>Y")
        self.mb_copy.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Shift>A")
        self.mb_alt_title.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)
        key, mod = Gtk.accelerator_parse("<Shift>C")
        self.mb_switch_account.add_accelerator("activate", accelgrp, key, mod, Gtk.AccelFlags.VISIBLE)

        self.main_window.add_accel_group(accelgrp)

        # Status icon
        if tray_available:
            self.statusicon = Gtk.StatusIcon()
            self.statusicon.set_from_file(utils.datadir + '/data/icon.png')
            self.statusicon.set_tooltip_text('Trackma-gtk ' + utils.VERSION)
            self.statusicon.connect('activate', self.status_event)
            self.statusicon.connect('popup-menu', self.status_menu_event)
            if self.config['show_tray']:
                self.statusicon.set_visible(True)
            else:
                self.statusicon.set_visible(False)

        # Engine configuration
        self.engine.connect_signal('episode_changed', self.changed_show)
        self.engine.connect_signal('score_changed', self.changed_show)
        self.engine.connect_signal('status_changed', self.changed_show_status)
        self.engine.connect_signal('playing', self.playing_show)
        self.engine.connect_signal('show_added', self.changed_show_status)
        self.engine.connect_signal('show_deleted', self.changed_show_status)
        self.engine.connect_signal('prompt_for_update', self.__do_update_next)

        self.selected_show = 0

        if not imaging_available:
            self.show_image.pholder_show("PIL library\nnot available")

        self.allow_buttons(False)

        # Don't show the main dialog if start in tray option is set
        if self.statusicon and self.config['show_tray'] and self.config['start_in_tray']:
            self.hidden = True
        else:
            self.main_window.show()

        self.show_ep_num.hide()

        self.start_engine()

    def _clear_gui(self):
        self.show_title.set_text('<span size="14000"><b>Trackma</b></span>')
        self.show_title.set_use_markup(True)
        self.show_image.pholder_show("Trackma")

        current_api = utils.available_libs[self.account['api']]
        api_iconfile = current_api[1]

        self.main_window.set_title('Trackma-gtk %s [%s (%s)]' % (
            utils.VERSION,
            self.engine.api_info['name'],
            self.engine.api_info['mediatype']))
        self.api_icon.set_from_file(api_iconfile)
        if self.statusicon and self.config['tray_api_icon']:
            self.statusicon.set_from_file(api_iconfile)
        self.api_user.set_text("%s (%s)" % (
            self.engine.get_userconfig('username'),
            self.engine.api_info['mediatype']))

        can_play = self.engine.mediainfo['can_play']
        can_update = self.engine.mediainfo['can_update']

        self.play_next_button.set_sensitive(can_play)

        self.show_ep_button.set_sensitive(can_update)
        self.show_ep_num.set_sensitive(can_update)
        self.add_epp_button.set_sensitive(can_update)

    def _create_lists(self):
        statuses_nums = self.engine.mediainfo['statuses']
        statuses_names = self.engine.mediainfo['statuses_dict']

        # Statusbox
        self.statusmodel.clear()
        for status in statuses_nums:
            self.statusmodel.append([str(status), statuses_names[status]])
        self.statusbox.set_model(self.statusmodel)
        self.statusbox.show_all()

        # Clear notebook
        for i in range(self.notebook.get_n_pages()):
            self.notebook.remove_page(-1)

        # Insert pages
        for status in statuses_nums:
            name = statuses_names[status]

            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            sw.set_size_request(550, 300)
            sw.set_border_width(5)

            self.show_lists[status] = ShowTreeView(
                status,
                self.config['colors'],
                self.config['visible_columns'],
                self.config['episodebar_style'])
            self.show_lists[status].get_selection().connect("changed", self.select_show)
            self.show_lists[status].connect("row-activated", self.__do_info)
            self.show_lists[status].connect("button-press-event", self.showview_context_menu)
            self.show_lists[status].connect("column-toggled", self._column_toggled)
            self.show_lists[status].pagenumber = self.notebook.get_n_pages()
            sw.add(self.show_lists[status])

            self.notebook.append_page(sw, Gtk.Label(name))
            self.notebook.show_all()
            self.show_lists[status].realize()

        self.notebook.connect("switch-page", self.select_show)

    def _column_toggled(self, w, column_name, visible):
        if visible:
            # Make column visible
            self.config['visible_columns'].append(column_name)

            for view in self.show_lists.values():
                view.cols[column_name].set_visible(True)
        else:
            # Make column invisible
            if len(self.config['visible_columns']) <= 1:
                return # There should be at least 1 column visible

            self.config['visible_columns'].remove(column_name)
            for view in self.show_lists.values():
                view.cols[column_name].set_visible(False)

        utils.save_config(self.config, self.configfile)

    def _show_episode_entry(self, *args):
        self.show_ep_button.hide()
        self.show_ep_num.set_text(self.show_ep_button.get_label())
        self.show_ep_num.show()
        self.show_ep_num.grab_focus()

    def _hide_episode_entry(self, *args):
        self.show_ep_num.hide()
        self.show_ep_button.show()

    def idle_destroy(self):
        GObject.idle_add(self.idle_destroy_push)

    def idle_destroy_push(self):
        self.quit = True
        self.main_window.destroy()

    def idle_restart(self):
        GObject.idle_add(self.idle_restart_push)

    def idle_restart_push(self):
        self.quit = False
        self.main_window.destroy()
        self.__do_switch_account(None, False, forget=True)

    def on_destroy(self, widget):
        if self.quit:
            Gtk.main_quit()

    def status_event(self, widget):
        # Called when the tray icon is left-clicked
        if self.hidden:
            self.main_window.show()
            self.hidden = False
        else:
            self.main_window.hide()
            self.hidden = True

    def status_menu_event(self, icon, button, time):
        # Called when the tray icon is right-clicked
        menu = Gtk.Menu()
        mb_show = Gtk.MenuItem("Show/Hide")
        mb_about = Gtk.ImageMenuItem('About', Gtk.Image.new_from_icon_name(Gtk.STOCK_ABOUT, 0))
        mb_quit = Gtk.ImageMenuItem('Quit', Gtk.Image.new_from_icon_name(Gtk.STOCK_QUIT, 0))

        mb_show.connect("activate", self.status_event)
        mb_about.connect("activate", self.on_about)
        mb_quit.connect("activate", self.__do_quit)

        menu.append(mb_show)
        menu.append(mb_about)
        menu.append(Gtk.SeparatorMenuItem())
        menu.append(mb_quit)
        menu.show_all()

        def pos(menu, icon):
            return Gtk.StatusIcon.position_menu(menu, icon)

        menu.popup(None, None, None, pos, button, time)

    def delete_event(self, widget, event, data=None):
        if self.statusicon and self.statusicon.get_visible() and self.config['close_to_tray']:
            self.hidden = True
            self.main_window.hide()
        else:
            self.__do_quit()
        return True

    def __do_quit(self, widget=None, event=None, data=None):
        if self.config['remember_geometry']:
            self.__do_store_geometry()
        if self.close_thread is None:
            self.close_thread = threading.Thread(target=self.task_unload)
            self.close_thread.start()

    def __do_store_geometry(self):
        (width, height) = self.main_window.get_size()
        self.config['last_width'] = width
        self.config['last_height'] = height
        utils.save_config(self.config, self.configfile)

    def _do_addsearch(self, widget):
        page = self.notebook.get_current_page()
        current_status = self.engine.mediainfo['statuses'][page]

        win = SearchWindow(self.engine, self.config['colors'], current_status)
        win.show_all()

    def __do_settings(self, widget):
        win = SettingsWindow(self.engine, self.config, self.configfile)
        win.show_all()

    def __do_reload(self, widget, account, mediatype):
        self.selected_show = 0

        threading.Thread(target=self.task_reload, args=[account, mediatype]).start()

    def __do_play(self, widget, playnext, ep=None):
        threading.Thread(target=self.task_play, args=(playnext,ep)).start()

    def __do_play_random(self, widget):
        threading.Thread(target=self.task_play_random).start()

    def __do_scanlibrary(self, widget):
        threading.Thread(target=self.task_scanlibrary).start()

    def __do_delete(self, widget):
        try:
            show = self.engine.get_show_info(self.selected_show)
            self.engine.delete_show(show)
        except utils.TrackmaError as e:
            self.error(e)

    def __do_info(self, widget, d1=None, d2=None):
        show = self.engine.get_show_info(self.selected_show)
        ShowInfoWindow(self.engine, show)

    def _do_add_epp(self, widget):
        show = self.engine.get_show_info(self.selected_show)
        try:
            self.engine.set_episode(self.selected_show, show['my_progress'] + 1)
        except utils.TrackmaError as e:
            self.error(e)

    def __do_rem_epp(self, widget):
        show = self.engine.get_show_info(self.selected_show)
        try:
            self.engine.set_episode(self.selected_show, show['my_progress'] - 1)
        except utils.TrackmaError as e:
            self.error(e)

    def __do_update(self, widget):
        self._hide_episode_entry()
        ep = self.show_ep_num.get_text()
        try:
            self.engine.set_episode(self.selected_show, ep)
        except utils.TrackmaError as e:
            self.error(e)

    def __do_score(self, widget):
        score = self.show_score.get_value()
        try:
            self.engine.set_score(self.selected_show, score)
        except utils.TrackmaError as e:
            self.error(e)

    def __do_status(self, widget):
        statusiter = self.statusbox.get_active_iter()
        status = self.statusmodel.get(statusiter, 0)[0]

        try:
            self.engine.set_status(self.selected_show, status)
        except utils.TrackmaError as e:
            self.error(e)

    def __do_update_next(self, show, played_ep):
        GObject.idle_add(self.task_update_next, show, played_ep)

    def changed_show(self, show):
        GObject.idle_add(self.task_changed_show, show)

    def changed_show_title(self, show, altname):
        GObject.idle_add(self.task_changed_show_title, show, altname)

    def changed_show_status(self, show, old_status=None):
        GObject.idle_add(self.task_changed_show_status, show, old_status)

    def playing_show(self, show, is_playing, episode):
        GObject.idle_add(self.task_playing_show, show, is_playing, episode)

    def task_changed_show(self, show):
        status = show['my_status']
        self.show_lists[status].update(show)
        if show['id'] == self.selected_show:
            self.show_ep_button.set_label(str(show['my_progress']))
            self.show_score.set_value(show['my_score'])

    def task_changed_show_title(self, show, altname):
        status = show['my_status']
        self.show_lists[status].update_title(show, altname)

    def task_changed_show_status(self, show, old_status):
        # Rebuild lists
        status = show['my_status']

        self.build_list(status)
        if old_status:
            self.build_list(old_status)

        pagenumber = self.show_lists[status].pagenumber
        self.notebook.set_current_page(pagenumber)

        self.show_lists[status].select(show)

    def task_playing_show(self, show, is_playing, episode):
        status = show['my_status']
        self.show_lists[status].playing(show, is_playing)

    def task_update_next(self, show, played_ep):
        dialog = Gtk.MessageDialog(self.main_window,
                                   Gtk.DialogFlags.MODAL,
                                   Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.YES_NO,
                                   "Update %s to episode %d?" % (show['title'], played_ep))
        dialog.show_all()
        dialog.connect("response", self.task_update_next_response, show, played_ep)

    def task_update_next_response(self, widget, response, show, played_ep):
        widget.destroy()
        # Update show to the played episode
        if response == Gtk.ResponseType.YES:
            try:
                show = self.engine.set_episode(show['id'], played_ep)
                status = show['my_status']
                self.show_lists[status].update(show)
            except utils.TrackmaError as e:
                self.error(e)

    def task_play(self, playnext, ep):
        self.allow_buttons(False)

        show = self.engine.get_show_info(self.selected_show)

        try:
            if playnext:
                self.engine.play_episode(show)
            else:
                if not ep:
                    ep = self.show_ep_num.get_value_as_int()
                self.engine.play_episode(show, ep)
        except utils.TrackmaError as e:
            self.error(e)

        self.status("Ready.")
        self.allow_buttons(True)

    def task_play_random(self):
        self.allow_buttons(False)

        try:
            self.engine.play_random()
        except utils.TrackmaError as e:
            self.error(e)

        self.status("Ready.")
        self.allow_buttons(True)

    def task_scanlibrary(self):
        try:
            self.engine.scan_library(rescan=True)
        except utils.TrackmaError as e:
            self.error(e)

        GObject.idle_add(self.build_list, self.engine.mediainfo['status_start'])

        self.status("Ready.")
        self.allow_buttons(True)

    def task_unload(self):
        self.allow_buttons(False)
        self.engine.unload()

        self.idle_destroy()

    def __do_retrieve_ask(self, widget):
        queue = self.engine.get_queue()

        if not queue:
            dialog = Gtk.MessageDialog(self.main_window,
                                       Gtk.DialogFlags.MODAL,
                                       Gtk.MessageType.QUESTION,
                                       Gtk.ButtonsType.YES_NO,
                                       "There are %d queued changes in your list. If you retrieve the remote list now you will lose your queued changes. Are you sure you want to continue?" % len(queue))
            dialog.show_all()
            dialog.connect("response", self.__do_retrieve)
        else:
            # If the user doesn't have any queued changes
            # just go ahead
            self.__do_retrieve()

    def __do_retrieve(self, widget=None, response=Gtk.ResponseType.YES):
        if widget:
            widget.destroy()

        if response == Gtk.ResponseType.YES:
            threading.Thread(target=self.task_sync, args=(False,True)).start()

    def __do_send(self, widget):
        threading.Thread(target=self.task_sync, args=(True,False)).start()

    def __do_sync(self, widget):
        threading.Thread(target=self.task_sync, args=(True,True)).start()

    def task_sync(self, send, retrieve):
        self.allow_buttons(False)

        try:
            if send:
                self.engine.list_upload()
            if retrieve:
                self.engine.list_download()

            GObject.idle_add(self._set_score_ranges)
            GObject.idle_add(self.build_all_lists)
        except utils.TrackmaError as e:
            self.error(e)
        except utils.TrackmaFatal as e:
            self.idle_restart()
            self.error("Fatal engine error: %s" % e)
            return

        self.status("Ready.")
        self.allow_buttons(True)

    def start_engine(self):
        threading.Thread(target=self.task_start_engine).start()

    def task_start_engine(self):
        if not self.engine.loaded:
            try:
                self.engine.start()
            except utils.TrackmaFatal as e:
                self.idle_restart()
                self.error("Fatal engine error: %s" % e)
                return

        Gdk.threads_enter()
        self.statusbox.handler_block(self.statusbox_handler)
        self._clear_gui()
        self._set_score_ranges()
        self._create_lists()
        self.build_all_lists()

        # Clear and build API and mediatypes menus
        for i in self.mb_mediatype_menu.get_children():
            self.mb_mediatype_menu.remove(i)

        for mediatype in self.engine.api_info['supported_mediatypes']:
            item = Gtk.RadioMenuItem(label=mediatype)
            if mediatype == self.engine.api_info['mediatype']:
                item.set_active(True)
            item.connect("activate", self.__do_reload, None, mediatype)
            self.mb_mediatype_menu.append(item)
            item.show()

        self.statusbox.handler_unblock(self.statusbox_handler)
        Gdk.threads_leave()

        self.status("Ready.")
        self.allow_buttons(True)

    def task_reload(self, account, mediatype):
        try:
            self.engine.reload(account, mediatype)
        except utils.TrackmaError as e:
            self.error(e)
        except utils.TrackmaFatal as e:
            print("Fatal engine error: %s" % e)
            self.idle_restart()
            self.error("Fatal engine error: %s" % e)
            return

        if account:
            self.account = account

        # Refresh the GUI
        self.task_start_engine()

    def select_show(self, widget, page=None, page_num=None):
        page = page_num

        if page is None:
            page = self.notebook.get_current_page()

        selection = self.notebook.get_nth_page(page).get_child().get_selection()

        (tree_model, tree_iter) = selection.get_selected()
        if not tree_iter:
            self.allow_buttons_push(False, lists_too=False)
            return

        try:
            self.selected_show = int(tree_model.get(tree_iter, 0)[0])
        except ValueError:
            self.selected_show = tree_model.get(tree_iter, 0)[0]

        self.allow_buttons_push(True, lists_too=False)

        show = self.engine.get_show_info(self.selected_show)

        # Block handlers
        self.statusbox.handler_block(self.statusbox_handler)

        if self.image_thread is not None:
            self.image_thread.cancel()

        self.show_title.set_text('<span size="14000"><b>{0}</b></span>'.format(html.escape(show['title'])))
        self.show_title.set_use_markup(True)

        # Episode selector
        self.show_ep_button.set_label(str(show['my_progress']))
        self._hide_episode_entry()

        # Status selector
        for i in self.statusmodel:
            if str(i[0]) == str(show['my_status']):
                self.statusbox.set_active_iter(i.iter)
                break

        # Score selector
        self.show_score.set_value(show['my_score'])

        # Image
        if show.get('image_thumb') or show.get('image'):
            utils.make_dir(utils.to_cache_path())
            filename = utils.to_cache_path("%s_%s_%s.jpg" % (self.engine.api_info['shortname'], self.engine.api_info['mediatype'], show['id']))

            if os.path.isfile(filename):
                self.show_image.image_show(filename)
            else:
                if imaging_available:
                    self.show_image.pholder_show('Loading...')
                    self.image_thread = ImageTask(self.show_image, show.get('image_thumb') or show['image'], filename, (100, 149))
                    self.image_thread.start()
                else:
                    self.show_image.pholder_show("PIL library\nnot available")
        else:
            self.show_image.pholder_show("No Image")


        # Unblock handlers
        self.statusbox.handler_unblock(self.statusbox_handler)

    def _set_score_ranges(self):
        self.score_decimal_places = 0
        if isinstance( self.engine.mediainfo['score_step'], float ):
            self.score_decimal_places = len(str(self.engine.mediainfo['score_step']).split('.')[1])

        self.show_score.set_value(0)
        self.show_score.set_digits(self.score_decimal_places)
        self.show_score.set_range(0, self.engine.mediainfo['score_max'])
        self.show_score.get_adjustment().set_step_increment(self.engine.mediainfo['score_step'])

        for view in self.show_lists.values():
            view.decimals = self.score_decimal_places

    def build_all_lists(self):
        for status in self.show_lists.keys():
            self.build_list(status)

    def build_list(self, status):
        widget = self.show_lists[status]
        widget.append_start()

        if status == self.engine.mediainfo['status_start']:
            library = self.engine.library()
            for show in self.engine.filter_list(widget.status_filter):
                widget.append(show, self.engine.altname(show['id']), library.get(show['id']))
        else:
            for show in self.engine.filter_list(widget.status_filter):
                widget.append(show, self.engine.altname(show['id']))

        widget.append_finish()

    def on_about(self, widget):
        about = Gtk.AboutDialog()
        about.set_program_name("Trackma-gtk")
        about.set_version(utils.VERSION)
        about.set_comments("Trackma is an open source client for media tracking websites.")
        about.set_website("http://github.com/z411/trackma")
        about.set_copyright("Thanks to all contributors. See AUTHORS file.\n(c) z411 - Icon by shuuichi")
        about.run()
        about.destroy()

    def message_handler(self, classname, msgtype, msg):
        # Thread safe
        #print("%s: %s" % (classname, msg))
        if msgtype == messenger.TYPE_WARN:
            GObject.idle_add(self.status_push, "%s warning: %s" % (classname, msg))
        elif msgtype != messenger.TYPE_DEBUG:
            GObject.idle_add(self.status_push, "%s: %s" % (classname, msg))
        elif self.debug:
            print('[D] {}: {}'.format(classname, msg))

    def error(self, msg, icon=Gtk.MessageType.ERROR):
        # Thread safe
        GObject.idle_add(self.error_push, msg, icon)

    def error_push(self, msg, icon=Gtk.MessageType.ERROR):
        dialog = Gtk.MessageDialog(self.main_window, Gtk.DialogFlags.MODAL, icon, Gtk.ButtonsType.OK, str(msg))
        dialog.show_all()
        dialog.connect("response", self.modal_close)
        print('Error: {}'.format(msg))

    def modal_close(self, widget, response_id):
        widget.destroy()

    def status(self, msg):
        # Thread safe
        GObject.idle_add(self.status_push, msg)

    def status_push(self, msg):
        print(msg)
        self.statusbar.push(0, msg)

    def allow_buttons(self, boolean):
        # Thread safe
        GObject.idle_add(self.allow_buttons_push, boolean)

    def allow_buttons_push(self, boolean, lists_too=True):
        if lists_too:
            for widget in self.show_lists.values():
                widget.set_sensitive(boolean)

        if self.selected_show or not boolean:
            if self.engine.mediainfo['can_play']:
                self.play_next_button.set_sensitive(boolean)
                self.mb_play.set_sensitive(boolean)

            if self.engine.mediainfo['can_update']:
                self.show_ep_button.set_sensitive(boolean)
                self.show_ep_num.set_sensitive(boolean)
                self.add_epp_button.set_sensitive(boolean)
                self.rem_epp_button.set_sensitive(boolean)

            self.scoreset_button.set_sensitive(boolean)
            self.show_score.set_sensitive(boolean)
            self.statusbox.set_sensitive(boolean)
            self.mb_copy.set_sensitive(boolean)
            self.mb_delete.set_sensitive(boolean)
            self.mb_alt_title.set_sensitive(boolean)
            self.mb_info.set_sensitive(boolean)
            self.mb_web.set_sensitive(boolean)
            self.mb_folder.set_sensitive(boolean)

    def __do_copytoclip(self, widget):
        # Copy selected show title to clipboard
        show = self.engine.get_show_info(self.selected_show)

        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(show['title'], -1)

        self.status('Title copied to clipboard.')

    def __do_altname(self,widget):
        show = self.engine.get_show_info(self.selected_show)
        current_altname = self.engine.altname(self.selected_show)

        dialog = Gtk.MessageDialog(
            None,
            Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            Gtk.MessageType.QUESTION,
            Gtk.ButtonsType.OK_CANCEL,
            None)
        dialog.set_markup('Set the <b>alternate title</b> for the show.')
        entry = Gtk.Entry()
        entry.set_text(current_altname)
        entry.connect("activate", self.altname_response, dialog, Gtk.ResponseType.OK)
        hbox = Gtk.HBox()
        hbox.pack_start(Gtk.Label("Alternate Title:"), False, 5, 5)
        hbox.pack_end(entry, True, True, 0)
        dialog.format_secondary_markup("Use this if the tracker is unable to find this show. Leave blank to disable.")
        dialog.vbox.pack_end(hbox, True, True, 0)
        dialog.show_all()
        retval = dialog.run()

        if retval == Gtk.ResponseType.OK:
            text = entry.get_text()
            self.engine.altname(self.selected_show, text)
            self.changed_show_title(show, text)

        dialog.destroy()

    def do_containingFolder(self, widget):

        #get needed show info
        show = self.engine.get_show_info(self.selected_show)
        try:
            filename = self.engine.get_episode_path(show, 1)
            with open(os.devnull, 'wb') as DEVNULL:
                subprocess.Popen(["/usr/bin/xdg-open", os.path.dirname(filename)],
                                 stdout=DEVNULL,
                                 stderr=DEVNULL)
        except OSError:
            # xdg-open failed.
            raise utils.EngineError("Could not open folder.")

        except utils.EngineError:
            # Show not in library.
            self.error("No folder found.")

    def altname_response(self, entry, dialog, response):
        dialog.response(response)

    def __do_web(self, widget):
        show = self.engine.get_show_info(self.selected_show)
        if show['url']:
            Gtk.show_uri(None, show['url'], Gdk.CURRENT_TIME)

    def _build_episode_menu(self, show):
        total = show['total'] or utils.estimate_aired_episodes(show) or 0

        menu_eps = Gtk.Menu()
        for i in range(1, total + 1):
            mb_playep = Gtk.CheckMenuItem(str(i))
            if i <= show['my_progress']:
                mb_playep.set_active(True)
            mb_playep.connect("activate", self.__do_play, False, i)
            menu_eps.append(mb_playep)

        return menu_eps

    def showview_context_menu(self, treeview, event):
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            pthinfo = treeview.get_path_at_pos(x, y)
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor(path, col, 0)
                show = self.engine.get_show_info(self.selected_show)

                menu = Gtk.Menu()
                mb_play = Gtk.ImageMenuItem('Play Next', Gtk.Image.new_from_icon_name(Gtk.STOCK_MEDIA_PLAY, 0))
                mb_play.connect("activate", self.__do_play, True)
                mb_info = Gtk.MenuItem("Show details...")
                mb_info.connect("activate", self.__do_info)
                mb_web = Gtk.MenuItem("Open web site")
                mb_web.connect("activate", self.__do_web)
                mb_folder = Gtk.MenuItem("Open containing folder")
                mb_folder.connect("activate", self.do_containingFolder)
                mb_copy = Gtk.MenuItem("Copy title to clipboard")
                mb_copy.connect("activate", self.__do_copytoclip)
                mb_alt_title = Gtk.MenuItem("Set alternate title...")
                mb_alt_title.connect("activate", self.__do_altname)
                mb_delete = Gtk.ImageMenuItem('Delete', Gtk.Image.new_from_icon_name(Gtk.STOCK_DELETE, 0))
                mb_delete.connect("activate", self.__do_delete)

                menu.append(mb_play)

                menu_eps = self._build_episode_menu(show)

                mb_playep = Gtk.MenuItem("Play episode")
                mb_playep.set_submenu(menu_eps)
                menu.append(mb_playep)

                menu.append(mb_info)
                menu.append(mb_web)
                menu.append(mb_folder)
                menu.append(Gtk.SeparatorMenuItem())
                menu.append(mb_copy)
                menu.append(mb_alt_title)
                menu.append(Gtk.SeparatorMenuItem())
                menu.append(mb_delete)

                menu.show_all()
                menu.popup(None, None, None, None, event.button, event.time)

