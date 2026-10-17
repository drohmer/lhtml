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



def problems(text, **options):
    document, said = quiet(lhtml.parse, text, **options)
    return [(p.line, p.column, str(p)) for p in document.problems]


class TestCrossings:

    def test_an_element_opened_in_an_item_is_closed_there(self):
        html, _ = quiet(lhtml.run, '* a span::[c] b\n* d ::\n')
        assert html == '<ul>\n<li>\na <span style="c"> b\n</span></li>\n<li>\nd ::\n</li>\n</ul>\n'
        (l1, c1, closed), (l2, c2, nothing) = problems('* a span::[c] b\n* d ::\n')
        assert 'span:: is closed at the end of the list item it is opened in' in closed
        assert (l1, c1) == (1, 5)
        assert 'this :: closes nothing: span:: was closed at the end of the list item' in nothing
        assert (l2, c2) == (2, 5)                     # at the ::, not at the element

    def test_a_close_inside_a_later_item_closes_nothing(self):
        html, _ = quiet(lhtml.run, 'div::[x]\n* a ::\n')
        assert html == '<div style="x">\n<ul>\n<li>\na ::\n</li>\n</ul>\n'
        said = problems('div::[x]\n* a ::\n')
        assert said[0][:2] == (1, 1) and 'div:: is never closed' in said[0][2]
        assert said[1][:2] == (2, 5) and 'it is inside a list item that div:: is not in' in said[1][2]

    def test_a_close_inside_a_bold_leaves_the_element_open_for_its_own(self):
        html, _ = quiet(lhtml.run, 'div:: a **x :: y** b ::')
        assert html == '<div> a <strong>x :: y</strong> b </div>'
        [(line, column, said)] = problems('div:: a **x :: y** b ::')
        assert (line, column) == (1, 13) and 'inside a bold that div:: is not in' in said

    def test_one_warning_per_crossing_naming_its_container(self):
        for text, kind in [('* a span::x\n', 'list item'), ('= T div:: x\n', 'heading'),
                           ('**a span:: b** c', 'bold'), ('__a span:: b__ c', 'italic')]:
            [(_, _, said)] = problems(text)
            assert f'closed at the end of the {kind} it is opened in' in said, said

    def test_an_italic_does_not_cross_a_bold(self):
        html, _ = quiet(lhtml.run, '**b __c** d__')
        assert html == '<strong>b __c</strong> d__'
        [(line, column, said)] = problems('**b __c** d__')
        assert (line, column) == (1, 5) and "would cross a bold" in said and "'__c** d__'" in said

    def test_a_link_label_does_not_cross_an_item_or_a_bold(self):
        html, _ = quiet(lhtml.run, '* link::u[a\n* b] c\n')
        assert html == '<ul>\n<li>\nlink::u[a\n</li>\n<li>\nb] c\n</li>\n</ul>\n'
        html, _ = quiet(lhtml.run, '**x link::u[**b**] y')
        assert html == '<strong>x link::u[</strong>b**] y'
        [(line, column, said)] = problems('**x link::u[**b**] y')
        assert (line, column) == (1, 5) and "link:: is left as text" in said and "'link::u[**b**]'" in said
        assert quiet(lhtml.run, 'link::u[a **b** c]')[0] == '<a href="u">a <strong>b</strong> c</a>'


class TestPlaces:

    CASES = ['* a', 'abc\n* x\n* ', 'xx\ndiv:: a **:: y**\n', '**a div:: b** c :: d',
             '* a span::[c] b\n* d ::\n', '\n* ', 'span::\n=() ::', '* ::c', '::z__::__',
             '= T div:: x\nmore\n* a\n** b **c**\n']

    def test_every_node_is_placed_and_nests_in_its_parent(self):
        for text in self.CASES:
            document, _ = quiet(lhtml.parse, text)
            for node in document.walk():
                if node is document:
                    continue
                assert node.line is not None, (text, node)
                start, end = node.span
                assert 0 <= start <= end <= len(text), (text, node)
                assert (node.line, node.column) == (text.count('\n', 0, start) + 1,
                                                    start - text.rfind('\n', 0, start)), (text, node)
                spans = [child.span for child in node.children]
                assert all(start <= a <= b <= end for a, b in spans), (text, node)
                assert all(b <= a for (_, b), (a, _) in zip(spans, spans[1:])), (text, node)

    def test_an_element_closed_by_its_container_ends_there(self):
        document, _ = quiet(lhtml.parse, '**a div:: b** c :: d')
        strong = next(n for n in document.walk() if n.kind == 'Strong')
        element = next(n for n in document.walk() if n.kind == 'Element')
        assert (strong.span, element.span, element.closed) == ((0, 13), (4, 11), 'container')

    def test_spans_are_offsets_in_the_text_given(self):
        text = '\ufeffa\r\n**b**\r\n'
        document, _ = quiet(lhtml.parse, text)
        strong = next(n for n in document.walk() if n.kind == 'Strong')
        assert text[strong.span[0]:strong.span[1]] == '**b**' and (strong.line, strong.column) == (2, 1)
        assert document.span == (0, len(text))

    def test_problems_are_in_source_order(self):
        said = problems('div:: a **x :: y** b\n')
        assert [(l, c) for l, c, _ in said] == sorted((l, c) for l, c, _ in said)

    def test_an_unknown_name_is_one_text(self):
        document = lhtml.parse('foo::(.x) y\n')
        assert [(n.kind, getattr(n, 'value', None)) for n in document.children] == [('Text', 'foo::(.x) y\n')]


class TestDepth:

    def test_deep_nesting_parses_and_renders(self):
        for text in ['div:: ' * 3000, 'div:: a **b :: c**\n' * 2000, '*' * 1500 + ' x\n',
                     ''.join('*' * k + ' x\n' for k in range(1, 1500))]:
            document, _ = quiet(lhtml.parse, text)
            assert lhtml.render(document)
            assert sum(1 for _ in document.walk()) > 1000

    def test_unclosed_brackets_take_linear_time(self):
        import time
        start = time.perf_counter()
        quiet(lhtml.run, 'span::[ x ' * 20000)
        assert time.perf_counter() - start < 3


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

    def test_the_anonymous_div_is_the_div_of_the_run(self):
        div = lhtml.Tag(container=True, render=lambda element, children, context: f'<section>{children}</section>')
        assert quiet(lhtml.run, '::(.a) x ::', tags={'div': div})[0] == '<section> x </section>'
        assert quiet(lhtml.run, '::(.a) x ::')[0] == '<div class="a"> x </div>'

    def test_the_built_in_tags_are_read_only(self):
        with pytest.raises(TypeError):
            lhtml.TAGS['foo'] = lhtml.Tag(render=lambda element, children, context: 'FOO')

    def test_an_inline_form_holds_nothing_even_in_a_container(self):
        cont = lhtml.Tag(container=True, render=lambda element, children, context:
                         f'<c>{element["text"]}|{children}</c>')
        assert quiet(lhtml.run, 'cont::x:: y', tags={'cont': cont})[0] == '<c>x::|</c> y'

    def test_a_tag_that_fails_names_itself_and_its_place(self):
        def fails(element, children, context):
            return 1 / 0
        with pytest.raises(lhtml.LHTMLError) as error:
            quiet(lhtml.run, 'a\nbad:: x ::', tags={'bad': lhtml.Tag(fails, container=True)})
        assert (error.value.line, error.value.column) == (2, 1) and 'bad::' in str(error.value)
        assert isinstance(error.value.__cause__, ZeroDivisionError)
        with pytest.raises(lhtml.LHTMLError, match='returned NoneType'):
            quiet(lhtml.run, 'none::', tags={'none': lhtml.Tag(lambda element, children, context: None)})
        with pytest.raises(lhtml.LHTMLError, match='container raised'):
            quiet(lhtml.run, 'bad:: x', tags={'bad': lhtml.Tag(str, container=lambda element: 1 / 0)})

    def test_the_tags_given_are_checked(self):
        with pytest.raises(TypeError, match='lhtml.Tag'):
            lhtml.run('x', tags={'old': lambda element, context: ''})
        for name in ('my tag', '1x', 'nl', 'code'):
            with pytest.raises(ValueError):
                lhtml.run('x', tags={name: lhtml.Tag(str)})

    def test_the_options_are_checked(self):
        with pytest.raises(TypeError, match='mapping'):
            lhtml.run('x', ['a'])
        with pytest.raises(TypeError, match='callable'):
            lhtml.render(lhtml.parse('x'), {'media': 'x'})

    def test_a_warning_names_the_tag_written(self):
        cont = lhtml.Tag(container=True, render=lambda element, children, context: children)
        [(_, _, said)] = problems('a\ncont:: x\n', tags={'cont': cont})
        assert said.startswith('cont:: is never closed')


class TestStages:
    """The stages read a text where each node already read is one character
    (EVENT_CHAR), a boundary: no HTML is written between them."""

    def test_a_node_read_ends_the_word_of_an_element_and_a_tag_may_follow_it(self):
        assert quiet(lhtml.run, '**span::x**')[0] == '<strong><span>x</span></strong>'
        assert quiet(lhtml.run, '**a**span::[c] b ::')[0] == '<strong>a</strong><span style="c"> b </span>'

    def test_a_label_keeps_the_markup_it_holds(self):
        assert quiet(lhtml.run, 'link::u[a **b** __c__]')[0] == '<a href="u">a <strong>b</strong> <em>c</em></a>'

    def test_an_unclosed_bracket_quotes_the_source(self):
        [(line, column, said)] = problems('= a link::u[x\n')
        assert (line, column) == (1, 5) and said.endswith("near 'link::u[x'")


class TestLineBreaks:
    """line-breaks, decided on the tree: a line break of the source (a Text)
    gets a <br> when its line and the next are not structure."""
    ON = {'line-breaks': True}

    def test_a_line_break_inside_the_html_of_a_tag_gets_none(self):
        html = lhtml.run('a\nspan::[color:red;\nfont-size:90%] b ::\nc', self.ON)
        assert html == 'a<br>\n<span style="color:red;\nfont-size:90%"> b </span><br>\nc'
        html = lhtml.run('a\nvideo::v.mp4\nb', self.ON)
        assert '<br>' not in html.split('<video')[1].split('</video>')[0]

    def test_a_block_element_is_structure_at_both_ends(self):
        assert lhtml.run('a\ndiv::[x] b\nc ::\nd', self.ON) == 'a\n<div style="x"> b\nc </div>\nd'

    def test_a_tag_that_writes_its_children_twice_is_one_piece(self):
        twice = lhtml.Tag(lambda element, children, context: f'<i>{children}{children}</i>', container=True)
        assert lhtml.run('a\nt:: b ::\nc', self.ON, tags={'t': twice}) == 'a<br>\n<i> b  b </i><br>\nc'


class TestMarksOfTheCaller:
    """The marks of the tree are Unicode noncharacters: a private-use
    character of the caller (the markers of a source map) is text."""

    def test_a_private_use_character_is_text(self):
        marker = 'page.html.j2:3'
        assert lhtml.run('div::(.x)' + marker + ' a ::') == '<div class="x">' + marker + ' a </div>'
        assert lhtml.run('span::x' + marker + '::') == '<span>x' + marker + '</span>'

    def test_a_mark_of_the_tree_in_the_input_is_replaced(self):
        # U+FDD0, the mark of the tree, is replaced; another noncharacter is text
        assert lhtml.run('a\ufdd0b \ufdd1') == 'a\ufffdb \ufdd1'


class TestWritten:

    def test_the_groups_and_value_of_an_element_are_as_written(self):
        document = lhtml.parse('div::[top:{{ top }}px](.c){title="\\(x\\)"} a ::\nimg::{{ base }}/a.png\n')
        div, img = [n for n in document.walk() if n.kind == 'Element']
        assert div.groups == {'[]': 'top:{{ top }}px', '()': '.c', '{}': 'title="\\(x\\)"'}
        assert img.value == '{{ base }}/a.png'
        assert lhtml.render(document).startswith('<div class="c" style="top:{{ top }}px" title="\\(x\\)">')


class TestLineBreaksAndTags:
    """With line-breaks, a tag is rendered once, with its children, as without."""
    ON = {'line-breaks': True}

    def test_a_tag_that_transforms_its_children_keeps_its_html(self):
        strip = lhtml.Tag(lambda element, children, context: f'<p>{children.strip()}</p>', container=True)
        assert lhtml.run('p:: a\nb ::', self.ON, tags={'p': strip}) == '<p>a\nb</p>'

    def test_a_tag_is_rendered_once(self):
        calls = []
        twice = lhtml.Tag(lambda element, children, context: calls.append(1) or f'<i>{children}{children}</i>',
                          container=True)
        lhtml.run('a\nt:: b\nc ::\nd', self.ON, tags={'t': twice})
        assert len(calls) == 1

    def test_a_tag_that_writes_its_children_as_given_gets_their_line_breaks(self):
        box = lhtml.Tag(lambda element, children, context: f'<b>{children}</b>', container=True)
        assert lhtml.run('x\nbox:: a\nb ::\ny', self.ON, tags={'box': box}) == 'x<br>\n<b> a<br>\nb </b><br>\ny'

    def test_the_attributes_of_a_heading_are_as_written(self):
        document = lhtml.parse('=(.{{ c }} #i) T\n')
        [heading] = [n for n in document.walk() if n.kind == 'Heading']
        assert heading.attributes == '.{{ c }} #i'
        assert lhtml.render(document) == '<h1 class="{{ c }}" id="i">T</h1>\n\n'
