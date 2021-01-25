import requests

from uuid import uuid1
from typing import Dict, List, Tuple, Optional

from utils import content_type_map_reverse


class MainModel:
    def __init__(self):
        self.requests: Dict[str, RequestTreeNode] = {}


class RequestModel:
    def __init__(self,
                 url: str = '',
                 method: str = 'GET',
                 name: str = '',
                 params: List[Tuple[str, str, str]] = None,
                 headers: List[Tuple[str, str, str]] = None,
                 content_type: str = '',
                 body_text: str = '',
                 body_form_data: List[Tuple[str, str, str]] = None,
                 body_form_urlencoded: List[Tuple[str, str, str]] = None,

                 saved: bool = False,
                 ):
        self.name = name

        self.method = method
        self.url = url

        self.params = params or [('', '', '')]
        self.headers = headers or [('', '', '')]

        self.content_type = content_type

        self.body_text = body_text
        self.body_form_data = body_form_data or [('', '', '')]
        self.body_form_urlencoded = body_form_urlencoded or [('', '', '')]

        self.saved = saved

        self.request: Optional[requests.Request] = None
        self.response: Optional[requests.Response] = None

    def set_headers(self, headers):
        self.headers = headers

    def do_request(self):
        params = self._get_params()
        headers = self._get_headers()
        body = self._get_body()

        try:
            self.request = requests.request(self.method,
                                            self.url,
                                            params=params,
                                            headers=headers,
                                            data=body)
            print('DONE')
        except Exception as e:
            print('ERROR', e)

    def _get_params(self) -> List[Tuple[str, str]]:
        return [(k, v) for k, v, _ in self.params if k]

    def _get_headers(self) -> Dict[str, str]:
        return dict([(k, v) for k, v, _ in self.headers if k])

    def _get_body(self):
        if self.content_type in content_type_map_reverse:
            return self.body_text

        form_body = {
            'multipart/form-data': self._get_form_data,
            'application/x-www-form-urlencoded': self._get_form_urlencoded,
        }
        if self.content_type in form_body:
            return form_body[self.content_type]()

        return ''

    def _get_form_data(self):
        return [(k, v) for k, v, _ in self.body_form_data]

    def _get_form_urlencoded(self):
        return [(k, v) for k, v, _ in self.body_form_urlencoded]


class FolderModel:
    def __init__(self, name: str):
        self.name = name


class RequestTreeNode:
    def __init__(self,
                 parent_pk: str = None,
                 collection_pk: str = None,
                 pk: str = None,
                 parent=None,
                 collection=None,
                 request: Optional[RequestModel] = None,
                 folder: Optional[FolderModel] = None
                 ):
        assert request or folder

        self.pk = pk or str(uuid1())
        self.parent_pk = parent_pk
        self.parent = parent
        self.collection_pk = collection.pk if collection else collection_pk
        self.collection = collection
        self.folder = folder
        self.request = request
        self.children = []

    def is_folder(self) -> bool:
        return self.folder is not None

    def add_child(self, node):
        assert self.is_folder()
        node.parent = self
        node.parent_pk = self.pk
        self.children.append(node)

    def remove_request(self, node):
        self.children.remove(node)


class CollectionModel:
    def __init__(self, name: str, nodes: List[RequestTreeNode] = None,
                 pk: str = None):
        self.pk = pk or str(uuid1())
        self.name = name
        self.nodes = nodes or []

    def add_node(self, node: RequestTreeNode):
        node.collection = self
        node.collection_pk = self.pk
        self.nodes.append(node)
