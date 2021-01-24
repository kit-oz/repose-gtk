import logging
from typing import List, Tuple, Dict, Optional

import requests
from gi.repository import Gtk, GLib

from models import RequestTreeNode
from pool import TPE
from widgets.request_container import RequestContainer
from widgets.response_container import ResponseContainer

log = logging.getLogger(__name__)


@Gtk.Template.from_file('ui/RequestEditor.glade')
class RequestEditor(Gtk.Box):
    __gtype_name__ = 'RequestEditor'

    request_method_combo: Gtk.ComboBox = Gtk.Template.Child()
    request_method_combo_store: Gtk.ListStore = Gtk.Template.Child()
    request_name_entry: Gtk.Entry = Gtk.Template.Child()
    url_entry: Gtk.Entry = Gtk.Template.Child()
    send_button: Gtk.Button = Gtk.Template.Child()
    save_button: Gtk.Button = Gtk.Template.Child()
    request_response_box: Gtk.Box = Gtk.Template.Child()

    def __init__(self, main_window):
        super(RequestEditor, self).__init__()

        self.main_window = main_window
        self.active_request: Optional[RequestTreeNode] = None
        self.last_response: Optional[requests.Response] = None

        self.request_container = RequestContainer(self)
        self.request_response_box.add(self.request_container.request_notebook)

        self.response_container = ResponseContainer(self)
        self.request_response_box.add(self.response_container)

        self.url_entry.connect('changed', self._on_url_change)
        self.request_method_combo.connect('changed', self._on_method_change)

    @Gtk.Template.Callback('on_request_name_changed')
    def _on_request_name_changed(self, entry: Gtk.Entry):
        self.active_request = self.get_request()

        if self.active_request.collection_pk:
            self.main_window.request_list.update_request(self.active_request)

    def get_request(self) -> RequestTreeNode:
        self.request_container.get_request(self.active_request)
        node = self.active_request
        req = node.request
        req.url = self.url_entry.get_text()
        req.method = self.get_method()
        req.name = self.request_name_entry.get_text()
        return node

    def set_request(self, node: RequestTreeNode):
        self.active_request = node
        req = node.request
        self.url_entry.set_text(req.url)
        self.set_method(req.method)
        self.request_name_entry.set_text(req.name)
        self.request_container.set_request(node)

    def set_method(self, method: str):
        self.request_method_combo.set_active_id(method)

    def get_method(self) -> str:
        return self.request_method_combo.get_active_id()

    @Gtk.Template.Callback('on_save_pressed')
    def _on_save_pressed(self, btn):
        log.info('Save pressed')

    @Gtk.Template.Callback('on_send_pressed')
    def _on_send_pressed(self, btn):
        url = self.active_request.request.url
        meth = self.get_method()
        self.response_container.set_response_spinner_active(True)

        params = self.request_container.get_params()
        headers = self.request_container.get_headers()
        body = self.request_container.get_body()

        TPE.submit(self.do_request, meth, url, params, headers, body)
        log.info('Creating request to %s - %s', meth, url)

    def do_request(self, method: str, url: str, params: List[Tuple[str, str]], headers: Dict[str, str], data=None):
        try:
            if type(data) is str:
                data = data.encode('utf-8')

            res = requests.request(method, url, params=params, headers=headers, data=data)
            # TODO: Load all the data into custom object before sending it back to UI thread
            GLib.idle_add(self.handle_request_finished, res)
        except Exception as e:
            log.error('Error occurred while sending request %s', e)
            GLib.idle_add(self.response_container.handle_request_finished_exceptionally, e)

    def handle_request_finished(self, response: requests.Response):
        log.info('Got %s response from %s', response.status_code, self.url_entry.get_text())
        self.last_response = response
        self.response_container.handle_request_finished(response)

    def _on_url_change(self, entry: Gtk.Entry):
        log.debug('Change request url to %s', entry.get_text())
        self.active_request.request.url = entry.get_text()

    def _on_method_change(self, entry: Gtk.ComboBox):
        log.debug('Change request method to %s', self.active_request.request.method)
        self.active_request.request.method = self.get_method()
