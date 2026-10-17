"""The document tree (lhtml.tree, prototype of step N5): its shape, its
places, the crossings, the tags. Its HTML is compared with lhtml.run by the
whole suite run with LHTML_TREE=1, the corpus and a fuzzer."""
import warnings

import pytest

import lhtml
from lhtml import tree


def kinds(node, depth=0):
    """The tree as indented kinds, for a readable comparison."""
    lines = ['  ' * depth + node.kind]
    for child in node.children:
        lines += kinds(child, depth + 1)
    return lines


def quiet(fn, *args, **options):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        result = fn(*args, **options)
    return result, [str(w.message) for w in caught]


class TestShape:

    def test_nodes_nest_what_the_passes_wrote_flat(self):
        document = tree.parse('= Title\n* a **b**\n** c\ndiv::[x:y]\n`code` \\(m\\) <b>raw</b>\n::\n')
        assert kinds(document) == [
            'Document', '  Heading', '    Text', '  Text',
            '  List', '    Item', '      Text', '      Strong', '        Text', '      Text',
            '    Item', '      List', '        Item', '          Text',
            '  Element', '    Text', '    InlineCode', '    Text', '    Math', '    Text',
            '    Raw', '    Text', '    Raw', '    Text', '  Text']

    def test_an_element_keeps_its_groups_and_value_and_a_code_block_its_language(self):
        document = tree.parse('img::a.png(.wide)[width:3px]\ncode::[python]\nx = 1\ncode::[-]\n')
        image = next(n for n in document.walk() if n.kind == 'Element')
        assert (image.name, image.value, image.groups['()'], image.groups['[]'], image.closed) == \
            ('img', 'a.png', '.wide', 'width:3px', 'void')
        code = next(n for n in document.walk() if n.kind == 'Code')
        assert (code.language, code.body) == ('python', '\nx = 1\n')

    def test_every_node_is_placed_in_the_source(self):
        text = 'a\n\\(x\ny\\)\n* item **b** div::[c] x ::\n'
        for node in tree.parse(text).walk():
            if node.kind in ('Text', 'Strong', 'Math', 'Item'):
                start, end = node.span
                line = text.count('\n', 0, start) + 1
                assert (node.line, node.column) == (line, start - text.rfind('\n', 0, start)), node
        strong = next(n for n in tree.parse(text).walk() if n.kind == 'Strong')
        assert text[strong.span[0]:strong.span[1]] == '**b**'
        element = next(n for n in tree.parse(text).walk() if n.kind == 'Element')
        assert text[element.span[0]:element.span[1]] == 'div::[c] x ::'


class TestSameHtml:

    @pytest.mark.parametrize('text', [
        '= T\n* a\n** b\n* c **d** div::[x:y] in ::\nend',
        'div::(.c)\n= H\n* i\n::\n',
        'a `c::d` \\(x\\) <b>x</b> img::a.png link::u[l]\n',
        '* last line without its line break',
        '_tiny::link::http://a.b/c[lspan::[a]link::u[**b**]\t ::nl',     # an unknown name is skipped whole
        '**`x::y`link::u[**b**]<div>::nl',                               # a bold closed in a label
        'link::http://a.b/c[l\n== box::(]x',                             # a heading opened in a label
    ])
    def test_the_html_of_run(self, text):
        macros = {'tiny': {'tag': 'span', 'class': 'tiny'}, 'box': {'class': 'box'}}
        assert quiet(tree.run, text, {'macros': macros}) == quiet(lhtml.run, text, {'macros': macros})


class TestCrossings:

    def test_an_element_opened_in_an_item_is_closed_there(self):
        html, said = quiet(tree.run, '* a span::[c] b\n* d ::\n')
        assert html == '<ul>\n<li>\na <span style="c"> b\n</span></li>\n<li>\nd ::\n</li>\n</ul>\n'
        assert any('closed at the end of the item it is opened in' in w for w in said)
        assert any('this :: closes nothing' in w for w in said)

    def test_a_close_inside_a_later_item_closes_nothing(self):
        html, said = quiet(tree.run, 'div::[x]\n* a ::\n')
        assert html == '<div style="x">\n<ul>\n<li>\na ::\n</li>\n</ul>\n</div>'
        assert any('its :: is inside a heading, list item, bold or italic' in w for w in said)


class TestTags:

    def test_a_tag_declares_whether_it_holds_what_follows(self):
        alert = tree.Tag(container=True, render=lambda element, children, context:
                         f'<div class="alert">{children}</div>')
        html, _ = quiet(tree.run, 'alert:: warning **here** ::\n', tags={'alert': alert})
        assert html == '<div class="alert"> warning <strong>here</strong> </div>\n'
        badge = tree.Tag(render=lambda element, children, context: f'<b>{element["text"]}</b>')
        assert quiet(tree.run, 'badge::new and more\n', tags={'badge': badge})[0] == '<b>new</b> and more\n'

    def test_a_macro_is_a_tag_and_warns_where_it_is(self):
        macros = {'gap': {'class': 'gap', 'variant': ['s', 'l'], 'empty': True}}
        document, said = quiet(tree.parse, 'x\ngap::zz\n', macros=macros)
        assert said == ["gap::zz: unknown variant (expected one of s, l) near 'gap::zz'"]
        assert (document.problems[0].line, document.problems[0].column) == (2, 1)

    def test_an_unknown_name_is_text(self):
        document = tree.parse('std::vector<int> v;\n')
        assert [n.kind for n in document.walk()] == ['Document', 'Text', 'Raw', 'Text']
