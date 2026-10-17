"""The document tree (lhtml.parse, lhtml.render, which lhtml.run is): its
shape, its places, the crossings, the tags. Before it was the engine of run,
its HTML was compared with the text passes it replaced on this suite, the
corpus and 80 000 fuzzed documents (docs/design.md of the generator, N5);
the HTML of run is what the rest of the suite checks."""
import warnings

import pytest

import lhtml


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
        document = lhtml.parse('= Title\n* a **b**\n** c\ndiv::[x:y]\n`code` \\(m\\) <b>raw</b>\n::\n')
        assert kinds(document) == [
            'Document', '  Heading', '    Text', '  Text',
            '  List', '    Item', '      Text', '      Strong', '        Text', '      Text',
            '    Item', '      List', '        Item', '          Text',
            '  Element', '    Text', '    InlineCode', '    Text', '    Math', '    Text',
            '    Raw', '    Text', '    Raw', '    Text', '  Text']

    def test_an_element_keeps_its_groups_and_value_and_a_code_block_its_language(self):
        document = lhtml.parse('img::a.png(.wide)[width:3px]\ncode::[python]\nx = 1\ncode::[-]\n')
        image = next(n for n in document.walk() if n.kind == 'Element')
        assert (image.name, image.value, image.groups['()'], image.groups['[]'], image.closed) == \
            ('img', 'a.png', '.wide', 'width:3px', 'void')
        code = next(n for n in document.walk() if n.kind == 'Code')
        assert (code.language, code.body) == ('python', '\nx = 1\n')

    def test_every_node_is_placed_in_the_source(self):
        text = 'a\n\\(x\ny\\)\n* item **b** div::[c] x ::\n'
        for node in lhtml.parse(text).walk():
            if node.kind in ('Text', 'Strong', 'Math', 'Item'):
                start, end = node.span
                line = text.count('\n', 0, start) + 1
                assert (node.line, node.column) == (line, start - text.rfind('\n', 0, start)), node
        strong = next(n for n in lhtml.parse(text).walk() if n.kind == 'Strong')
        assert text[strong.span[0]:strong.span[1]] == '**b**'
        element = next(n for n in lhtml.parse(text).walk() if n.kind == 'Element')
        assert text[element.span[0]:element.span[1]] == 'div::[c] x ::'


class TestWhatThePassesDid:
    """Cases the fuzzer found while the tree was compared with the passes."""

    def test_an_unknown_name_is_skipped_whole(self):
        html, _ = quiet(lhtml.run, '_tiny::link::http://a.b/c[lspan::[a]link::u[**b**]\t ::nl',
                        {'macros': {'tiny': {'tag': 'span', 'class': 'tiny'}}})
        assert html == '_tiny::link::http://a.b/c[lspan::[a]link::u[**b**]\t <div style="height:1em;"></div>'

    def test_a_last_list_line_gets_its_line_break(self):
        assert quiet(lhtml.run, '* last')[0] == '<ul>\n<li>\nlast\n</li>\n</ul>\n'

    def test_the_markup_a_link_label_holds_is_written_once(self):
        html, _ = quiet(lhtml.run, '**x link::u[**b**] y')
        assert html == '<strong>x <a href="u"></strong>b**</a> y'
        html, _ = quiet(lhtml.run, 'link::http://a.b/c[l\n== box::(]x')
        assert html == '<a href="http://a.b/c">l\n<h2>box::(</a>x</h2>\n'


class TestCrossings:

    def test_an_element_opened_in_an_item_is_closed_there(self):
        html, said = quiet(lhtml.run, '* a span::[c] b\n* d ::\n')
        assert html == '<ul>\n<li>\na <span style="c"> b\n</span></li>\n<li>\nd ::\n</li>\n</ul>\n'
        assert any('closed at the end of the item it is opened in' in w for w in said)
        assert any('this :: closes nothing' in w for w in said)

    def test_a_close_inside_a_later_item_closes_nothing(self):
        html, said = quiet(lhtml.run, 'div::[x]\n* a ::\n')
        assert html == '<div style="x">\n<ul>\n<li>\na ::\n</li>\n</ul>\n</div>'
        assert any('its :: is inside a heading, list item, bold or italic' in w for w in said)


class TestTags:

    def test_a_tag_declares_whether_it_holds_what_follows(self):
        alert = lhtml.Tag(container=True, render=lambda element, children, context:
                         f'<div class="alert">{children}</div>')
        html, _ = quiet(lhtml.run, 'alert:: warning **here** ::\n', tags={'alert': alert})
        assert html == '<div class="alert"> warning <strong>here</strong> </div>\n'
        badge = lhtml.Tag(render=lambda element, children, context: f'<b>{element["text"]}</b>')
        assert quiet(lhtml.run, 'badge::new and more\n', tags={'badge': badge})[0] == '<b>new</b> and more\n'

    def test_a_macro_is_a_tag_and_warns_where_it_is(self):
        macros = {'gap': {'class': 'gap', 'variant': ['s', 'l'], 'empty': True}}
        document, said = quiet(lhtml.parse, 'x\ngap::zz\n', macros=macros)
        assert said == ["gap::zz: unknown variant (expected one of s, l) near 'gap::zz'"]
        assert (document.problems[0].line, document.problems[0].column) == (2, 1)

    def test_an_unknown_name_is_text(self):
        document = lhtml.parse('std::vector<int> v;\n')
        assert [n.kind for n in document.walk()] == ['Document', 'Text', 'Raw', 'Text']
