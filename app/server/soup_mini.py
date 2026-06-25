"""
迷你 HTML 解析器 — 仅使用 Python 标准库 html.parser
提供类似 BeautifulSoup 的 find/find_all/get_text 接口
"""

from html.parser import HTMLParser


class _Node:
    """HTML 节点"""
    __slots__ = ('tag', 'attrs', 'children', 'data')

    def __init__(self, tag=None, attrs=None, data=""):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.data = data

    def get_text(self):
        parts = []
        self._collect_text(parts)
        return ''.join(parts)

    def _collect_text(self, parts):
        if self.data:
            parts.append(self.data)
        for child in self.children:
            child._collect_text(parts)

    def get(self, key, default=''):
        val = self.attrs.get(key)
        return val if val is not None else default

    def find(self, name, attrs=None):
        if attrs is None:
            attrs = {}
        stack = list(self.children)
        while stack:
            node = stack.pop(0)
            if node.tag == name and self._match_attrs(node, attrs):
                return node
            stack.extend(node.children)
        return None

    def find_all(self, name, attrs=None):
        if attrs is None:
            attrs = {}
        result = []
        stack = list(self.children)
        while stack:
            node = stack.pop(0)
            if node.tag == name and self._match_attrs(node, attrs):
                result.append(node)
            stack.extend(node.children)
        return result

    @staticmethod
    def _match_attrs(node, attrs):
        for k, v in attrs.items():
            nv = node.attrs.get(k)
            if nv is None:
                return False
            if v is not None and nv != v:
                return False
        return True


class _HTMLTreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node('__root__')
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, dict(attrs))
        self._stack[-1].children.append(node)
        if tag not in ('br', 'hr', 'input', 'img', 'meta', 'link', 'area',
                       'base', 'col', 'embed', 'source', 'track', 'wbr'):
            self._stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].tag == tag:
                self._stack = self._stack[:i]
                break

    def handle_data(self, data):
        text = data.strip()
        if text:
            self._stack[-1].children.append(_Node(data=text))

    def handle_entityref(self, name):
        c = {'amp': '&', 'lt': '<', 'gt': '>', 'quot': '"', 'apos': "'"}.get(name, f'&{name};')
        self._stack[-1].children.append(_Node(data=c))

    def handle_charref(self, name):
        try:
            if name.startswith('x'):
                c = chr(int(name[1:], 16))
            else:
                c = chr(int(name))
            self._stack[-1].children.append(_Node(data=c))
        except (ValueError, OverflowError):
            pass


def from_string(html_text):
    if not html_text:
        return _Node()
    builder = _HTMLTreeBuilder()
    try:
        builder.feed(html_text)
        builder.close()
    except Exception:
        pass
    return builder.root
