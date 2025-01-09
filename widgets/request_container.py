import logging
from typing import Tuple, List, Dict, Optional

from gi.repository import Gtk, GtkSource

from models import RequestTreeNode, RequestModel
from widgets.param_table import ParamTable
from utils import language_map, content_type_map, content_type_map_reverse

log = logging.getLogger(__name__)


class RequestContainer:
    def __init__(self, request_editor):
        self.request_editor = request_editor
        self.request_model: Optional[RequestModel] = None

        builder = Gtk.Builder().new_from_file('ui/RequestContainer.glade')

        self.request_notebook: Gtk.Notebook = builder.get_object(
            'requestNotebook')
        self.lang_manager = GtkSource.LanguageManager()

        self.body_notebook: Gtk.Notebook = builder.get_object(
            'requestTypeNotebook')
        self.body_notebook.connect('switch-page',
                                   self._on_body_notebook_page_switched)

        self._init_param_table()
        self._init_header_table()
        self._init_body_text(builder)
        self._init_request_type_popover(builder)
        self._init_body_form_data_table()
        self._init_body_form_urlencoded_table()

        self.request_notebook.set_current_page(0)

    def _init_param_table(self):
        self.param_table = ParamTable()
        self.request_notebook.insert_page(self.param_table,
                                          Gtk.Label(label='Params'), 0)
        self.param_table.connect('changed', self._on_param_table_changed)

    def _init_header_table(self):
        self.header_table = ParamTable()
        self.request_notebook.insert_page(self.header_table,
                                          Gtk.Label(label='Headers'), 1)
        self.header_table.connect('changed', self._on_header_table_changed)

    def _init_body_text(self, builder):
        self.body_text: GtkSource.View = builder.get_object('requestText')
        self.body_text_buffer = self.body_text.get_buffer()
        self.body_text_buffer.connect('changed',
                                          self._on_body_text_changed)

        style_manager = GtkSource.StyleSchemeManager()
        scheme: GtkSource.StyleScheme = style_manager.get_scheme('kate')
        self.body_text_buffer.set_style_scheme(scheme)

        # Set based on type of request
        lang = self.lang_manager.get_language('text')
        self.body_text_buffer.set_language(lang)

    def _init_request_type_popover(self, builder):
        self.request_type_popover: Gtk.Popover = builder.get_object(
            'requestTypePopover')
        self.request_type_popover_tree_view: Gtk.TreeView = builder.get_object(
            'requestTypePopoverTreeView')
        self.request_type_popover_tree_view_store: Gtk.ListStore = builder.get_object(
            'requestTypePopoverStore')
        self.request_type_popover_tree_view.connect('row-activated',
                                                    self._on_popover_row_activated)

    def _init_body_form_data_table(self):
        self.body_form_data_table = ParamTable()
        self.body_notebook.insert_page(self.body_form_data_table,
                                       Gtk.Label('Form Data'), 2)
        self.body_form_data_table.connect('changed',
                                          self._on_body_form_data_table_changed)

    def _init_body_form_urlencoded_table(self):
        self.body_form_urlencoded_table = ParamTable()
        self.body_notebook.insert_page(self.body_form_urlencoded_table,
                                       Gtk.Label('Form Url-Encoded'), 3)
        self.body_form_urlencoded_table.connect('changed',
                                                self._on_body_form_urlencoded_table_changed)

    def _on_param_table_changed(self, widget):
        params = self.param_table.get_values()
        log.debug('Change request params to %s', params)
        self.request_model.params = params

    def _on_header_table_changed(self, widget):
        headers = self.header_table.get_values()
        log.debug('Change request headers to %s', headers)
        self.request_model.headers = headers

    def _on_body_text_changed(self, widget):
        start, end = self.body_text_buffer.get_bounds()
        body_text = self.body_text_buffer.get_text(start, end, True)
        log.debug('Change request body raw text to %s', body_text)
        self.request_model.body_text = body_text

    def _on_body_form_data_table_changed(self, widget):
        body_form_data = self.body_form_data_table.get_values()
        log.debug('Change request body form data to %s', body_form_data)
        self.request_model.body_form_data = body_form_data

    def _on_body_form_urlencoded_table_changed(self, widget):
        body_form_urlencoded = self.body_form_urlencoded_table.get_values()
        log.debug('Change request body form urlencoded to %s',
                  body_form_urlencoded)
        self.request_model.body_form_urlencoded = body_form_urlencoded

    def _on_body_notebook_page_switched(self, notebook: Gtk.Notebook,
                                        page: Gtk.Widget, page_num: int):
        log.debug('Change body notebook page to %s', page_num)
        ct_func = {
            1: self._get_active_content_type,
            2: lambda: 'multipart/form-data',
            3: lambda: 'application/x-www-form-urlencoded',
        }.get(page_num)

        content_type = ct_func() if ct_func else ''
        if self.request_model.content_type == content_type:
            return

        self.request_model.content_type = content_type
        if not content_type:
            self.header_table.delete_row_by_key('content-type')
        else:
            self.header_table.prepend_or_update_row_by_key(
                ('Content-Type', content_type, ''))

    def _get_active_content_type(self):
        sel: Gtk.TreeSelection = self.request_type_popover_tree_view.get_selection()
        model, paths = sel.get_selected_rows()
        if paths:
            type_id = model[paths[0]][1]
            return content_type_map[type_id]

        return 'text/plain'

    def _on_popover_row_activated(self, tree: Gtk.TreeView, path: Gtk.TreePath,
                                  col: Gtk.TreeViewColumn):
        store = self.request_type_popover_tree_view_store
        it = store.get_iter(path)
        type_name = store.get_value(it, 0)
        type_id = store.get_value(it, 1)
        log.debug('Selected request type %s - %s', type_id, type_name)

        lang = self.lang_manager.get_language(
            language_map.get(type_id, 'text'))
        self.body_text_buffer.set_language(lang)

        content_type = content_type_map[type_id]
        self.request_model.content_type = content_type
        self.header_table.prepend_or_update_row_by_key(
            ('Content-Type', content_type, ''))

        self.request_type_popover.hide()
        self.body_notebook.set_current_page(1)

    def set_request_model(self, request_model: RequestModel):
        self.request_model = request_model
        self.param_table.set_values(request_model.params)
        self.header_table.set_values(request_model.headers)
        self.body_text_buffer.set_text(request_model.body_text, -1)
        self.body_form_data_table.set_values(request_model.body_form_data)
        self.body_form_urlencoded_table.set_values(
            request_model.body_form_urlencoded)

        self._update_body_notebook_page(request_model.content_type)

    def _update_body_notebook_page(self, content_type):
        body_notebook_page = 0
        if content_type in content_type_map_reverse:
            body_notebook_page = 1
        elif content_type == 'multipart/form-data':
            body_notebook_page = 2
        elif content_type == 'application/x-www-form-urlencoded':
            body_notebook_page = 3
        self.body_notebook.set_current_page(body_notebook_page)
