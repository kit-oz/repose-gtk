import json
import logging
from io import StringIO
from typing import Optional

import jsonpath_rw
import requests
from gi.repository import Gtk, GtkSource, WebKit2, GObject
from lxml import etree, html

from models import RequestModel
from utils import get_content_type, timedelta_fmt, format_response_size, \
    get_language_for_mime_type

log = logging.getLogger(__name__)


@Gtk.Template.from_file('ui/ResponseContainer.glade')
class ResponseContainer(Gtk.Overlay):
    __gtype_name__ = 'ResponseContainer'

    response_notebook: Gtk.Notebook = Gtk.Template.Child()
    response_text_pretty: GtkSource.View = Gtk.Template.Child()
    response_text_raw: Gtk.TextView = Gtk.Template.Child()
    response_loading_spinner: Gtk.Spinner = Gtk.Template.Child()
    response_headers_text: Gtk.TextView = Gtk.Template.Child()
    response_status_label: Gtk.Label = Gtk.Template.Child()
    response_time_label: Gtk.Label = Gtk.Template.Child()
    response_size_label: Gtk.Label = Gtk.Template.Child()

    response_filter_search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    response_filter_search_bar: Gtk.SearchBar = Gtk.Template.Child()
    response_webview_scroll_window: Gtk.ScrolledWindow = Gtk.Template.Child()

    response_menu_popover: Gtk.Popover = Gtk.Template.Child()
    response_menu_toggle_filter: Gtk.MenuItem = Gtk.Template.Child()

    def __init__(self, request_editor):
        super(ResponseContainer, self).__init__()

        self.request_model: Optional[RequestModel] = None
        self.response: Optional[requests.Response] = None
        self.lang_manager = GtkSource.LanguageManager()
        self.handler_id = None

        style_manager = GtkSource.StyleSchemeManager()
        # scheme: GtkSource.StyleScheme = mgr.get_scheme('classic')
        scheme: GtkSource.StyleScheme = style_manager.get_scheme('kate')
        self.response_text_pretty.get_buffer().set_style_scheme(scheme)

        # TODO: Lazy load the web view
        self.response_webview: WebKit2.WebView = WebKit2.WebView() \
            .new_with_context(WebKit2.WebContext().new_ephemeral())
        self.response_webview_scroll_window.add(self.response_webview)

    @Gtk.Template.Callback('on_response_filter_changed')
    def _on_response_filter_changed(self, entry: Gtk.SearchEntry):
        filter_text = entry.get_text()
        if filter_text == '':
            self._set_response_text()

        ct = get_content_type(self.response)
        try:
            if ct == 'application/json':
                path_expr = jsonpath_rw.parse(filter_text)
                j = self.response.json()
                match_text = json.dumps(
                    [match.value for match in path_expr.find(j)],
                    indent=4) or 'No matches found'
                self.response_text_pretty.get_buffer().set_text(match_text)
            elif ct in {'text/xml', 'application/xml'}:
                root = etree.fromstring(self.response.text)
                matches = root.xpath(filter_text)
                matches_root = etree.Element('matches')
                for m in matches:
                    matches_root.append(m)

                matches_html = etree.tostring(matches_root, encoding='unicode',
                                              pretty_print=True)
                self.response_text_pretty.get_buffer().set_text(matches_html)
            elif ct == 'text/html':
                root = html.fromstring(self.response.text)
                matches = root.xpath(filter_text)
                matches_root = etree.Element('matches')
                for m in matches:
                    matches_root.append(m)

                matches_html = etree.tostring(matches_root, encoding='unicode',
                                              pretty_print=True)
                self.response_text_pretty.get_buffer().set_text(matches_html)
            else:
                log.warning(
                    'Got unexpected content type %s when filtering response.',
                    ct)
        except Exception as e:
            log.debug('Failed to filter response json %s', e)

    def _get_formatted_response_text(self):
        if not self.response:
            return ""

        ct = get_content_type(self.response)
        try:
            txt = GObject.markup_escape_text(self.response.text)
            if ct == 'application/json':
                j = self.response.json()
                txt = json.dumps(j, indent=2)
            elif ct in {'text/xml', 'application/xml'}:
                root = etree.fromstring(txt)
                txt = etree.tostring(root, encoding='unicode',
                                     pretty_print=True)
            elif ct == 'text/html':  # TODO: Add css path filters
                root = html.fromstring(txt)
                txt = etree.tostring(root, encoding='unicode',
                                     pretty_print=True)
            elif not txt:
                txt = 'Empty Response'
        except Exception as e:
            log.warning('Failed to parse %s response: %s', ct, e)
            txt = 'Failed to parse response.'

        return txt

    def _set_response_text_pretty(self):
        txt = self._get_formatted_response_text()
        self._highlight_syntax(txt)
        self.response_text_pretty.get_buffer().set_text(txt)

    def _set_response_text_raw(self):
        text = GObject.markup_escape_text(self.response.text) \
            if self.response else ""
        self.response_text_raw.get_buffer().set_text(text)

    def _set_headers(self):
        headers_markup = '\n'.join(
            [f'<b>{GObject.markup_escape_text(k)}</b>'
             f' → {GObject.markup_escape_text(v)}'
             for k, v in self.response.headers.items()]
        ) if self.response else ""

        buf: Gtk.TextBuffer = self.response_headers_text.get_buffer()
        start, end = buf.get_bounds()
        buf.delete(start, end)
        buf.insert_markup(buf.get_start_iter(), headers_markup, -1)

    def _set_status_label(self):
        status_markup = f'{self.response.status_code} {self.response.reason}' \
            if self.response else "-"
        if self.response and not self.response.ok:
            status_markup = f'<span foreground="red">{status_markup}</span>'
        self.response_status_label.set_markup(f'Status: {status_markup}')

    def _set_time_label(self):
        time = timedelta_fmt(self.response.elapsed) if self.response else "-"
        self.response_time_label.set_text(f'Time: {time}')

    def _set_size_label(self):
        size = format_response_size(self.response) if self.response else "-"
        self.response_size_label.set_text(f'Size: {size}')

    @Gtk.Template.Callback('populate_response_text_context_menu')
    def _populate_response_text_context_menu(self, view: Gtk.TextView,
                                             popup: Gtk.Widget):
        if type(popup) is not Gtk.Menu:
            return

        menu: Gtk.Menu = popup

        word_wrap_toggle: Gtk.MenuItem = Gtk.MenuItem().new_with_label(
            'Toggle word wrap')
        word_wrap_toggle.connect('activate', self._word_wrap_toggle_clicked)
        menu.append(word_wrap_toggle)

        ct = get_content_type(self.response)
        if self.response and ct in {'application/json', 'text/html',
                                    'text/xml', 'application/xml'}:
            show_filter_toggle: Gtk.MenuItem = Gtk.MenuItem().new_with_label(
                'Show response filter')
            show_filter_toggle.connect('activate',
                                       self._show_filter_toggle_clicked)
            menu.append(show_filter_toggle)

        menu.show_all()

    def _show_filter_toggle_clicked(self, btn):
        is_revealed = self.response_filter_search_bar.get_search_mode()
        self.response_filter_search_bar.set_search_mode(not is_revealed)

    def set_response_spinner_active(self, active: bool):
        if active:
            self.response_loading_spinner.start()
            self.reorder_overlay(self.response_loading_spinner, 1)
        else:
            self.response_loading_spinner.stop()
            self.reorder_overlay(self.response_loading_spinner, 0)

    def _set_response_webview(self):
        """Loads the webview, or show error message if webkit unavailable."""
        if (
                not self.response
                or not self.response.ok
                or self.response.request.method != 'GET'
                or get_content_type(self.response) != 'text/html'
        ):
            self.response_webview.load_html("")
            return

        # TODO: Enable running of javascript
        self.response_webview.load_html(self.response.text)

    def _word_wrap_toggle_clicked(self, btn):
        current = self.response_text_pretty.get_wrap_mode()
        new = Gtk.WrapMode.NONE if current != Gtk.WrapMode.NONE else Gtk.WrapMode.WORD
        self.response_text_pretty.set_wrap_mode(new)

    def handle_request_finished(self, request_model: RequestModel):
        self.response = request_model.response
        try:
            self.fill_response_info()
        finally:
            self.set_response_spinner_active(False)

    def fill_response_info(self):
        self._set_status_label()
        self._set_time_label()
        self._set_size_label()
        self._set_headers()
        self._set_response_text_pretty()
        self._set_response_text_raw()
        self._set_response_webview()

    def _highlight_syntax(self, txt: str):
        if not self.response:
            lang_id = 'text'
        else:
            lang_id = get_language_for_mime_type(
                get_content_type(self.response))
        buf: GtkSource.Buffer = self.response_text_pretty.get_buffer()
        if lang_id == 'html':
            lang_id = 'xml'  # Full HTML highlighting is very slow; it freezes the UI.

        # Disable highlighting for files with really long lines
        if any((True for line in StringIO(txt) if len(line) > 5000)):
            lang_id = 'text'

        lang = self.lang_manager.get_language(lang_id)
        current_lang: GtkSource.Language = buf.get_language()
        if not current_lang or current_lang.get_id() != lang_id:
            buf.set_language(lang)

    def handle_request_finished_exceptionally(self, ex: Exception):
        self.set_response_spinner_active(False)
        self.response_text_pretty.get_buffer().set_text(
            f'Error occurred while performing request: {ex}')
        self.response_notebook.set_current_page(1)  # Body page

    def set_request_model(self, request_model: RequestModel):
        if self.handler_id:
            self.request_model.disconnect(self.handler_id)

        self.request_model = request_model
        self.response = request_model.response
        self.fill_response_info()
        self.handler_id = self.request_model.connect(
            "request_finished",
            self.handle_request_finished
        )
