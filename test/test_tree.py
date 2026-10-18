"""The document tree (lhtml.parse, lhtml.render, which lhtml.run is): its
shape, its places, the crossings, the tags. Before it was the engine of run,
its HTML was compared with the text passes it replaced on this suite, the
corpus and 80 000 fuzzed documents (docs/design.md of the generator, N5);
the HTML of run is what the rest of the suite checks."""
import re
import time
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

    def test_a_deeper_list_is_in_the_item_before_it(self):
        document = lhtml.parse('* Parent\n** Child\n* Next\n')
        assert kinds(document)[:8] == ['Document', '  List', '    Item', '      Text', '      List', '        Item',
                                       '          Text', '    Item']
        assert lhtml.render(document) == ('<ul>\n<li>\nParent\n<ul>\n<li>\nChild\n</li>\n</ul>\n</li>\n'
                                          '<li>\nNext\n</li>\n</ul>\n')
        # an item of its own only when there is none to hold it
        assert lhtml.run('** a\n* b') == '<ul>\n<li>\n<ul>\n<li>\na\n</li>\n</ul>\n</li>\n<li>\nb\n</li>\n</ul>\n'

    def test_nodes_nest_what_the_passes_wrote_flat(self):
        document = lhtml.parse('= Title\n* a **b**\n** c\ndiv::[x:y]\n`code` \\(m\\) <b>raw</b>\n::\n')
        assert kinds(document) == [
            'Document', '  Heading', '    Text', '  Text',
            '  List', '    Item', '      Text', '      Strong', '        Text', '      Text',
            '      List', '        Item', '          Text',
            '  Element', '    Text', '    InlineCode', '    Text', '    Math', '    Text',
            '    Raw', '    Text', '    Raw', '    Text', '  Text']

    def test_an_element_keeps_its_groups_and_value_and_a_code_block_its_language(self):
        document = lhtml.parse('img::a.png(.wide)[width:3px]\ncode::[python]\nx = 1\ncode::[-]\n')
        image = next(n for n in document.walk() if n.kind == 'Element')
        assert (image.name, image.written.tag, image.void, image.end_tag) == ('img', 'img', True, True)
        assert dict(image.attributes) == {'class': 'wide', 'style': 'width:3px', 'src': 'a.png', 'alt': 'a.png'}
        assert (image.written.text, image.written.parentheses, image.written.brackets) == ('a.png', '.wide', 'width:3px')
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
                        macros={'tiny': {'tag': 'span', 'class': 'tiny'}})
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
        assert (strong.span, element.span, element.end_tag) == ((0, 13), (4, 11), True)

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
        document = lhtml.parse('foo::(.x) y\n', warn=False)
        assert [(n.kind, getattr(n, 'value', None)) for n in document.children] == [('Text', 'foo::(.x) y\n')]
        assert [str(p) for p in document.problems] == ["foo:: is no tag, it is left as text (near 'foo::(.x)')"]


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
        alert = lhtml.Tag(lambda written: lhtml.Element('div', {'class': 'alert'}), container=True)
        html, _ = quiet(lhtml.run, 'alert:: warning **here** ::\n', tags={'alert': alert})
        assert html == '<div class="alert"> warning <strong>here</strong> </div>\n'
        badge = lhtml.Tag(lambda written: lhtml.Element('b', children=[lhtml.Text(written.text)]))
        assert quiet(lhtml.run, 'badge::new and more\n', tags={'badge': badge})[0] == '<b>new</b> and more\n'
        raw = lhtml.Tag(lambda written: lhtml.Raw('<hr class="x">'))
        assert lhtml.run('a raw:: b', tags={'raw': raw}) == 'a <hr class="x"> b'

    def test_a_macro_is_a_tag_and_warns_where_it_is(self):
        macros = {'gap': {'class': 'gap', 'variant': ['s', 'l'], 'empty': True}}
        document, said = quiet(lhtml.parse, 'x\ngap::zz\n', macros=macros)
        assert said == ["gap::zz: unknown variant, expected one of s, l"]
        assert (document.problems[0].line, document.problems[0].column) == (2, 1)

    def test_an_unknown_name_is_text(self):
        document = lhtml.parse('std::vector<int> v;\n')
        assert [n.kind for n in document.walk()] == ['Document', 'Text', 'Raw', 'Text']

    def test_the_anonymous_div_is_the_div_of_the_run(self):
        div = lhtml.Tag(lambda written: lhtml.Element('section'), container=True)
        assert quiet(lhtml.run, '::(.a) x ::', tags={'div': div})[0] == '<section> x </section>'
        assert quiet(lhtml.run, '::(.a) x ::')[0] == '<div class="a"> x </div>'

    def test_the_built_in_tags_are_read_only(self):
        with pytest.raises(TypeError):
            lhtml.TAGS['foo'] = lhtml.Tag(lambda written: lhtml.Text('FOO'))

    def test_an_inline_form_holds_nothing_even_in_a_container(self):
        cont = lhtml.Tag(lambda written: lhtml.Element('c', children=[lhtml.Text(written.text)]), container=True)
        assert quiet(lhtml.run, 'cont::x:: y', tags={'cont': cont})[0] == '<c>x</c> y'

    def test_a_tag_that_fails_names_itself_and_its_place(self):
        def fails(written):
            return 1 / 0
        with pytest.raises(lhtml.LHTMLError) as error:
            quiet(lhtml.run, 'a\nbad:: x ::', tags={'bad': lhtml.Tag(fails, container=True)})
        assert (error.value.line, error.value.column) == (2, 1) and 'bad::' in str(error.value)
        assert isinstance(error.value.__cause__, ZeroDivisionError)
        with pytest.raises(lhtml.LHTMLError, match='got NoneType'):
            quiet(lhtml.run, 'none::', tags={'none': lhtml.Tag(lambda written: None)})
        with pytest.raises(lhtml.LHTMLError, match='a container builds one Element'):
            quiet(lhtml.run, 'two:: x ::', tags={'two': lhtml.Tag(lambda written: [lhtml.Text(), lhtml.Text()],
                                                                  container=True)})
        with pytest.raises(lhtml.LHTMLError, match='container raised'):
            quiet(lhtml.run, 'bad:: x', tags={'bad': lhtml.Tag(str, container=lambda written: 1 / 0)})

    def test_the_tags_given_are_checked(self):
        with pytest.raises(TypeError, match='lhtml.Tag'):
            lhtml.run('x', tags={'old': lambda element, context: ''})
        for name in ('my tag', '1x', 'nl', 'code'):
            with pytest.raises(ValueError):
                lhtml.run('x', tags={name: lhtml.Tag(str)})

    def test_the_options_are_checked(self):
        with pytest.raises(TypeError, match='mapping'):
            lhtml.run('x', macros=['a'])
        with pytest.raises(TypeError, match='callable'):
            lhtml.render(lhtml.parse('x'), media='x')

    def test_a_warning_names_the_tag_written(self):
        cont = lhtml.Tag(lambda written: lhtml.Element('div'), container=True)
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
        assert (line, column) == (1, 5) and said.endswith("(near 'link::u[x')")


class TestLineBreaks:
    """line-breaks, decided on the tree: a line break of the source (a Text)
    gets a <br> when its line and the next are not structure."""
    ON = {'line_breaks': True}

    def test_a_line_break_inside_the_html_of_a_tag_gets_none(self):
        html = lhtml.run('a\nspan::[color:red;\nfont-size:90%] b ::\nc', **self.ON)
        assert html == 'a<br>\n<span style="color:red;\nfont-size:90%"> b </span><br>\nc'
        html = lhtml.run('a\nvideo::v.mp4\nb', **self.ON)
        assert '<br>' not in html.split('<video')[1].split('</video>')[0]

    def test_a_block_element_is_structure_at_both_ends(self):
        assert lhtml.run('a\ndiv::[x] b\nc ::\nd', **self.ON) == 'a\n<div style="x"> b\nc </div>\nd'

    def test_the_children_of_a_tag_of_the_caller_get_their_line_breaks(self):
        box = lhtml.Tag(lambda written: lhtml.Element('b'), container=True)
        assert lhtml.run('x\nbox:: a\nb ::\ny', **self.ON, tags={'box': box}) == 'x<br>\n<b> a<br>\nb </b><br>\ny'

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
        assert (div.written.brackets, div.written.parentheses, div.written.braces, div.written.text) == \
            ('top:{{ top }}px', '.c', 'title="\\(x\\)"', '')
        assert img.written.text == img.attributes['src'] == '{{ base }}/a.png'
        assert lhtml.render(document).startswith('<div class="c" style="top:{{ top }}px" title="\\(x\\)">')


class TestAuthoritativeTree:
    """render writes the HTML from the fields of the nodes alone."""

    def test_a_node_changed_changes_the_html(self):
        document = lhtml.parse('img::before.png and **b**\n')
        image = next(n for n in document.walk() if n.kind == 'Element')
        image.attributes['src'] = 'after.png'
        del image.attributes['alt']
        next(n for n in document.walk() if n.kind == 'Strong').children[0].value = 'c'
        assert lhtml.render(document) == '<img src="after.png"> and <strong>c</strong>\n'

    def test_the_label_of_a_link_is_its_children(self):
        document = lhtml.parse('link::page.html[Un **lien**]')
        link = next(n for n in document.walk() if n.kind == 'Element')
        assert [n.kind for n in link.walk()] == ['Element', 'Text', 'Strong', 'Text']
        assert (link.name, link.attributes['href'], link.written.brackets) == ('a', 'page.html', 'Un **lien**')
        assert [(n.line, n.column) for n in link.children] == [(1, 17), (1, 20)]
        link.children[0].value = 'A '
        assert lhtml.render(document) == '<a href="page.html">A <strong>lien</strong></a>'

    def test_the_word_of_an_element_is_its_content(self):
        document = lhtml.parse('span::bonjour monde ::')
        span = next(n for n in document.walk() if n.kind == 'Element')
        assert [c.value for c in span.children] == ['bonjour', ' monde ']
        assert span.children[1].span == (13, 20)

    def test_a_macro_builds_an_element(self):
        macros = {'demo': {'tag': 'iframe', 'url': 'src', 'class': 'demo', 'empty': True}}
        document = lhtml.parse('demo::a.html', macros=macros)
        demo = next(n for n in document.walk() if n.kind == 'Element')
        assert (demo.name, demo.written.tag, dict(demo.attributes)) == ('iframe', 'demo', {'class': 'demo', 'src': 'a.html'})

    def test_no_placeholder_in_the_tree(self):
        document = lhtml.parse('span::[c:{{ x }}](.{{ k }}) `i` \\(m\\) <b>r</b> link::{{ u }}[l `c`] ::\n')
        for node in document.walk():
            for value in vars(node).values():
                assert '\x00' not in str(value)
        assert 'stores' not in vars(document)

    def test_the_attributes_of_a_heading_are_as_written(self):
        document = lhtml.parse('=(.{{ c }} #i) T\n')
        [heading] = [n for n in document.walk() if n.kind == 'Heading']
        assert heading.parentheses == '.{{ c }} #i' and dict(heading.attributes) == {'class': '{{ c }}', 'id': 'i'}
        assert lhtml.render(document) == '<h1 class="{{ c }}" id="i">T</h1>\n\n'


class TestReviewSurprises:
    """Rules that hold for every tag, from an external review."""

    def test_the_url_of_a_url_macro_is_kept_as_written(self):
        macros = {'demo': {'tag': 'iframe', 'url': 'src', 'class': 'demo', 'empty': True}}
        html = lhtml.run('demo::my__demo__.html and **b**', macros=macros)
        assert 'src="my__demo__.html"' in html and '<em>' not in html and '<strong>b</strong>' in html
        assert 'style="width:3px"' in lhtml.run('demo::a.html#x[width:3px]', macros=macros)
        url = lhtml.Tag(lambda written: lhtml.Raw(f'<a href="{written.text}">'), url=True)
        assert lhtml.run('u::a__b__c', tags={'u': url}) == '<a href="a__b__c">'

    def test_a_quoted_attribute_value_holds_its_brackets(self):
        assert lhtml.run('link::u[Text]{title="a } b"}') == '<a title="a } b" href="u">Text</a>'
        assert lhtml.run("span::{data-x='[1, 2]'} a ::") == "<span data-x='[1, 2]'> a </span>"
        # an apostrophe after an unclosed { in text is text
        assert lhtml.run("a { b l'eau span::[c] d ::") == "a { b l'eau <span style=\"c\"> d </span>"

    def test_an_attribute_written_replaces_the_default(self):
        assert lhtml.run('img::photo.jpg{alt="Portrait"}') == '<img alt="Portrait" src="photo.jpg">'
        assert lhtml.run('img::photo.jpg') == '<img src="photo.jpg" alt="photo.jpg">'
        assert lhtml.run('link::u[T]{href="v"}') == '<a href="v">T</a>'
        assert lhtml.run('img::a.png{data-alt="x"}') == '<img data-alt="x" src="a.png" alt="a.png">'

    def test_an_option_spelled_otherwise_is_refused(self):
        for call in (lambda: lhtml.run('a', line_break=True), lambda: lhtml.run('a', {'line-breaks': True}),
                     lambda: lhtml.render(lhtml.parse('a'), line_break=True)):
            with pytest.raises(TypeError):
                call()

    def test_an_attribute_name_in_a_value_replaces_nothing(self):
        assert lhtml.run('link::page.html{onclick="location.href=\'x\'"}[go]') == \
            '<a onclick="location.href=\'x\'" href="page.html">go</a>'
        assert 'src="a.png"' in lhtml.run('img::a.png{onclick="this.src=\'b.png\'"}')
        assert lhtml.run('img::a.png{title="alt=x"}').count('alt=') == 2       # its own and the default
        assert lhtml.run('img::a.png{ALT="A"}').lower().count('alt=') == 1
        assert lhtml.run('img::a.png{alt}') == '<img alt src="a.png">'

    def test_a_macro_attribute_written_replaces_the_macro_one(self):
        macros = {'demo': {'tag': 'iframe', 'url': 'src', 'empty': True},
                  'im': {'tag': 'img', 'url': 'src', 'attrs': 'alt="" loading="lazy"'}}
        assert lhtml.run('demo::a.html{src="b"}', macros=macros).count('src=') == 1
        html = lhtml.run('im::a.png{alt="A"}', macros=macros)
        assert html.count('alt=') == 1 and 'alt="A"' in html and 'loading="lazy"' in html

    def test_apostrophes_in_text_are_text(self):
        assert lhtml.run("{ it's link::u[label] and it's ok") == "{ it's <a href=\"u\">label</a> and it's ok"
        assert '<img class="w"' in lhtml.run("l'ensemble {x | x > 0 et l'image img::a.png(.w) d'un")
        assert lhtml.run("span::{title=it's}x :: and it's") == "<span title=it's>x </span> and it's"

    def test_the_url_tags_are_those_of_the_run(self):
        plain = lhtml.Tag(lambda written: lhtml.Element('i', children=[lhtml.Text(written.text)]))
        assert '<em>' in lhtml.run('img::a__b__.png', tags={'img': plain})      # an img of the caller: no URL
        assert '<em>' in lhtml.run('img::a__b__.png', tags={n: plain for n in ('img', 'link', 'video', 'videoplay')})
        assert '<em>' not in lhtml.run('img::a__b__.png')

    def test_attribute_groups_stay_linear(self):
        import time
        for text in ('x::{a="}"\n' * 4000, 'img::a.png{' + ' ' * 40000 + '}', 'p::{a="{"} ' * 4000):
            start = time.perf_counter()
            quiet(lhtml.run, text)
            assert time.perf_counter() - start < 2, text[:20]

    def test_a_brace_in_a_quoted_value_is_text(self):
        assert lhtml.run('span::{title="a { b"}x ::') == '<span title="a { b">x </span>'
        assert lhtml.run("span::{title='{'}x ::") == "<span title='{'>x </span>"

    def test_an_unquoted_value_is_one_attribute(self):
        assert lhtml.run('img::a.png{title=a=alt}') == '<img title=a=alt src="a.png" alt="a.png">'
        assert 'src="a.png"' in lhtml.run('img::a.png{data-q=x=src}')
        assert lhtml.run('img::a.png{ {% if x %}alt="y"{% endif %} }').count('alt=') == 1

    def test_the_attributes_of_a_macro_stay_as_written(self):
        macros = {'d': {'tag': 'div', 'attrs': 'data-u=http://x?a=b a=b=c data-x="1"'}}
        assert '<div data-u=http://x?a=b a=b=c data-x="1">' in lhtml.run('d:: x ::', macros=macros)
        assert '<div data-u=http://x?a=b a=b=c data-x="2">' in lhtml.run('d::{data-x="2"} x ::', macros=macros) \
            or 'data-x="2"' in lhtml.run('d::{data-x="2"} x ::', macros=macros)

    def test_replacing_an_attribute_of_a_macro_keeps_the_others_as_written(self):
        macros = {'card': {'tag': 'img', 'attrs': 'title="a  b" loading="lazy"'}}
        assert lhtml.run('card::{loading="eager"} x.png', macros=macros) == \
            '<img title="a  b" loading="eager"> x.png'

    def test_one_priority_for_the_attributes_of_a_url_macro(self):
        # the macro, then its url, then the page: one src each time
        macros = {'demo': {'tag': 'iframe', 'url': 'src', 'empty': True, 'attrs': 'src="default.html" title="d"'}}
        run = lambda text: lhtml.run(text, macros=macros)
        assert run('demo::page.html') == '<iframe src="page.html" title="d"></iframe>'
        assert run('demo::') == '<iframe src="default.html" title="d"></iframe>'
        assert run('demo::page.html{src="b.html"}') == '<iframe title="d" src="b.html"></iframe>'

    def test_classes_and_styles_add_up(self):
        assert lhtml.run('img::a.png(.a){class="b a"}') == '<img class="a b" src="a.png" alt="a.png">'
        assert lhtml.run('span::[margin:0]{style="color:red"} x ::') == \
            '<span style="margin:0;color:red"> x </span>'
        macros = {'box': {'class': 'box', 'attrs': 'class="m" style="top:0"'}}
        assert lhtml.run('box::(.p){class="q" style="left:0"} x ::', macros=macros) == \
            '<div class="box m p q" style="top:0;left:0"> x </div>'
        # alone, a class written {...} stays where it is written
        assert lhtml.run('span::{title="t" class="c"} x ::') == '<span title="t" class="c"> x </span>'

    def test_a_default_of_a_video_written_in_the_page_is_not_doubled(self):
        html = lhtml.run('videoplay::a.mp4{loop="false"}')
        assert html.count('loop') == 1 and 'autoplay muted playsinline' in html

    def test_a_css_string_holds_its_brackets(self):
        assert lhtml.run('span::[content:"]";] texte ::') == \
            '<span style="content:&quot;]&quot;;"> texte </span>'
        assert lhtml.run("span::[font-family:'A]', serif] x ::") == \
            '<span style="font-family:\'A]\', serif"> x </span>'
        assert lhtml.run("link::u[l'ami [x]]") == '<a href="u">l\'ami [x]</a>'    # an apostrophe in a label is text

    def test_a_quoted_value_may_span_lines(self):
        assert lhtml.run('span::{title="a\n}b"} texte ::') == '<span title="a\n}b"> texte </span>'
        # not across a blank line: the brace closes the group, and the element is text
        html, said = quiet(lhtml.run, 'span::{title="a\n\n}b"} texte ::')
        assert html == '<span>{title="a\n\n}b"} texte </span>'
        assert said[0].startswith('span:: has a closing bracket without its opening one')

    def test_a_tag_whose_groups_are_left_as_text_is_warned(self):
        html, said = quiet(lhtml.run, 'div::[a]x] y ::')
        assert html == '<div>[a]x] y </div>'
        assert said == ["div:: has a closing bracket without its opening one: its groups are left as text "
                        "(near 'div::[a]x]')"]
        assert quiet(lhtml.run, 'f(a::b) and std::vector[0])')[1] == []       # not a tag: no warning

    def test_unclosed_quotes_stay_linear(self):
        import time
        for text in ('x::{a="\n' * 4000, "x::[a:'\n" * 4000, 'x::{a="' * 4000):
            start = time.perf_counter()
            quiet(lhtml.run, text)
            assert time.perf_counter() - start < 2, text[:20]

    def test_a_url_ends_before_marks_that_close_an_emphasis(self):
        macros = {'demo': {'tag': 'iframe', 'url': 'src', 'empty': True}}
        assert lhtml.run('**img::a.png**') == '<strong><img src="a.png" alt="a.png"></strong>'
        assert lhtml.run('x __img::a.png__ y') == 'x <em><img src="a.png" alt="a.png"></em> y'
        for text in ('**__img::a.png__**', '__**img::a.png**__'):        # nested, either order
            html = lhtml.run(text)
            assert 'src="a.png"' in html and '**' not in html and '__' not in html, html
        assert lhtml.run('**demo::a.html**', macros=macros) == '<strong><iframe src="a.html"></iframe></strong>'
        # marks that close nothing are the URL's
        assert 'href="https://d.org/x.html#object.__init__"' in lhtml.run('link::https://d.org/x.html#object.__init__')
        assert 'src="a**b.png"' in lhtml.run('img::a**b.png')

    def test_an_element_left_open_in_an_item_ends_before_its_nested_list(self):
        html, said = quiet(lhtml.run, '* a span:: x\n** b\n')
        assert html == '<ul>\n<li>\na <span> x\n</span><ul>\n<li>\nb\n</li>\n</ul>\n</li>\n</ul>\n'
        assert len(said) == 1 and 'closed at the end of the list item' in said[0]
        assert quiet(lhtml.run, 'div::\n* a\n** b\n::\n')[0].endswith('</ul>\n</div>\n')   # an element around the list holds it
        document, _ = quiet(lhtml.parse, '* a span:: x\n** b\n')
        span = next(n for n in document.walk() if n.kind == 'Element')
        assert span.end_tag and span.span[1] <= len('* a span:: x\n')


class TestSecondReview:
    """The findings of the review of the tree and the attributes."""

    def test_text_hidden_in_a_group_is_placed_where_it_is_written(self):
        document = lhtml.parse('a::b(.c `k` .d) z')
        assert [(n.kind, n.span) for n in document.children] == \
            [('Text', (0, 8)), ('InlineCode', (8, 11)), ('Text', (11, 17))]
        [label] = next(n for n in lhtml.parse('link::a[img::p.png]').walk() if n.kind == 'Element').children
        assert label.span == (8, 18)

    def test_the_space_between_two_labels_is_where_the_first_closes(self):
        link = lhtml.parse('x link::u[a](.c)[b] y').children[1]
        assert [(n.value, n.span) for n in link.children] == [('a', (10, 11)), (' ', (11, 11)), ('b', (17, 18))]

    def test_a_link_label_keeps_its_line_breaks(self):
        assert lhtml.run('link::u[a\nb]', line_breaks=True) == '<a href="u">a\nb</a>'

    def test_a_field_holding_a_nul_is_text(self):
        document = lhtml.parse('a\nb')
        document.children[0].value = '\x00R0\x00\nq'
        assert lhtml.render(document, line_breaks=True) == '\x00R0\x00<br>\nq'

    def test_repr_of_a_deep_tree(self):
        assert repr(quiet(lhtml.parse, 'div:: ' * 3000)[0]).startswith('Document(')

    def test_empty_groups_are_an_element(self):
        assert lhtml.run('::()::') == '<div></div>'

    def test_a_text_a_tag_builds_is_its_own(self):
        box = lhtml.Tag(lambda written: lhtml.Element('div', children=[lhtml.Text('head:')]), container=True)
        element = next(n for n in lhtml.parse('box:: x ::', tags={'box': box}).walk() if n.kind == 'Element')
        assert [c.value for c in element.children] == ['head:', ' x ']

    def test_many_urls_and_glued_markers_stay_linear(self):
        import time

        def duration(text):             # the best of two: a machine's own pauses aside
            times = []
            for _ in range(2):
                start = time.perf_counter()
                quiet(lhtml.run, text)
                times.append(time.perf_counter() - start)
            return min(times)
        # four times the text: about four times the time (quadratic: sixteen), on any machine
        for piece, count in (('link::u[a] ', 4000), ('a::', 4000), ('.a::', 3000)):
            small, large = duration(piece * count), duration(piece * count * 4)
            assert large < 8 * small + 0.02, (piece, small, large)

    def test_a_bracket_left_open_in_prose_holds_no_string(self):
        assert '<a href="u">label</a>' in quiet(lhtml.run, 'The interval [0, 1) is.\n\nNote: "see link::u[label]" end')[0]
        assert '<a href="u">l</a>' in quiet(lhtml.run, 'A set {x = "a, link::u[l] b" end')[0]

    def test_jinja_in_names_and_values(self):
        assert lhtml.run('img::a.png{title={{ x }} alt="y"}') == '<img title={{ x }} alt="y" src="a.png">'
        assert [a.name for a in lhtml.attributes.read('data-{{ a }}="1" data-{{ b }}="2" {{ more }}')] == \
            ['data-{{ a }}', 'data-{{ b }}']
        assert lhtml.run('img::a.png{{% if x %}alt="y"{% endif %}}') == '<img {% if x %}alt="y"{% endif %} src="a.png">'
        assert lhtml.run('img::a.png(.a){class="a {{ b }}"}') == '<img class="a {{ b }}" src="a.png" alt="a.png">'

    def test_one_id(self):
        assert lhtml.run('span::(#a){id="b"} t ::') == '<span id="b"> t </span>'
        assert lhtml.run('ida::(#p) t ::', macros={'ida': {'attrs': 'id="m"'}}) == '<div id="p"> t </div>'

    def test_the_class_and_style_of_a_macro_come_first(self):
        assert lhtml.run('sty::[a:2] t ::', macros={'sty': {'attrs': 'style="a:1"'}}) == '<div style="a:1;a:2"> t </div>'
        assert lhtml.run('pa::(.p) t ::', macros={'pa': {'class': 'k', 'attrs': 'class="m"'}}) == \
            '<div class="k m p"> t </div>'

    def test_an_unclosed_quote_is_warned(self):
        html, said = quiet(lhtml.run, 'div::{title="a\n\nb} t ::')
        assert said == ['div:: a value of its {...} has no closing quote: it is written so (near \'div::{title="a\')']

    def test_the_attributes_api(self):
        attributes = lhtml.Attributes.read(' x="1" ')
        assert attributes.html() == ' x="1"'
        attributes['y'] = None
        assert attributes.html() == ' x="1" y'
        with pytest.raises(KeyError):
            attributes[1]
        with pytest.raises(TypeError):
            attributes['z'] = 3


class TestLineBreaksOnTheNodes:
    """The line breaks read the nodes: an element by its name, a raw zone as written."""

    def test_an_element_built_as_pre_keeps_its_lines(self):
        pre = lhtml.Tag(lambda written: lhtml.Element('pre'), container=True)
        assert lhtml.run('a\np:: x\ny ::\nb', line_breaks=True, tags={'p': pre}) == 'a\n<pre> x\ny </pre>\nb'

    def test_a_block_element_by_its_name(self):
        section = lhtml.Tag(lambda written: lhtml.Element('section'), container=True)
        assert lhtml.run('a\ns:: x ::\nb', line_breaks=True, tags={'s': section}) == 'a\n<section> x </section>\nb'
        aside = lhtml.Tag(lambda written: lhtml.Element('q'), container=True)
        assert lhtml.run('a\ns:: x ::\nb', line_breaks=True, tags={'s': aside}) == 'a<br>\n<q> x </q><br>\nb'

    def test_a_zone_is_one_piece(self):
        assert lhtml.run('a\n<div>\nx\n</div>\nb', line_breaks=True) == 'a\n<div>\nx\n</div>\nb'


class TestPublicModel:
    """The nodes are made as they read; render reads the HTML fields of the
    nodes, never what the source wrote."""

    def test_a_node_is_made_as_it_reads(self):
        assert lhtml.Text('Bonjour').value == 'Bonjour'
        note = lhtml.Element('div', {'class': 'note'}, children=[lhtml.Strong(children=[lhtml.Text('!')])])
        assert isinstance(note.attributes, lhtml.Attributes)
        assert lhtml.render(note) == '<div class="note"><strong>!</strong></div>'
        assert lhtml.render(lhtml.Code('x = 1\n', 'python')).startswith('<div class="code"><pre>')
        assert lhtml.render(lhtml.Raw('<hr>')) == '<hr>'
        with pytest.raises(TypeError):
            lhtml.Text('a', (0, 1))     # a place is a keyword

    def test_what_the_source_wrote_does_not_change_the_html(self):
        import dataclasses
        document = lhtml.parse('span::x:: link::u[l]')
        before = lhtml.render(document)
        for node in document.walk():
            if isinstance(node, lhtml.Element):
                node.written = dataclasses.replace(node.written, tag='other', inline=False)
        assert lhtml.render(document) == before

    def test_an_element_never_closed_writes_no_closing_tag(self):
        document, _ = quiet(lhtml.parse, 'div:: a')
        div = next(n for n in document.walk() if n.kind == 'Element')
        assert not div.end_tag and lhtml.render(document) == '<div> a'
        div.end_tag = True
        assert lhtml.render(document) == '<div> a</div>'

    @pytest.mark.parametrize('name', ['span', 'a', 'div'])
    @pytest.mark.parametrize('line_breaks', [False, True])
    def test_a_deep_tree_needs_no_recursion(self, name, line_breaks):
        root = inner = lhtml.Element(name)
        for k in range(5000):
            child = lhtml.Element(name if k % 3 else 'span')
            inner.children.append(child)
            inner = child
        inner.children.append(lhtml.Text('x\ny'))
        html = lhtml.render(lhtml.Document(children=[root]), line_breaks=line_breaks)
        assert html.count(f'</{name}>') >= 3333 and 'x' in html

    def test_a_label_keeps_its_line_breaks_at_any_depth(self):
        assert lhtml.run('link::u[a **b**\nc]', line_breaks=True) == '<a href="u">a <strong>b</strong>\nc</a>'
        assert lhtml.run('x\nspan:: a\nb ::\ny', line_breaks=True) == 'x<br>\n<span> a<br>\nb </span><br>\ny'


class TestAttributeMerges:
    """The attributes are read once, merged as Attributes, written by render."""

    def test_an_empty_class_or_style_joins_the_others(self):
        assert lhtml.run('img::x.png(.a){class=""}') == '<img class="a" src="x.png" alt="x.png">'
        assert lhtml.run('span::[c:d]{style=""} x ::') == '<span style="c:d"> x </span>'
        assert lhtml.run('span::{class=""} x ::') == '<span class=""> x </span>'      # given: kept
        assert lhtml.run('span::{class="" class=""} x ::') == '<span class=""> x </span>'
        assert lhtml.run('span:: x ::') == '<span> x </span>'                       # absent: none

    def test_no_ordinary_attribute_twice(self):
        macros = {'box': {'class': 'box', 'attrs': 'class="m" title="t" data-a="1"'}}
        html = lhtml.run('box::(.p #i){class="q" title="u" data-a="2"} x ::', macros=macros)
        assert html == '<div class="box m p q" id="i" title="u" data-a="2"> x </div>'
        assert all(html.count(f' {name}=') == 1 for name in ('class', 'id', 'title', 'data-a'))

    def test_the_priorities_of_macro_url_and_page(self):
        macros = {'demo': {'tag': 'iframe', 'url': 'src', 'empty': True, 'attrs': 'src="d" id="m" allowfullscreen'}}
        assert lhtml.run('demo::', macros=macros) == '<iframe src="d" id="m" allowfullscreen></iframe>'
        assert lhtml.run('demo::u', macros=macros) == '<iframe src="u" id="m" allowfullscreen></iframe>'
        assert lhtml.run('demo::u(#p){src="w"}', macros=macros) == '<iframe id="p" allowfullscreen src="w"></iframe>'

    def test_a_variant_is_one_class(self):
        macros = {'gap': {'class': 'gap', 'variant': ['a.b'], 'empty': True}}
        assert lhtml.run('gap::a.b', macros=macros) == '<div class="gap gap-a.b"></div>'

    def test_an_attribute_without_value(self):
        document = lhtml.parse('video::v.mp4{controls}')
        video = next(n for n in document.walk() if n.kind == 'Video')
        assert video.attributes['controls'] is None and 'controls' in video.attributes
        video.attributes['muted'] = None
        assert '<video controls muted>' in lhtml.render(document)

    def test_jinja_in_a_name_keeps_its_case(self):
        document = lhtml.parse('span::{data-{{ K }}="one" DATA-X="y"} x ::')
        span = next(n for n in document.walk() if n.kind == 'Element')
        assert list(span.attributes) == ['data-{{ K }}', 'data-x']
        span.attributes['data-{{ K }}'] = 'two'
        assert 'data-{{ k }}' not in span.attributes
        assert lhtml.render(document) == '<span data-{{ K }}="two" DATA-X="y"> x </span>'

    def test_a_conditional_fragment_stays_in_its_place(self):
        document = lhtml.parse('img::a.png{{% if w %}width="{{ w }}"{% endif %} alt="A"}')
        image = next(n for n in document.walk() if n.kind == 'Element')
        image.attributes['alt'] = 'B'
        assert lhtml.render(document) == '<img {% if w %}width="{{ w }}"{% endif %} alt="B" src="a.png">'

    def test_a_merge_changes_neither_side(self):
        a, b = lhtml.Attributes({'x': '1'}), lhtml.Attributes({'y': '2'})
        a.extend(b)
        b['y'] = '3'
        assert (a['y'], dict(b)) == ('2', {'y': '3'})
        assert dict(a.without({'x'})) == {'y': '2'} and 'x' in a


class TestModelReview:
    """From the review of the model."""

    def test_a_video_is_made_from_its_src(self):
        assert lhtml.render(lhtml.Video('clip.mp4')).startswith('<video>\n\t<source src="clip.mp4"')

    def test_attributes_are_a_mapping(self):
        assert lhtml.render(lhtml.Element('div', None)) == '<div></div>'
        for wrong in ('class="a"', [('a', 'b')]):
            with pytest.raises(TypeError, match='mapping'):
                lhtml.Element('div', wrong)

    def test_the_written_of_a_link_is_a_value(self):
        link = next(n for n in lhtml.parse('link::u.html[a]').walk() if n.kind == 'Element')
        assert isinstance(link.written.label, tuple) and hash(link.written)
        again = next(n for n in lhtml.parse('link::u.html[a]').walk() if n.kind == 'Element')
        assert link.written == again.written


class TestAttributesReview:
    """From the review of the attribute merges."""

    def test_a_class_in_a_jinja_block_keeps_it(self):
        assert lhtml.run('img::x.png(.b){ {% if x %}class="a"{% endif %} }') == \
            '<img class="b {% if x %}a{% endif %}" src="x.png" alt="x.png">'
        assert lhtml.run('span::(.b){ {% if x %}class="a"{% else %}class="c"{% endif %} } x ::') == \
            '<span class="b {% if x %}a{% else %}c{% endif %}"> x </span>'
        # alone, it stays where it is
        assert lhtml.run('span::{ {% if x %}class="a"{% else %}class="c"{% endif %} } x ::') == \
            '<span {% if x %}class="a"{% else %}class="c"{% endif %}> x </span>'
        # the other attributes of its block stay in it
        assert lhtml.run('span::(.b){{% if x %}class="a" title="t"{% endif %} id="i"} x ::') == \
            '<span class="b {% if x %}a{% endif %}" {% if x %}title="t"{% endif %} id="i"> x </span>'
        macros = {'box': {'class': 'b', 'attrs': '{% if x %}style="m:1"{% endif %}'}}
        assert lhtml.run('box::[z:1] x ::', macros=macros) == \
            '<div class="b" style="z:1;{% if x %}m:1{% endif %}"> x </div>'
        # {% set x = 1 %} opens no block
        assert lhtml.run('img::x.png(.b){{% set k = 1 %} class="a"}').startswith('<img class="b a"')

    def test_a_statement_glued_to_a_value_is_part_of_it(self):
        assert lhtml.run('img::x.png(.p){class=a{% if x %}b{% endif %}}') == \
            '<img class="p a{% if x %}b{% endif %}" src="x.png" alt="x.png">'
        macros = {'box': {'attrs': 'title=a{% if x %}b{% endif %}'}}
        assert lhtml.run('box::{b=2} x ::', macros=macros) == '<div title=a{% if x %}b{% endif %} b=2> x </div>'

    def test_an_empty_class_of_a_macro_is_given(self):
        for name in ('class', 'style'):
            macros = {'box': {'attrs': f'{name}=""'}}
            assert lhtml.run('box:: x ::', macros=macros) == f'<div {name}=""> x </div>'
        assert lhtml.run('box::{class="z"} x ::', macros={'box': {'attrs': 'class=""'}}) == '<div class="z"> x </div>'

    def test_a_mapping_set_on_a_node_is_rendered(self):
        element = lhtml.Element('div')
        element.attributes = {'a': 'b'}
        assert lhtml.render(element) == '<div a="b"></div>'

    def test_a_macro_is_described_as_it_renders(self):
        info = lhtml.describe_macro('x', {'class': 'a', 'attrs': 'class="b" title="t"'})
        assert info['html'] == '<div class="a b" title="t">'


def test_attributes_in_many_jinja_blocks_stay_linear():
    import time

    def duration(n):
        text = 'span::{' + ' '.join(f'{{% if x %}}a{k}="1"{{% endif %}}' for k in range(n)) + '} x ::'
        start = time.perf_counter()
        lhtml.run(text)
        return time.perf_counter() - start
    small, large = duration(1000), duration(4000)
    assert large < 8 * small + 0.02, (small, large)


class TestProblems:
    """Each parse collects its own problems: no global state."""

    def test_problems_without_warnings(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            document = lhtml.parse('div:: x', warn=False)
        assert caught == [] and [p.line for p in document.problems] == [1]

    def test_a_warning_is_where_the_caller_called(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            lhtml.run('div:: x')
        assert [w.filename for w in caught] == [__file__]

    def test_an_error_holds_the_problems_before_it(self):
        macros = {'gap': {'class': 'gap', 'variant': ['s'], 'empty': True}}
        with pytest.raises(lhtml.LHTMLError) as error:
            lhtml.parse('gap::zz\nbad::\n', macros=macros, tags={'bad': lhtml.Tag(lambda written: 1 / 0)},
                        warn=False)
        assert [p.line for p in error.value.problems] == [1]

    def test_parses_in_threads_keep_their_own(self):
        from concurrent.futures import ThreadPoolExecutor

        def problems(k):
            text = 'div:: x\n' * (k % 3) + 'ok\n'
            return k, len(lhtml.parse(text, warn=False).problems)
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(problems, range(2000)))
        assert all(count == k % 3 for k, count in results)


class TestMessages:
    """What an author reads: one format, `subject: problem[; what to do] (near 'source')`,
    one warning for one mistake, a suggestion when a name is close to a known one."""

    def said(self, text, **options):
        return [str(p) for p in lhtml.parse(text, warn=False, **options).problems]

    def test_a_code_block_never_closed(self):
        assert self.said('code::[python]\nx = a**b**c\n') == [
            'code::[python] is never closed (its code::[-] is missing): what follows is read as LHTML']

    def test_a_code_closer_without_its_block(self):
        assert self.said('x\ncode::[-]\n') == [
            "code::[-] closes no code block; a block opens with code::[language] (near 'code::[-]')"]

    def test_one_warning_for_an_old_closer(self):
        said = self.said('* a span::[c] b span::[-]\n* d ::\n')
        assert said == ["span::[-]: [-] is a style here, not a closing tag; close a tag with :: "
                        "(near 'span::[-]')"]

    def test_a_language_close_to_a_known_one(self):
        assert self.said('code::[pyhton]\nx\ncode::[-]\n') == [
            "code::[pyhton]: unknown language, shown as plain text; did you mean 'python'?"]

    def test_a_variant_close_to_a_known_one(self):
        macros = {'gap': {'class': 'gap', 'variant': ['small', 'large'], 'empty': True}}
        assert self.said('gap::smal', macros=macros) == [
            "gap::smal: unknown variant, expected one of small, large; did you mean 'small'?"]

    def test_a_name_followed_by_a_group_is_no_tag(self):
        assert self.said('bxo::(.good) x', macros={'box': {}}) == [
            "bxo:: is no tag, it is left as text; did you mean 'box'? (near 'bxo::(.good)')"]
        assert self.said('std::vector<int> cgp::mesh(x)') == []      # C++ in the text

    def test_a_word_glued_to_its_closing(self):
        assert self.said('span::[c] word::\nx') == [
            "span:: is never closed; word:: is no closing ::, write 'word ::' (near 'span::[c]')"]

    def test_an_unclosed_bracket(self):
        assert self.said('a link::u[x and') == [
            "link:: '[' has no closing ']': it is left as text (near 'link::u[x and')"]

    def test_a_link_without_label_shows_its_url(self):
        assert lhtml.run('link::https://a.org and') == '<a href="https://a.org">https://a.org</a> and'
        assert lhtml.run('link::u[l]') == '<a href="u">l</a>'


@pytest.mark.parametrize('make', [
    lambda n: '**img::a.png** ' * n,                                                # URLs on one line
    lambda n: 'div:: ' * n + '\n' + ''.join(f'* a{k}\n\nx\n\n' for k in range(n)),     # lists, divs open
    lambda n: 'code::[zz]\nx\ncode::[-]\n' * n,                                     # unknown languages
], ids=['urls-on-a-line', 'lists-in-open-divs', 'unknown-languages'])
def test_long_texts_stay_linear(make):
    import time

    def duration(n):
        times = []
        for _ in range(2):
            start = time.perf_counter()
            lhtml.parse(make(n), warn=False)
            times.append(time.perf_counter() - start)
        return min(times)
    small, large = duration(500), duration(2000)
    assert large < 8 * small + 0.02, (small, large)


def test_attributes_of_many_names_stay_linear():
    import time

    def duration(n):
        start = time.perf_counter()
        lhtml.Attributes({f'a{k}': 'v' for k in range(n)})
        return time.perf_counter() - start
    small, large = duration(2000), duration(8000)
    assert large < 8 * small + 0.02, (small, large)


class TestThirdReview:

    def test_a_statement_in_a_jinja_string_or_comment_opens_no_block(self):
        assert lhtml.run('''div::(.base){title="{{ '{% if x %}' }}" class="extra"} x ::''') == \
            '''<div class="base extra" title="{{ '{% if x %}' }}"> x </div>'''
        assert lhtml.run('div::(.base){{# {% if x %} #} class="extra"} x ::') == \
            '<div class="base extra" {# {% if x %} #}> x </div>'

    @pytest.mark.parametrize('zone', ['code::[text]\nword::\ncode::[-]\n', '<!--\nword::\n-->\n'])
    def test_a_word_in_a_zone_is_no_closing_meant(self, zone):
        assert [str(p) for p in lhtml.parse('div::\n' + zone, warn=False).problems] == \
            ["div:: is never closed (near 'div::')"]


class TestExtensionHelpers:

    def test_add_class(self):
        attributes = lhtml.Attributes.read('title="t" class="a b"')
        assert attributes.add_class('b c', 'd').html() == ' title="t" class="a b c d"'
        assert lhtml.Attributes({'id': 'x'}).add_class('n').html() == ' id="x" class="n"'
        assert lhtml.Attributes.read('class="{{ k }} a"').add_class('a', 'z')['class'] == '{{ k }} a z'

    def test_load_macros_checks_each_definition(self, tmp_path):
        with pytest.raises(lhtml.LHTMLMacroError, match='invalid macro name'):
            lhtml.load_macros({'1bad': {}})
        path = tmp_path / 'macros.yaml'
        path.write_text('box: {class: b, colour: red}\n')
        with pytest.raises(lhtml.LHTMLMacroError, match='unknown field') as error:
            lhtml.load_macros(str(path))
        assert error.value.path == str(path)
        assert lhtml.load_macros([{'a': {}}, {'a': None}]) == {}


class TestAuthorsGroup4:

    def said(self, text):
        return [str(p) for p in lhtml.parse(text, warn=False).problems]

    def test_a_heading_with_a_style_or_attributes(self):
        assert self.said('=[color:red] Titre\nx') == [
            '=[color:red] Titre: a heading takes (.class #id) only, it is left as text']
        assert self.said('=(.c) Titre') == []

    def test_bold_or_italic_across_lines(self):
        assert self.said('**a\nb** c') == [
            "**...** across lines is no bold (each is within its line): it is left as text (near '**a')"]
        assert self.said('x __a\nb__ y')[0].startswith('__...__ across lines is no italic')
        for fine in ('2**10 and 3**4\nz', '**a**\nb', '**a\n\nb**', 'my__var and __init__'):
            assert self.said(fine) == [], fine

    def test_an_indented_code_closer_adds_no_line(self):
        assert lhtml.run('  code::[text]\n  x\n  code::[-]\n') == \
            '  <div class="code"><pre><span></span>  x\n</pre></div>\n\n'


class TestDesignGroup5:

    def test_setting_an_attribute_of_jinja_branches_gives_it_always(self):
        cases = {'{% if x %}title="a"{% else %}title="b"{% endif %} alt="z"': ' alt="z" title="T"',
                 'title="o" {% if x %}title="a" id="i"{% endif %}': ' title="T" {% if x %}id="i"{% endif %}',
                 'title="o" {% if x %}title="a"{% endif %}': ' title="T"',
                 'a=1 title="o" b=2': ' a=1 title="T" b=2'}
        for written, html in cases.items():
            attributes = lhtml.Attributes.read(written)
            attributes['title'] = 'T'
            assert attributes.html() == html, written

    def test_two_style_groups_are_one_style(self):
        assert lhtml.run('span::[a:1][b:2] x ::') == '<span style="a:1;b:2"> x </span>'
        assert lhtml.run('span::[a:1;][b:2] x ::') == '<span style="a:1;b:2"> x </span>'
        assert lhtml.run('link::u[a][b]') == '<a href="u">a b</a>'         # a label, two groups

    def test_a_heading_keeps_its_parentheses(self):
        heading = next(n for n in lhtml.parse('=(.a #b) T').walk() if n.kind == 'Heading')
        assert heading.parentheses == '.a #b'

    def test_attributes_equal(self):
        A = lhtml.Attributes
        assert A.read('a="1"') == A({'a': '1'}) and A.read('a=1') == {'a': '1'}
        assert A.read('{% if x %}a=1{% endif %}') != {'a': '1'}      # its block: not a dict
        assert A.read('a=1 a=2') != {'a': '1'}
        assert A.read('{% if x %}a=1{% endif %}') != A.read('a=1')

    def test_an_excerpt_is_cut_by_columns(self):
        from lhtml.diagnostics import excerpt
        shown, underline = excerpt('é' * 150 + ' X ' + 'é' * 50, 152,
                                   lambda ch: ch.encode('ascii', 'backslashreplace').decode())
        assert len(shown) < 120 and shown[underline.index('^')] == 'X'

    def test_a_pre_never_closed_keeps_the_rest_preformatted(self):
        document = lhtml.Document(children=[lhtml.Text('a\nb\n'),
                                            lhtml.Element('pre', children=[lhtml.Text('x\ny')], end_tag=False),
                                            lhtml.Text('\nc\nd')])
        assert lhtml.render(document, line_breaks=True) == 'a<br>\nb\n<pre>x\ny\nc\nd'


class TestLexersOfACall:

    def test_lexers_of_a_call(self):
        from pygments.lexers import PythonLexer
        text = 'code::[mypy]\nimport x\ncode::[-]\n'
        document = lhtml.parse(text, lexers={'mypy': PythonLexer}, warn=False)
        assert document.problems == []
        assert 'class="kn"' in lhtml.render(document, lexers={'mypy': PythonLexer})
        assert 'class="kn"' in lhtml.run(text, lexers={'mypy': PythonLexer})
        assert 'class="kn"' in lhtml.highlight('import x\n', 'mypy', lexers={'mypy': PythonLexer})
        assert 'mypy' not in lhtml.LEXERS                                  # no other call changes
        assert lhtml.parse(text, warn=False).problems                      # unknown without them

    def test_lexers_are_checked(self):
        for wrong in (['a'], {'a': 1}, {1: str}):
            with pytest.raises(TypeError, match='lexers'):
                lhtml.run('x', lexers=wrong)


class TestTagsInALabel:
    """The label of a link reads the elements that hold nothing: a thumbnail
    as a link, without raw HTML."""

    def said(self, text):
        return [str(p) for p in lhtml.parse(text, warn=False).problems]

    def html(self, text):
        return lhtml.render(lhtml.parse(text, warn=False))

    def test_an_image_as_a_link(self):
        assert lhtml.run('link::a.html[img::b.png]') == '<a href="a.html"><img src="b.png" alt="b.png"></a>'
        assert lhtml.run('link::a.html[img::b.png Voir **la** suite]') == \
            '<a href="a.html"><img src="b.png" alt="b.png"> Voir <strong>la</strong> suite</a>'
        macros = {'gap': {'class': 'g', 'variant': ['l'], 'empty': True}}
        assert lhtml.run('link::u[gap::l]', macros=macros) == '<a href="u"><div class="g g-l"></div></a>'

    def test_the_image_is_a_node_of_the_label(self):
        document = lhtml.parse('x link::a.html[img::b.png]')
        link = next(n for n in document.walk() if n.kind == 'Element' and n.name == 'a')
        image = link.children[0]
        assert (image.name, image.written.tag, image.line, image.column) == ('img', 'img', 1, 16)

    def test_what_would_hold_the_label_stays_text(self):
        assert self.html('link::a.html[div::(.c) x]') == '<a href="a.html">div::(.c) x</a>'
        assert self.said('link::a.html[div::(.c) x]') == [
            "div:: holds what follows: in the label of a link it is left as text (near 'div::(.c)')"]
        assert self.html('link::a[link::b[x]]') == '<a href="a">link::b[x]</a>'
        assert self.said('link::a[link::b[x]]') == [
            "link:: in the label of a link is left as text (near 'link::b[x]')"]
        assert lhtml.run('link::u[cgp::mesh a::b a :: b]') == '<a href="u">cgp::mesh a::b a :: b</a>'


class TestReadingASource:
    """lhtml.zones and lhtml.read_tag: a source as LHTML reads it, for tools."""

    def test_the_zones(self):
        text = ('code::[python]\nc\ncode::[-]\n{{ j }} {# k #}\n<!-- h -->\n<script>s</script>\n`i`\n'
                'img::{{ base }}/a.png(.w)\n\\(m\\)\n<b>\n')
        found = [(z.kind, text[z.start:z.end]) for z in lhtml.zones(text)]
        assert [kind for kind, _ in found] == ['code', 'jinja', 'comment', 'comment', 'raw', 'inline_code',
                                               'url', 'math', 'tag']
        url = next(z for z in lhtml.zones(text) if z.kind == 'url')
        assert (url.tag, url.value) == ('img', '{{ base }}/a.png')

    def test_an_outer_zone_owns_what_it_holds(self):
        assert [z.kind for z in lhtml.zones('`<script>x</script>` <!-- `c` -->')] == ['inline_code', 'comment']

    def test_the_zones_of_other_tags_and_of_another_markup(self):
        assert [z.tag for z in lhtml.zones('demo::a__b.html', url_tags=('demo',))] == ['demo']
        assert lhtml.zones('demo::a__b.html') == []
        fences = re.compile(r'(?m:^```[^\n]*\n.*?^```$)', re.DOTALL)
        assert [z.kind for z in lhtml.zones('```\n<b>\n```\n<i>', code=fences)] == ['code', 'tag']
        assert [z.kind for z in lhtml.zones('= T\n<b>', start=4)] == ['tag']

    def test_read_tag(self):
        found = lhtml.read_tag('x includeadv::{root: a, file: b} y', 2)
        assert (found.start, found.end) == (2, 32)
        assert (found.written.tag, found.written.braces, found.written.line, found.written.column) == \
            ('includeadv', 'root: a, file: b', 1, 3)
        written = lhtml.read_tag('img::{{ base }}/a.png(.w)[s]', 0).written
        assert (written.text, written.parentheses, written.brackets) == ('{{ base }}/a.png', '.w', 's')
        assert lhtml.read_tag('span::x::', 0).written.inline and lhtml.read_tag('no tag', 0) is None

    def test_the_url_ends_where_parse_ends_it(self):
        for text in ('**img::a.png**', '__**img::a.png**__'):
            assert [z.value for z in lhtml.zones(text) if z.kind == 'url'] == ['a.png']
            assert [f.written.text for f in lhtml.read_tags(text)] == ['a.png']
        found = list(lhtml.read_tags('(link::https://e.org/S_t[screen tearing]).'))
        assert [(f.written.text, f.written.brackets) for f in found] == [('https://e.org/S_t', 'screen tearing')]

    def test_read_tags_reads_as_parse(self):
        text = ('a `img::no.png` <!-- img::c.png --> **img::z.png** std::vector cgp::mesh\n'
                'code::[t]\nimg::q.png\ncode::[-]\nlink::u[img::in.png] x __video::v.mp4 y__\n')
        found = [(f.written.tag, f.written.text, text[f.start:f.end]) for f in lhtml.read_tags(text)]
        assert found == [('img', 'z.png', 'img::z.png'), ('link', 'u', 'link::u[img::in.png]'),
                         ('img', 'in.png', 'img::in.png'), ('video', 'v.mp4', 'video::v.mp4')]
        macros = {'demo': {'url': 'src', 'empty': True}}
        assert [f.written.tag for f in lhtml.read_tags('demo::a.html', macros=macros)] == ['demo']
        assert list(lhtml.read_tags('demo::a.html')) == []          # no tag of the run: text

    def test_read_tags_is_linear(self):
        import time

        def duration(n):
            text = ' '.join('img::a.png(.c)' for _ in range(n))
            start = time.perf_counter()
            assert len(list(lhtml.read_tags(text))) == n
            return time.perf_counter() - start
        small, large = duration(500), duration(2000)
        assert large < 8 * small + 0.02, (small, large)



class TestFourthReview:

    def test_wrap_takes_any_iterable(self):
        assert lhtml.wrap('x', css=(name for name in ['a.css', 'b.css'])).count('rel="stylesheet"') == 2

    def test_links_nested_deeply_need_no_recursion(self):
        html, _ = quiet(lhtml.run, 'link::a[' * 3000 + 'x' + ']' * 3000)
        assert html.startswith('<a href="a">link::a[')

    def test_only_if_and_for_blocks_join_a_class(self):
        assert lhtml.run('span::(.base){{% for c in cs %}class="{{ c }}"{% endfor %}} t ::') == \
            '<span class="base {% for c in cs %} {{ c }}{% endfor %}"> t </span>'
        assert lhtml.run('span::(.base){{% set x %}class="z"{% endset %}} t ::') == \
            '<span class="base" {% set x %}class="z"{% endset %}> t </span>'
        attributes = lhtml.Attributes.read('title="o" {% set x %}title="s"{% endset %}')
        attributes['title'] = 'T'
        assert attributes.html() == ' title="T" {% set x %}title="s"{% endset %}'

    def test_read_tag_reads_the_syntax_anywhere(self):
        text = 'code::[c++]\nincludeadv::{filepath:"f.hpp"}\ncode::[-]\n'
        found = lhtml.read_tag(text, text.index('includeadv'))
        assert (found.written.braces, found.written.line) == ('filepath:"f.hpp"', 2)
        assert list(lhtml.read_tags(text, {'includeadv'})) == []            # parse: in a code block

    def test_a_page_read_tag_by_tag_stays_linear(self):
        import time

        def duration(n):
            text = '\n'.join('img::a.png(.c)' for _ in range(n))
            start = time.perf_counter()
            for k in range(n):
                lhtml.read_tag(text, k * 15)
            return time.perf_counter() - start
        small, large = duration(500), duration(2000)
        assert large < 8 * small + 0.02, (small, large)


class TestFifthReview:

    def test_read_tags_keeps_the_rules_of_each_tag(self):
        text = 'link::u[span:: x] link::v[img::p.png]'
        found = list(lhtml.read_tags(text))
        assert [f.written.tag for f in found] == ['link', 'link', 'img']     # span:: is text in a label
        label = found[1].written.label
        assert label[0].name == 'img' and label[0].attributes['src'] == 'p.png'
        assert [text[f.start:f.end] for f in found] == ['link::u[span:: x]', 'link::v[img::p.png]', 'img::p.png']

    def test_read_tags_gives_the_opening_of_a_container(self):
        text = 'div::(.c) a img::b.png ::'
        assert [(f.written.tag, text[f.start:f.end]) for f in lhtml.read_tags(text)] == \
            [('div', 'div::(.c)'), ('img', 'img::b.png')]

    def test_a_block_with_another_statement_is_not_folded(self):
        assert lhtml.run('div::(.base){{% if ok %}{% set c = "e" %}class="{{ c }}"{% endif %}} x ::') == \
            '<div class="base" {% if ok %}{% set c = "e" %}class="{{ c }}"{% endif %}> x </div>'

    def test_a_loop_in_a_block_separates_its_turns(self):
        assert lhtml.run('div::(.base){{% if ok %}{% for c in l %}class="{{ c }}"{% endfor %}{% endif %}} x ::') == \
            '<div class="base {% if ok %}{% for c in l %} {{ c }}{% endfor %}{% endif %}"> x </div>'

    def test_blocks_that_write_in_place_are_folded(self):
        assert lhtml.run('span::(.base){{% with %}class="z"{% endwith %}} t ::') == \
            '<span class="base {% with %}z{% endwith %}"> t </span>'
        assert lhtml.run('span::(.base){{%- for c in cs -%}class="{{ c }}"{%- endfor %}} t ::') == \
            '<span class="base {% for c in cs %} {{ c }}{% endfor %}"> t </span>'

    def test_an_attribute_set_is_read_back(self):
        attributes = lhtml.Attributes.read('{% set y %}title="b"{% endset %}')
        attributes['title'] = 'T'
        assert attributes['title'] == 'T' and dict(attributes) == {'title': 'T'}

    def test_wrap_refuses_bytes(self):
        for value in (b'ab', bytearray(b'z'), ['a.css', 3]):
            with pytest.raises(TypeError):
                lhtml.wrap('x', css=value)

    def test_a_stray_closing_bracket_ends_a_url(self):
        assert lhtml.run('(see link::https://x.org) more') == '(see <a href="https://x.org">https://x.org</a>) more'
        assert lhtml.run('(link::https://w.org/A_(b)) x') == '(<a href="https://w.org/A_(b)">https://w.org/A_(b)</a>) x'
        assert [z.value for z in lhtml.zones('(see img::a.png) more') if z.kind == 'url'] == ['a.png']

    def test_read_tag_reads_as_parse_where_parse_reads(self):
        for text, start, expected in [('**includeadv::{a:1}** c', 2, 'includeadv::{a:1}'),
                                      ('span::[c]**bold** text', 0, 'span::[c]'),
                                      ('link::p.html[includeadv::a.txt] after', 13, 'includeadv::a.txt'),
                                      ('**img::a.png**', 2, 'img::a.png')]:
            found = lhtml.read_tag(text, start)
            assert text[found.start:found.end] == expected
        assert lhtml.read_tag('link::a.html[t][u] q', 0).written.brackets == 't u'
        assert lhtml.read_tag('abc span::x', 5) is None
        with pytest.raises(ValueError):
            lhtml.read_tag('x', -3)

    def test_read_tag_is_linear_on_one_line(self):
        text = '**img::a.png** ' * 20000
        started = time.perf_counter()
        for m in re.finditer('img::', text):
            lhtml.read_tag(text, m.start())
        assert time.perf_counter() - started < 5

    def test_zones_code_flags_are_its_own(self):
        found = lhtml.zones('IMG::a.png ```A```', code=re.compile('```a```', re.I))
        assert [z.kind for z in found] == ['code']


class TestSixthReview:

    def test_read_tag_parses_a_page_once_whatever_its_names(self):
        names = ['img', 'link', 'span', 'div', 'b', 'video', 'figure', 'n0', 'n1', 'n2']
        text = ' '.join(f'{names[i % len(names)]}::a{i}.png' for i in range(2000))
        started = time.perf_counter()
        found = [lhtml.read_tag(text, m.start()) for m in re.finditer(r'(?<![\w-])\w+::', text)]
        assert time.perf_counter() - started < 5
        assert [f.written.tag for f in found[:10]] == names

    def test_a_value_after_a_block_has_its_joiner(self):
        assert lhtml.run('div::(.base){{% if ok %}{% if ok %}class="a"{% endif %}class="b"{% endif %}} x ::') == \
            '<div class="base {% if ok %}{% if ok %}a{% endif %} b{% endif %}"> x </div>'
        assert lhtml.run('div::(.base){{% if ok %}class="a"{% else %}class="b"{% endif %}} x ::') == \
            '<div class="base {% if ok %}a{% else %}b{% endif %}"> x </div>'

    def test_zones_keeps_the_ascii_flag_of_code(self):
        assert lhtml.zones('é', code=re.compile(r'\w', re.A)) == []
