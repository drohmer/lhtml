"""LHTML test suite.

Tests cover:
- Input/output reference pairs (regression tests)
- Heading syntax (with and without class/id)
- Comment removal
- Plugin system (tag registry, lexer registry)
- Non-regression on real-world lab_website examples
"""

import os
import re
import glob
import time
import warnings

import pytest

import lhtml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INPUT_DIR = os.path.join(os.path.dirname(__file__), 'input_tests')
def _normalize_pygments(html):
    """Ignore quote escaping inside <pre> blocks, which varies across Pygments versions."""
    return re.sub(r'<pre>.*?</pre>',
                  lambda m: m.group(0).replace('&quot;', '"').replace('&#39;', "'"),
                  html, flags=re.DOTALL)


def _find_test_pairs():
    """Find all .l.html / -out.html test pairs."""
    pairs = []
    for f in sorted(os.listdir(INPUT_DIR)):
        if f.endswith('.l.html'):
            ref = f.replace('.l.html', '-out.html')
            ref_path = os.path.join(INPUT_DIR, ref)
            if os.path.isfile(ref_path):
                pairs.append((f, ref))
    return pairs


# ---------------------------------------------------------------------------
# Reference pair tests (replaces run_test.py)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('input_file,ref_file', _find_test_pairs(),
                         ids=[p[0] for p in _find_test_pairs()])
def test_reference_pair(input_file, ref_file):
    """Each .l.html input should produce output matching -out.html."""
    with open(os.path.join(INPUT_DIR, input_file)) as f:
        txt = f.read()
    with open(os.path.join(INPUT_DIR, ref_file)) as f:
        expected = f.read()

    result = lhtml.run(txt)
    if input_file.endswith('.w.l.html'):
        result = lhtml.wrap(result)

    # Reference files have trailing newline
    result, expected = _normalize_pygments(result), _normalize_pygments(expected)
    assert result == expected[:-1] or result == expected


# ---------------------------------------------------------------------------
# Heading tests
# ---------------------------------------------------------------------------

class TestHeadings:
    def test_simple_title(self):
        assert '<h1>Hello</h1>' in lhtml.run('\n= Hello\n')

    def test_h2(self):
        assert '<h2>Sub</h2>' in lhtml.run('\n== Sub\n')

    def test_h3(self):
        assert '<h3>Deep</h3>' in lhtml.run('\n=== Deep\n')

    def test_with_class(self):
        r = lhtml.run('\n=(.myClass) Styled\n')
        assert '<h1 class="myClass">Styled</h1>' in r

    def test_with_id(self):
        r = lhtml.run('\n=(#myId) IDed\n')
        assert '<h1 id="myId">IDed</h1>' in r

    def test_with_class_and_id(self):
        r = lhtml.run('\n=(.cls #id) Both\n')
        assert 'class="cls"' in r
        assert 'id="id"' in r

    def test_parentheses_in_content(self):
        r = lhtml.run('\n= Exemples de (très bons) projets\n')
        assert '<h1>Exemples de (très bons) projets</h1>' in r


# ---------------------------------------------------------------------------
# Comment tests
# ---------------------------------------------------------------------------

class TestComments:
    def test_comment_is_refused_by_name(self):
        with pytest.raises(lhtml.LHTMLParseError, match='::# comments were removed'):
            lhtml.run('\nSome text ::# this is a comment\n')

    def test_anchor_is_not_a_comment(self):
        assert lhtml.run('link::#top[Top]\n') == '<a href="#top">Top</a>\n'


# ---------------------------------------------------------------------------
# Inline formatting tests
# ---------------------------------------------------------------------------

class TestInlineFormatting:
    def test_bold(self):
        assert '<strong>bold</strong>' in lhtml.run('\n**bold**\n')

    def test_italic(self):
        assert '<em>italic</em>' in lhtml.run('\n__italic__\n')

    def test_inline_code(self):
        assert '<code class="code-inline">x</code>' in lhtml.run('\n`x`\n')

    def test_nested_bold_italic(self):
        r = lhtml.run('\n**bold with __italic__ inside**\n')
        assert '<strong>' in r
        assert '<em>italic</em>' in r


# ---------------------------------------------------------------------------
# Tag system tests
# ---------------------------------------------------------------------------

class TestTags:
    def test_div_with_style(self):
        r = lhtml.run('\ndiv::[color:red;] hello ::\n')
        assert '<div style="color:red;"> hello </div>' in r

    def test_link(self):
        r = lhtml.run('\nlink::https://example.com[Click]\n')
        assert '<a href="https://example.com">Click</a>' in r

    def test_img(self):
        r = lhtml.run('\nimg::pic.jpg[width:100px;]\n')
        assert 'src="pic.jpg"' in r
        assert 'alt="pic.jpg"' in r

    def test_spacer(self):
        r = lhtml.run('\n::nl\n')
        assert '<div style="height:1em;"></div>' in r

    def test_passthrough_std_namespace(self):
        r = lhtml.run('\nstd::vector<float>\n')
        assert 'std::vector<float>' in r

    def test_passthrough_trick(self):
        r = lhtml.run('\ntrick::\n')
        assert 'trick::' in r


# ---------------------------------------------------------------------------
# Explicit closing tags
# ---------------------------------------------------------------------------

class TestExplicitClosing:
    """::name[-] and ::[-] were removed in 3.0: a tag is closed by ::."""

    @pytest.mark.parametrize('source', ['div::[c]\nx\n::div[-]\n', 'div::[c]\nx\n::[-]\n'])
    def test_refused_by_name(self, source):
        with pytest.raises(lhtml.LHTMLParseError, match='close a tag with ::'):
            lhtml.run(source)

    def test_bare_close_still_works(self):
        r = lhtml.run('\ndiv::[color:green;]\ntext\n::\n')
        assert '</div>' in r

    def test_named_tag_with_dash_style_warns(self):
        r, w = _run_with_warnings('span::[c] x span::[-] y\n')
        assert '<span style="-">' in r
        assert any('not a closing tag' in x for x in w)


# ---------------------------------------------------------------------------
# Verbatim tests
# ---------------------------------------------------------------------------

class TestVerbatim:
    @pytest.mark.parametrize('source, expected', [
        ('div::{title="see ::#top"} x ::\n', '<div title="see ::#top"> x </div>\n'),
        ('div::{data-x="verbatim::[]"} x ::\n', '<div data-x="verbatim::[]"> x </div>\n'),
    ])
    def test_removed_syntax_inside_an_attribute_is_text(self, source, expected):
        assert lhtml.run(source) == expected

    def test_groups_of_a_stray_element_stay_literal(self):
        with pytest.warns(lhtml.LHTMLWarning, match='closing bracket without its opening one'):
            assert lhtml.run('div::[a__b__]x] y ::\n') == '<div>[a__b__]x] y </div>\n'

    def test_refused_by_name(self):
        with pytest.raises(lhtml.LHTMLParseError, match='verbatim:: was removed'):
            lhtml.run('\nverbatim::[]\n**not bold**\nverbatim::[-]\n')


# ---------------------------------------------------------------------------
# Plugin system tests
# ---------------------------------------------------------------------------

class TestPluginSystem:
    def test_custom_tag(self):
        tags = {'alert': lhtml.Tag(lambda written: lhtml.Element('div', {'class': 'alert'},
                                                                 children=[lhtml.Text(written.text)]))}
        r = lhtml.run('\nalert::Warning\n', tags=tags)
        assert '<div class="alert">Warning</div>' in r
        assert 'alert' not in lhtml.TAGS

    def test_custom_lexer(self, monkeypatch):
        from pygments.lexers import PythonLexer
        monkeypatch.setitem(lhtml.LEXERS, 'mypython', PythonLexer)
        assert 'class="kn"' in lhtml.run('code::[mypython]\nimport x\ncode::[-]\n')


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------

class TestCodeBlocks:
    def test_python_code_block(self):
        r = lhtml.run('\ncode::[python]\ndef hello():\n    pass\ncode::[-]\n')
        assert '<pre>' in r
        assert 'hello' in r

    def test_cpp_code_block(self):
        r = lhtml.run('\ncode::[c++]\nint x = 0;\ncode::[-]\n')
        assert '<pre>' in r

    def test_text_code_block(self):
        r = lhtml.run('\ncode::[text]\nplain text\ncode::[-]\n')
        assert 'plain text' in r


# ---------------------------------------------------------------------------
# Unnamed div (::() syntax)
# ---------------------------------------------------------------------------

class TestUnnamedDiv:
    def test_unnamed_div_with_class(self):
        r = lhtml.run('\n::(.highlight)[padding:10px;]\ncontent\n::\n')
        assert 'class="highlight"' in r
        assert 'style="padding:10px;"' in r
        assert 'content' in r

    def test_unnamed_div_style_only(self):
        r = lhtml.run('\n::[color:red;]\ntext\n::\n')
        assert '<div style="color:red;">' in r

    def test_unnamed_div_wrapping_list(self):
        r = lhtml.run('\n::(.box)\n* item one\n* item two\n::\n')
        assert 'class="box"' in r
        assert '<ul>' in r
        assert '<li>' in r


# ---------------------------------------------------------------------------
# Inline close (:: on same line)
# ---------------------------------------------------------------------------

class TestInlineClose:
    def test_empty_div_inline_close(self):
        r = lhtml.run('\ndiv::[height:25px;]::\n')
        assert '<div style="height:25px;"></div>' in r

    def test_span_inline_close_with_class(self):
        r = lhtml.run('\nspan::(.tag)[color:white;] label ::\n')
        assert '<span class="tag" style="color:white;"> label </span>' in r

    def test_unnamed_inline_close(self):
        r = lhtml.run('\n::[margin:5px;]::\n')
        assert '<div style="margin:5px;"></div>' in r


# ---------------------------------------------------------------------------
# Complex nesting
# ---------------------------------------------------------------------------

class TestComplexNesting:
    def test_nested_divs_three_levels(self):
        r = lhtml.run('\n::[padding:20px;]\n::[background:#eee;]\ndiv::[color:red;] deep ::\n::\n::\n')
        assert '<div style="padding:20px;">' in r
        assert '<div style="background:#eee;">' in r
        assert '<div style="color:red;"> deep </div>' in r
        assert r.count('</div>') == 3

    def test_formatting_inside_nested_div(self):
        r = lhtml.run('\n::[border:1px solid;]\n**bold** and __italic__\n::\n')
        assert '<strong>bold</strong>' in r
        assert '<em>italic</em>' in r
        assert '<div style="border:1px solid;">' in r

    def test_link_inside_div(self):
        r = lhtml.run('\n::[padding:5px;]\nlink::https://example.com[click]\n::\n')
        assert '<a href="https://example.com">click</a>' in r


# ---------------------------------------------------------------------------
# Mixed content (real-world patterns)
# ---------------------------------------------------------------------------

class TestMixedContent:
    def test_heading_with_bold(self):
        r = lhtml.run('\n= Title with **bold** word\n')
        assert '<h1>Title with <strong>bold</strong> word</h1>' in r

    def test_list_with_inline_code(self):
        r = lhtml.run('\n* Use `printf` to print\n')
        assert '<li>' in r
        assert '<code class="code-inline">printf</code>' in r

    def test_list_with_link(self):
        r = lhtml.run('\n* See link::https://example.com[docs]\n')
        assert '<li>' in r
        assert '<a href="https://example.com">docs</a>' in r

    def test_code_inside_styled_div(self):
        r = lhtml.run('\n::[font-size:80%;]\ncode::[c++]\nint x;\ncode::[-]\n::\n')
        assert '<div style="font-size:80%;">' in r
        assert '<pre>' in r

    def test_raw_html_passthrough_with_lhtml(self):
        r = lhtml.run('\n<p>HTML</p>\ndiv::[color:red;] lhtml ::\n')
        assert '<p>HTML</p>' in r
        assert '<div style="color:red;"> lhtml </div>' in r


# ---------------------------------------------------------------------------
# Non-regression: real-world lab_website examples
# ---------------------------------------------------------------------------

class TestLabWebsite:
    @pytest.fixture
    def lab_files(self):
        base = os.path.join(
            os.path.dirname(__file__), '..', '..', 'examples_references',
            'lab_website', 'csc_43043_ep_lab_website', '_site', 'content',
        )
        files = glob.glob(os.path.join(base, '**', '*.l.html'), recursive=True)
        return files

    def test_all_lab_files_compile(self, lab_files):
        if not lab_files:
            pytest.skip('Lab website examples not found')
        for f in lab_files:
            with open(f) as fid:
                txt = fid.read()
            if not txt.endswith('\n'):
                txt += '\n'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                html = lhtml.run(txt)
            assert len(html) > 0, f'Empty output for {f}'


# ---------------------------------------------------------------------------
# Regression tests for bugs fixed in 2.3.0
# ---------------------------------------------------------------------------

def _run_with_warnings(text, **options):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        result = lhtml.run(text, **options)
    return result, [str(x.message) for x in w]


class TestTagAtDocumentStart:
    def test_anonymous_div_first_character(self):
        r, w = _run_with_warnings('::[color:red;]\nhi\n::\n')
        assert r == '<div style="color:red;">\nhi\n</div>\n'
        assert w == []

    def test_named_div_first_character(self):
        r = lhtml.run('div::[color:red;] hi ::\n')
        assert r == '<div style="color:red;"> hi </div>\n'


class TestTagBoundaries:
    def test_python_slice_untouched(self):
        assert lhtml.run('x = a[::2]\n') == 'x = a[::2]\n'

    def test_python_slice_in_inline_code(self):
        r = lhtml.run('Use `a[::2]` here\n')
        assert r == 'Use <code class="code-inline">a[::2]</code> here\n'

    def test_cpp_nested_namespace_untouched(self):
        assert lhtml.run('std::chrono::seconds\n') == 'std::chrono::seconds\n'

    def test_tag_name_glued_to_word_untouched(self):
        assert lhtml.run('obj.link::x[y]\n') == 'obj.link::x[y]\n'

    def test_link_inside_brackets(self):
        r = lhtml.run('[link::page.html[Doc]]\n')
        assert r == '[<a href="page.html">Doc</a>]\n'

    def test_link_after_bold_and_quotes(self):
        r = lhtml.run('**link::a.html[A]** "link::b.html[B]"\n')
        assert r == '<strong><a href="a.html">A</a></strong> "<a href="b.html">B</a>"\n'

    def test_closing_glued_to_html_tag(self):
        r = lhtml.run('<p>Raw div::[color:blue;] lhtml ::</p>\n')
        assert r == '<p>Raw <div style="color:blue;"> lhtml </div></p>\n'

    def test_spacer_glued_to_html_tag(self):
        r = lhtml.run('<a href="x">x</a>::nl\n')
        assert r == '<a href="x">x</a><div style="height:1em;"></div>\n'

    def test_img_source_stops_at_html_tag(self):
        r = lhtml.run('img::a.jpg<br>\n')
        assert r == '<img src="a.jpg" alt="a.jpg"><br>\n'


class TestTagNames:
    def test_plugin_name_with_digit_dash_underscore(self):
        tags = {name: lhtml.Tag(lambda written, name=name: lhtml.Raw(f'<{name}/>'))
                for name in ('h2', 'my-tag', 'my_tag')}
        assert lhtml.run('h2::x my-tag::y my_tag::z\n', tags=tags) == '<h2/> <my-tag/> <my_tag/>\n'

    def test_unknown_name_with_digit_passes_through(self):
        r, _ = _run_with_warnings('h2::[color:red;] Titre\n')
        assert r == 'h2::[color:red;] Titre\n'

    def test_link_with_dash_text_is_not_a_closing_tag(self):
        r, w = _run_with_warnings('link::page.html[-]\n')
        assert r == '<a href="page.html">-</a>\n'
        assert w == []

    def test_builtin_tags_registered(self):
        assert {'div', 'span', 'link', 'img', 'video', 'videoplay'} <= set(lhtml.TAGS)


class TestInlineCode:
    def test_no_bold_or_italic_inside(self):
        r = lhtml.run('Call `__init__` and `x**2**y`\n')
        assert '<em>' not in r and '<strong>' not in r
        assert r == ('Call <code class="code-inline">__init__</code> and '
                     '<code class="code-inline">x**2**y</code>\n')

    def test_html_escaped(self):
        r = lhtml.run('`std::vector<float> v; if (a<b && c>d)`\n')
        assert r == ('<code class="code-inline">std::vector&lt;float&gt; v; '
                     'if (a&lt;b && c&gt;d)</code>\n')

    def test_existing_entities_kept(self):
        r = lhtml.run('`#include &lt;cstdint&gt;`\n')
        assert r == '<code class="code-inline">#include &lt;cstdint&gt;</code>\n'

    def test_tags_are_literal(self):
        r = lhtml.run('`link::https://x.org/a.hpp[a.hpp]`\n')
        assert r == '<code class="code-inline">link::https://x.org/a.hpp[a.hpp]</code>\n'

    def test_dollar_not_math(self):
        r = lhtml.run('`$x$` and **bold**\n')
        assert r == '<code class="code-inline">$x$</code> and <strong>bold</strong>\n'

    def test_unclosed_paren_after_colons(self):
        r, w = _run_with_warnings('Note `foo::bar(x` ok\n')
        assert r == 'Note <code class="code-inline">foo::bar(x</code> ok\n'


class TestRawHtmlProtection:
    def test_css_pseudo_elements_in_style(self):
        src = "<style>\n ::selection {color:red}\np ::before{content:'x'}\n</style>\n"
        assert lhtml.run(src) == src

    def test_script_untouched(self):
        src = '<script>\nlet s = `a**b**c`; x = y__z__w;\n* not a list\n= not a title\n</script>\n'
        assert lhtml.run(src) == src

    def test_html_comment_untouched(self):
        src = '<!-- **x** div::[a] __y__ -->\n'
        assert lhtml.run(src) == src

    def test_attribute_values_untouched(self):
        src = '<a href="https://x.org/a__b__c?q=**s**">l</a>\n'
        assert lhtml.run(src) == src

    def test_text_between_html_tags_processed(self):
        assert lhtml.run('<p>**bold**</p>\n') == '<p><strong>bold</strong></p>\n'


class TestMath:
    def test_dollar_is_text(self):
        assert lhtml.run('$x**2 + y**2$ costs $5\n') == '$x<strong>2 + y</strong>2$ costs $5\n'

    def test_inline_paren(self):
        assert lhtml.run(r'\(a_1 + a__b__\)' + '\n') == r'\(a_1 + a__b__\)' + '\n'

    def test_display_math(self):
        src = '\\[\n\\sum_i x_i**2\n\\]\n\\[ a__b__ \\]\n'
        assert lhtml.run(src) == src

    def test_formatting_outside_math(self):
        r = lhtml.run('**bold** $x**2$ __it__\n')
        assert r == '<strong>bold</strong> $x**2$ <em>it</em>\n'

    def test_prices_are_not_math(self):
        r = lhtml.run('costs $5 and **bold** $10\n')
        assert r == 'costs $5 and <strong>bold</strong> $10\n'


class TestYamlFrontMatter:
    """LHTML reads no front matter (3.0): its options come from the caller."""

    def test_separators_in_document_kept(self):
        src = 'Intro\n---\nmiddle\n---\nend\n'
        assert lhtml.run(src) == src

    def test_front_matter_is_text(self):
        src = '---\ntitle: T\nwrap-auto: true\n---\nbody\n'
        assert lhtml.run(src) == src


class TestCodeBlockLanguages:
    def test_empty_language(self):
        r, w = _run_with_warnings('code::[]\nabc\ncode::[-]\n')
        assert '<pre>' in r and 'abc' in r
        assert w == []

    def test_unknown_language_warns(self):
        r, w = _run_with_warnings('code::[foolang]\nabc\ncode::[-]\n')
        assert '<pre>' in r and 'abc' in r
        assert any('foolang' in x for x in w)


class TestPlaceholders:
    def test_literal_placeholder_like_text(self):
        src = 'verbatim::[abc] code::[12] verbatim::[3]\n'
        r, _ = _run_with_warnings(src)
        assert r == src

class TestUnclosedTags:
    def test_unclosed_div_warns(self):
        r, w = _run_with_warnings('div::[x]\nhello\n')
        assert r == '<div style="x">\nhello\n'
        assert any('div:: is never closed' in x and 'div::[x]' in x for x in w)

    def test_closed_div_no_warning(self):
        _, w = _run_with_warnings('div::[x]\nhello\n::\n')
        assert w == []

    def test_extra_closing_warns_with_context(self):
        r, w = _run_with_warnings('hello\n::\n')
        assert r == 'hello\n::\n'
        assert any('closes nothing: no element is open' in x for x in w)

    @pytest.mark.parametrize('source, expected', [
        ('a :: b', 'a :: b'),
        ('span::[c] x :: y ::', '<span style="c"> x </span> y ::'),
    ])
    def test_unmatched_closing_is_kept_as_text(self, source, expected):
        r, w = _run_with_warnings(source)
        assert r == expected
        assert any('closes nothing: no element is open' in x for x in w)


class TestAttributeEscaping:
    def test_quotes_in_style(self):
        r = lhtml.run('div::[font-family:"Arial";] x ::\n')
        assert r == '<div style="font-family:&quot;Arial&quot;;"> x </div>\n'

    def test_quotes_in_img_src(self):
        r = lhtml.run('img::a"b.jpg\n')
        assert 'src="a&quot;b.jpg"' in r


class TestIncludeRemoved:
    """include:: was removed in 3.0: LHTML reads no file."""

    def test_include_raises_with_the_jinja_way(self):
        with pytest.raises(lhtml.LHTMLParseError) as e:
            lhtml.run('include::part.html\n')
        assert 'include::part.html' in str(e.value) and '{% include "part.html" %}' in str(e.value)

    def test_include_inside_code_block_raises(self):
        # LHTML 2 expanded it; reading it as text would change the output silently
        with pytest.raises(lhtml.LHTMLParseError):
            lhtml.run('code::[text]\ninclude::a.hpp\ncode::[-]\n')

    def test_include_glued_to_a_word_is_text(self):
        assert lhtml.run('xinclude::b.html\n') == 'xinclude::b.html\n'


class TestCli:
    def _run_cli(self, monkeypatch, capsys, *args):
        from lhtml import cli
        monkeypatch.setattr('sys.argv', ['lhtml', *args])
        code = 0
        try:
            cli.main()
        except SystemExit as e:
            code = e.code
        out = capsys.readouterr()
        return code, out.out, out.err

    def test_stdout_single_trailing_newline(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / 'a.l.html'
        f.write_text('**A**\n')
        code, out, _ = self._run_cli(monkeypatch, capsys, str(f))
        assert code == 0
        assert out == '<strong>A</strong>\n'

    def test_two_inputs_of_the_same_name_are_refused_before_writing(self, tmp_path, monkeypatch, capsys):
        for d in ('a', 'b'):
            (tmp_path / d).mkdir()
            (tmp_path / d / 'page.l.html').write_text(d.upper())
        out = tmp_path / 'out'
        code, _, err = self._run_cli(monkeypatch, capsys, str(tmp_path / 'a/page.l.html'),
                                     str(tmp_path / 'b/page.l.html'), '-o', str(out) + '/')
        assert code == 1 and 'would both be written to' in err
        assert not (out / 'page.html').exists()

    def test_names_differing_by_case_are_one_output(self, tmp_path, monkeypatch, capsys):
        for d, name in (('a', 'Page.l.html'), ('b', 'page.l.html')):
            (tmp_path / d).mkdir()
            (tmp_path / d / name).write_text(d.upper())
        code, _, err = self._run_cli(monkeypatch, capsys, str(tmp_path / 'a/Page.l.html'),
                                     str(tmp_path / 'b/page.l.html'), '-o', str(tmp_path / 'out') + '/')
        # one file on a file system without case (macOS, Windows): refused everywhere
        assert code == 1 and 'would both be written to' in err and 'nothing written' in err
        assert not (tmp_path / 'out').exists()

    def test_one_input_named_in_two_cases_is_one(self, tmp_path, monkeypatch, capsys):
        (tmp_path / 'a').mkdir()
        (tmp_path / 'a/Page.l.html').write_text('= A\n')
        if not (tmp_path / 'a/page.l.html').exists():
            pytest.skip('a file system with case')
        code, _, err = self._run_cli(monkeypatch, capsys, str(tmp_path / 'a/Page.l.html'),
                                     str(tmp_path / 'a/page.l.html'), '-o', str(tmp_path / 'out') + '/')
        assert code == 0, err

    def test_a_missing_or_repeated_input_is_no_collision(self, tmp_path, monkeypatch, capsys):
        (tmp_path / 'a').mkdir()
        (tmp_path / 'a/x.l.html').write_text('= A\n')
        out = str(tmp_path / 'out') + '/'
        code, _, err = self._run_cli(monkeypatch, capsys, str(tmp_path / 'nope/x.l.html'),
                                     str(tmp_path / 'a/x.l.html'), '-o', out)
        assert code == 1 and 'file not found' in err and 'would both' not in err
        assert not (tmp_path / 'out').exists()             # checked before any is written
        code, _, err = self._run_cli(monkeypatch, capsys, str(tmp_path / 'a/x.l.html'),
                                     str(tmp_path / 'a/x.l.html'), '-o', out)
        assert code == 0, err

    def test_missing_file_is_an_error(self, tmp_path, monkeypatch, capsys):
        code, out, err = self._run_cli(monkeypatch, capsys, str(tmp_path / 'nope.l.html'))
        assert code == 1
        assert out == ''
        assert 'file not found' in err

    def test_multiple_inputs_require_output_directory(self, tmp_path, monkeypatch, capsys):
        a, b = tmp_path / 'a.l.html', tmp_path / 'b.l.html'
        a.write_text('= A\n')
        b.write_text('= B\n')
        code, _, err = self._run_cli(monkeypatch, capsys, str(a), str(b),
                                     '-o', str(tmp_path / 'out.html'))
        assert code == 2
        assert not (tmp_path / 'out.html').exists()

    def test_multiple_inputs_to_directory(self, tmp_path, monkeypatch, capsys):
        a, b = tmp_path / 'a.l.html', tmp_path / 'b.l.html'
        a.write_text('= A\n')
        b.write_text('= B\n')
        code, _, _ = self._run_cli(monkeypatch, capsys, str(a), str(b),
                                   '-o', str(tmp_path / 'build') + '/')
        assert code == 0
        assert (tmp_path / 'build' / 'a.html').read_text() == '<h1>A</h1>\n\n'
        assert (tmp_path / 'build' / 'b.html').read_text() == '<h1>B</h1>\n\n'

    def test_lhtml_error_reported_without_traceback(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / 'a.l.html'
        f.write_text('include::missing.html\n')
        code, _, err = self._run_cli(monkeypatch, capsys, str(f))
        assert code == 1
        assert 'missing.html' in err and 'Traceback' not in err

    def test_video_poster_is_not_probed(self, tmp_path, monkeypatch, capsys):
        (tmp_path / 'assets').mkdir()
        (tmp_path / 'assets' / 'v-poster.jpg').write_bytes(b'')
        f = tmp_path / 'a.l.html'
        f.write_text('video::assets/v.mp4\n')
        code, out, _ = self._run_cli(monkeypatch, capsys, str(f))
        assert code == 0 and 'poster=' not in out


# ---------------------------------------------------------------------------
# Regression tests for issues found by automated bug hunting (2.3.0)
# ---------------------------------------------------------------------------

class TestCodeAndVerbatimBlocks:
    def test_verbatim_markers_inside_code_block_shown_as_code(self):
        r, _ = _run_with_warnings('code::[python]\nverbatim::[]x verbatim::[-]\ncode::[-]\n')
        assert '\x00' not in r
        assert 'verbatim' in r and '<pre>' in r

    def test_code_opener_glued_to_text(self):
        r = lhtml.run('values code::[text]\nabc\ncode::[-]\nafter **b**\n')
        assert '<pre>' in r and '<strong>b</strong>' in r

    def test_word_ending_with_code_is_not_a_block(self):
        src = 'the bytecode::Instr type\n'
        assert lhtml.run(src) == src

    def test_code_directives_in_inline_code_are_text(self):
        r = lhtml.run('Write `code::[c++]` then `code::[-]`.\n')
        assert r == ('Write <code class="code-inline">code::[c++]</code> then '
                     '<code class="code-inline">code::[-]</code>.\n')

    def test_text_glued_after_language_is_kept(self):
        r = lhtml.run('code::[text]x = 1\ncode::[-]\n')
        assert 'x = 1' in r

    def test_unclosed_language_bracket_does_not_crash(self):
        r, _ = _run_with_warnings('code::[python\nx\ncode::[-]\n')
        assert 'x' in r



class TestProtectionOrder:
    def test_script_tag_in_inline_code(self):
        r = lhtml.run('Use `<script>` to start and `</script>` to end.\n')
        assert r == ('Use <code class="code-inline">&lt;script&gt;</code> to start and '
                     '<code class="code-inline">&lt;/script&gt;</code> to end.\n')

    def test_comment_markers_in_inline_code(self):
        r = lhtml.run('`<!--` and `-->` **b**\n')
        assert '<strong>b</strong>' in r and '&lt;!--' in r

    def test_backquote_inside_html_attribute(self):
        src = '<a title="a`b">x</a> and `c`\n'
        assert lhtml.run(src) == '<a title="a`b">x</a> and <code class="code-inline">c</code>\n'

    def test_comparison_operators_do_not_hide_lists(self):
        r = lhtml.run('for i<n we have\n* item one\n* item two\nthen p->x\n')
        assert '<ul>' in r and r.count('<li>') == 2

    def test_greater_than_inside_quoted_attribute(self):
        src = '<span title="a > b __c__">t</span> <img alt="2 > 1 **x**">\n'
        assert lhtml.run(src) == src

    def test_arrow_function_in_event_handler(self):
        src = '<button onclick="f(() => g(\'__a__\'))">b</button>\n'
        assert lhtml.run(src) == src

    def test_nul_character_in_input(self):
        r = lhtml.run('a \x00R0\x00 b <b title="\x00R0\x00">x</b>\n')
        assert '\x00' not in r and 'a �R0� b' in r


class TestDirectivesInProtectedZones:
    def test_include_in_html_comment_ignored(self):
        src = '<!-- include::missing.html -->\n'
        assert lhtml.run(src) == src

    def test_include_in_inline_code_ignored(self):
        r = lhtml.run('Use `include::header.html` here\n')
        assert r == 'Use <code class="code-inline">include::header.html</code> here\n'

    def test_include_glued_to_word_ignored(self):
        src = 'xinclude::b.html\n'
        assert lhtml.run(src) == src

    def test_comment_marker_in_html_comment(self):
        src = '<!-- old: ::# note -->\ntext\n'
        assert lhtml.run(src) == src

    def test_comment_marker_in_code_block(self):
        r = lhtml.run('code::[text]\na::#b;\ncode::[-]\n')
        assert 'a::#b;' in r

    def test_anchor_link_is_not_a_comment(self):
        r = lhtml.run('See link::#intro[the intro] for details.\n')
        assert r == 'See <a href="#intro">the intro</a> for details.\n'

    def test_comment_in_url_attribute(self):
        src = '<a href="page.html::#x">y</a>\n'
        assert lhtml.run(src) == src


class TestUrls:
    def test_underscores_in_link_url(self):
        r = lhtml.run('link::https://docs.python.org/x.html#object.__init__[init] and __c__\n')
        assert r == ('<a href="https://docs.python.org/x.html#object.__init__">init</a> '
                     'and <em>c</em>\n')

    def test_underscores_in_img_src(self):
        r = lhtml.run('img::assets/my__img__x.png[width:5px]\n')
        assert 'src="assets/my__img__x.png"' in r

    def test_parentheses_in_url(self):
        r = lhtml.run('link::https://en.wikipedia.org/wiki/Mercury_(planet)[Mercury]\n')
        assert r == '<a href="https://en.wikipedia.org/wiki/Mercury_(planet)">Mercury</a>\n'

    def test_parentheses_in_image_name(self):
        r = lhtml.run('img::assets/fig(1).png\n')
        assert 'src="assets/fig(1).png"' in r

    def test_class_group_after_url(self):
        r = lhtml.run('link::page.html(.nav)[Back]\n')
        assert r == '<a class="nav" href="page.html">Back</a>\n'

    def test_math_like_text_in_url(self):
        r = lhtml.run('link::https://x.com/$a$[t]\n')
        assert r == '<a href="https://x.com/$a$">t</a>\n'


class TestNestedBrackets:
    def test_nested_square_brackets_in_link_text(self):
        r = lhtml.run('link::http://a.com[ [R. B., SCA] ]\n')
        assert r == '<a href="http://a.com"> [R. B., SCA] </a>\n'

    def test_nested_braces_in_attributes(self):
        r = lhtml.run('div::{onclick="f({a:1})"} x ::\n')
        assert r == '<div onclick="f({a:1})"> x </div>\n'

    def test_deep_nesting_does_not_crash(self):
        r, _ = _run_with_warnings('div::[' + '[' * 600 + ']' * 600 + '] x ::\n')
        assert isinstance(r, str)


class TestBareTagEdgeCases:
    def test_closing_glued_to_bold(self):
        r = lhtml.run('**span::[c] x ::** after\n')
        assert r == '<strong><span style="c"> x </span></strong> after\n'

    def test_closing_followed_by_punctuation(self):
        r = lhtml.run('This is span::(.red) important ::, and more\n')
        assert r == 'This is <span class="red"> important </span>, and more\n'

    def test_closing_at_end_of_heading(self):
        r = lhtml.run('= Title span::[c] x ::\n')
        assert r == '<h1>Title <span style="c"> x </span></h1>\n\n'

    def test_spacer_followed_by_tag(self):
        r, w = _run_with_warnings('::nl::[text-align:center]\nimg::a.png[w]\n::\n')
        assert r == ('<div style="height:1em;"></div><div style="text-align:center">\n'
                     '<img style="w" src="a.png" alt="a.png">\n</div>\n')
        assert w == []

    def test_spacer_followed_by_punctuation_or_parenthesis(self):
        assert lhtml.run('::nl.\n') == '<div style="height:1em;"></div>.\n'
        assert lhtml.run('::nl(x)\n') == '<div style="height:1em;"></div>(x)\n'

    def test_closing_then_empty_div(self):
        r, w = _run_with_warnings('div::[x]\nA\n:: ::[height:1em;]::\n')
        assert r == '<div style="x">\nA\n</div> <div style="height:1em;"></div>\n'
        assert w == []

    @pytest.mark.parametrize('source', ['in {0, 1, 2}:::nl\n', 'a ::::[x] b\n'])
    def test_three_colons_or_more_are_text(self, source):
        r, w = _run_with_warnings(source)
        assert r == source and w == []

    def test_scope_operator_between_html_tags(self):
        src = '<span>std</span><span>::</span><span>cout</span>\n'
        r, w = _run_with_warnings(src)
        assert r == src and w == []

    def test_scope_operator_after_inline_code(self):
        src = '`std`::vector\n'
        assert lhtml.run(src) == '<code class="code-inline">std</code>::vector\n'

    def test_bare_colons_in_inline_code(self):
        r, w = _run_with_warnings('call `::glfwInit()` and `a[:, ::2]` and `::`\n')
        assert r == ('call <code class="code-inline">::glfwInit()</code> and '
                     '<code class="code-inline">a[:, ::2]</code> and '
                     '<code class="code-inline">::</code>\n')
        assert w == []

    def test_unclosed_paren_in_non_tag_does_not_warn_with_placeholder(self):
        _, w = _run_with_warnings('std::max(a, b `x`\n')
        assert all('\x00' not in x for x in w)


class TestPluginReadmeExample:
    def test_alert_example(self):
        import dataclasses

        def alert_element(written):
            attributes = dataclasses.replace(written, parentheses='.alert ' + written.parentheses).attributes
            return lhtml.Element('div', attributes, children=[lhtml.Text(written.text)])
        alert = lhtml.Tag(alert_element, container=True)
        r = lhtml.run('alert::[background:yellow; padding:10px;] Warning message ::\n',
                      tags={'alert': alert})
        assert r == '<div class="alert" style="background:yellow; padding:10px;"> Warning message </div>\n'
        seen = []
        lhtml.run('spy::(.c)[s]{a=1}w', tags={'spy': lhtml.Tag(lambda written: seen.append(written) or [])})
        assert seen[0] == lhtml.Written('spy', 'w', False, '.c', 's', 'a=1', None, 1, 1, 'spy::(.c)[s]{a=1}w')


# ---------------------------------------------------------------------------
# Robustness: encodings, line endings, CLI, wrapper (2.3.0)
# ---------------------------------------------------------------------------

class TestInputNormalization:
    def test_crlf_with_options(self):
        r = lhtml.wrap(lhtml.run('= T\r\nx\r\n'), title='A')
        assert '<title>A</title>' in r and '<h1>T</h1>' in r and '\r' not in r

    def test_crlf_heading_has_no_carriage_return(self):
        assert lhtml.run('= T\r\n') == '<h1>T</h1>\n\n'

    def test_bom_removed(self):
        assert lhtml.run('\ufeff**x**\n') == '<strong>x</strong>\n'

    def test_source_read_as_utf8_without_bom(self, tmp_path, monkeypatch):
        (tmp_path / 'a.l.html').write_bytes('\ufeffé ” ü\r\n'.encode('utf-8'))
        monkeypatch.setattr('locale.getpreferredencoding', lambda *a, **k: 'cp1252')
        from lhtml.cli import read_source
        assert read_source(str(tmp_path / 'a.l.html')) == 'é ” ü\n'

    def test_non_string_current_directory(self):
        r = lhtml.run('---\ncurrent_directory: 5\n---\nvideo::a.mp4\n')
        assert '<video' in r


class TestWrapAndMisc:
    def test_wrapper_escapes_title_and_paths(self):
        r = lhtml.wrap(lhtml.run('x'), title='A </title> & B', css='a".css')
        assert '<title>A &lt;/title&gt; &amp; B</title>' in r
        assert 'href="a&quot;.css"' in r

    def test_code_language_case_insensitive_custom_lexer(self):
        upper = lhtml.run('code::[C++]\nvec3 v;\ncode::[-]\n')
        lower = lhtml.run('code::[ c++ ]\nvec3 v;\ncode::[-]\n')
        assert upper == lower == lhtml.run('code::[c++]\nvec3 v;\ncode::[-]\n')

    def test_video_mime_type(self):
        r = lhtml.run('video::clip.MP4?v=2\n')
        assert 'type="video/mp4"' in r


class TestCliRobustness:
    _run_cli = TestCli._run_cli

    def test_non_utf8_file_does_not_stop_the_batch(self, tmp_path, monkeypatch, capsys):
        bad, good = tmp_path / 'bad.l.html', tmp_path / 'good.l.html'
        bad.write_bytes('caf\xe9\n'.encode('latin-1'))
        good.write_text('**ok**\n')
        code, _, err = self._run_cli(monkeypatch, capsys, str(bad), str(good),
                                     '-o', str(tmp_path / 'out') + '/')
        assert code == 1
        assert 'bad.l.html' in err and 'Traceback' not in err
        assert (tmp_path / 'out' / 'good.html').read_text() == '<strong>ok</strong>\n'

    def test_output_file_in_missing_directory(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / 'a.l.html'
        f.write_text('**a**\n')
        code, _, _ = self._run_cli(monkeypatch, capsys, str(f), '-o', str(tmp_path / 'new' / 'a.html'))
        assert code == 0
        assert (tmp_path / 'new' / 'a.html').read_text() == '<strong>a</strong>\n'

    def test_never_overwrites_input(self, tmp_path, monkeypatch, capsys):
        page, other = tmp_path / 'page.html', tmp_path / 'other.html'
        page.write_text('**p**\n')
        other.write_text('**o**\n')
        code, _, err = self._run_cli(monkeypatch, capsys, str(page), str(other))
        assert code == 1
        assert 'overwrite' in err
        assert page.read_text() == '**p**\n' and other.read_text() == '**o**\n'

    def test_utf8_output_and_bom_input(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / 'a.l.html'
        f.write_bytes('\ufeff**é**\n'.encode('utf-8'))
        out = tmp_path / 'a.html'
        code, _, _ = self._run_cli(monkeypatch, capsys, str(f), '-o', str(out))
        assert code == 0
        assert out.read_bytes() == '<strong>é</strong>\n'.encode('utf-8')

    def test_warnings_name_the_file_and_are_not_deduplicated(self, tmp_path, monkeypatch, capsys):
        a, b = tmp_path / 'e1.l.html', tmp_path / 'e2.l.html'
        a.write_text('x\n::\n')
        b.write_text('x\n::\n')
        code, _, err = self._run_cli(monkeypatch, capsys, str(a), str(b),
                                     '-o', str(tmp_path / 'out') + '/')
        assert code == 0
        assert err.count(':2:1: warning: this :: closes nothing: no element is open') == 2
        assert f'{a}:2:1: warning:' in err and f'{b}:2:1: warning:' in err



# ---------------------------------------------------------------------------
# Line breaks option (-b / line-breaks)
# ---------------------------------------------------------------------------

class TestLineBreaks:
    ON = {'line_breaks': True}

    def test_disabled_by_default(self):
        assert lhtml.run('a\nb\n\nc\n') == 'a\nb\n\nc\n'

    def test_basic_with_blank_line(self):
        r = lhtml.run('Ligne 1\nLigne 2\n\nAutre paragraphe\n', **self.ON)
        assert r == 'Ligne 1<br>\nLigne 2<br>\n<br>\nAutre paragraphe\n'

    def test_leading_and_trailing_blank_lines_ignored(self):
        assert lhtml.run('\n\na\nb\n\n\n', **self.ON) == '\n\na<br>\nb\n\n\n'

    def test_no_break_around_heading_and_list(self):
        r = lhtml.run('= Titre\n\nTexte a\nTexte b\n\n* item 1\n* item 2\n\nfin\n', **self.ON)
        assert r == ('<h1>Titre</h1>\n\n\nTexte a<br>\nTexte b\n\n'
                     '<ul>\n<li>\nitem 1\n</li>\n<li>\nitem 2\n</li>\n</ul>\n\nfin\n')

    def test_breaks_inside_div_but_not_around(self):
        r = lhtml.run('div::[x]\nl1\nl2\n::\napres\n::nl\nb\n', **self.ON)
        assert r == ('<div style="x">\nl1<br>\nl2\n</div>\napres\n'
                     '<div style="height:1em;"></div>\nb\n')

    def test_no_break_after_block_end(self):
        # closing :: on its own line, at the end of a text line, or followed by text
        assert lhtml.run('div::[x]\ntexte\n::\nsuite\n', **self.ON) == \
            '<div style="x">\ntexte\n</div>\nsuite\n'
        assert lhtml.run('div::[x]\ntexte ::\nsuite\n', **self.ON) == \
            '<div style="x">\ntexte </div>\nsuite\n'
        assert lhtml.run('div::[x]\na\n:: b\nc\n', **self.ON) == \
            '<div style="x">\na\n</div> b\nc\n'
        # raw HTML block end, blank line after it ignored
        assert lhtml.run('<div>\na\n</div>\n\nb\n', **self.ON) == '<div>\na\n</div>\n\nb\n'
        assert lhtml.run('x\n</p>\ny\n</ul>\nz\n', **self.ON) == 'x\n</p>\ny\n</ul>\nz\n'

    def test_inline_elements_are_text(self):
        r = lhtml.run('Use **gras** et span::[c] s :: ici\nsuite `code` link::u[l]\n', **self.ON)
        assert r == ('Use <strong>gras</strong> et <span style="c"> s </span> ici<br>\n'
                     'suite <code class="code-inline">code</code> <a href="u">l</a>\n')

    def test_protected_blocks_untouched(self):
        src = ('avant\ncode::[text]\na\nb\ncode::[-]\n'
               '<script>\nx\ny\n</script>\n'
               '\\[\nm1\nm2\n\\]\n'
               '<!--\nc1\nc2\n-->\napres\n')
        r = lhtml.run(src, **self.ON)
        assert '<br>' not in r

    def test_existing_br_not_doubled(self):
        assert lhtml.run('a<br>\nb\n', **self.ON) == 'a<br>\nb\n'

    def test_raw_block_html(self):
        r = lhtml.run('<p>\nx\ny\n</p>\n', **self.ON)
        assert r == '<p>\nx<br>\ny\n</p>\n'

    def test_images_one_per_line_are_stacked(self):
        r = lhtml.run('img::a.jpg\nimg::b.jpg\nvideo::c.mp4\nfin\n', **self.ON)
        assert r.startswith('<img src="a.jpg" alt="a.jpg"><br>\n<img src="b.jpg" alt="b.jpg"><br>\n<video')
        assert r.endswith('</video><br>\nfin\n')
        assert '<source src="c.mp4" type="video/mp4">\n' in r

    def test_no_break_inside_pre(self):
        src = '<pre>\n**a** x\ny\n</pre>\nt\nu\n'
        assert lhtml.run(src, **self.ON) == '<pre>\n<strong>a</strong> x\ny\n</pre>\nt<br>\nu\n'

    def test_cli_flag(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / 'a.l.html'
        f.write_text('a\nb\n')
        for flag in ('-b', '--line-breaks'):
            code, out, _ = TestCli._run_cli(self, monkeypatch, capsys, flag, str(f))
            assert code == 0 and out == 'a<br>\nb\n'


class TestAuditRegressions:
    @pytest.mark.parametrize('source', [
        '<script>const s = "code::[]include::missing.txt code::[-]";</script>',
        '<style>p::before {content:"verbatim::[]**x**verbatim::[-]"}</style>',
        '<!-- code::[]include::missing.txt code::[-] -->',
        '<a title="code::[]include::missing.txt code::[-]">**label**</a>',
    ])
    def test_outer_zone_owns_block_directives(self, source):
        assert lhtml.run(source) == source.replace('**label**', '<strong>label</strong>')

    def test_inline_code_owns_block_directive_after_text(self):
        source = '`example code::[]include::missing.txt code::[-]`'
        assert lhtml.run(source) == '<code class="code-inline">' + source[1:-1] + '</code>'

    @pytest.mark.parametrize('source', [
        '<a\n href="page__draft__.html">**label**</a>',
        '<a title="first\n**second**"\n href="x">**label**</a>',
        '<input\n disabled\n data-path="__draft__">',
    ])
    def test_multiline_html_attributes(self, source):
        assert lhtml.run(source) == source.replace('**label**', '<strong>label</strong>')

    @pytest.mark.parametrize('source', [
        '{{ "page__draft__.html" }}',
        '{{ user.__class__.__name__ }}',
        '{% set path = "page__draft__.html" %}',
        '{# code::[]include::missing.txt code::[-] #}',
        '{{ "}} **literal**" }}',
        '{% set text = "%} __literal__" %}',
        '{{\n "__literal__"\n }}',
    ])
    def test_jinja_preserved_with_surrounding_formatting(self, source):
        assert lhtml.run('**before** ' + source + ' __after__') == (
            '<strong>before</strong> ' + source + ' <em>after</em>')

    @pytest.mark.parametrize('opening', ['{{', '{%'])
    def test_unclosed_jinja_with_quotes_is_fast(self, opening):
        source = opening + ' ' + 'il dit "oui" puis "non ' * 200 + '**b**'
        start = time.perf_counter()
        result = lhtml.run(source)
        assert time.perf_counter() - start < 1
        assert result.endswith('<strong>b</strong>')

    def test_styles_classes_and_inline_attributes_are_not_formatted(self):
        source = ('div::(.my__class__)[background:url(photo__small__x.png)]'
                  '{data-path="a__b__"} **content** ::')
        assert lhtml.run(source) == (
            '<div class="my__class__" style="background:url(photo__small__x.png)"'
            ' data-path="a__b__"> <strong>content</strong> </div>')

    def test_link_label_keeps_formatting_and_inline_code(self):
        assert lhtml.run('link::page__draft__.html(.my__class__)[**bold** `code`]') == (
            '<a class="my__class__" href="page__draft__.html">'
            '<strong>bold</strong> <code class="code-inline">code</code></a>')

    def test_attribute_quotes_are_escaped_after_restoring(self):
        assert lhtml.run('div::[font-family:"__font__"] x ::') == (
            '<div style="font-family:&quot;__font__&quot;"> x </div>')



class TestCliSourceProtection:
    _run_cli = TestCli._run_cli

    def test_batch_cannot_overwrite_another_input(self, tmp_path, monkeypatch, capsys):
        first, second, third = [tmp_path / name for name in
                                ('page.l.html', 'page.html', 'other.l.html')]
        first.write_text('= First\n')
        second.write_text('Original content\n')
        third.write_text('= Other\n')
        code, _, err = self._run_cli(monkeypatch, capsys, str(first), str(second), str(third))
        assert code == 1 and 'overwrite' in err and 'nothing written' in err
        assert first.read_text() == '= First\n'
        assert second.read_text() == 'Original content\n'
        assert not (tmp_path / 'other.html').exists()

    @pytest.mark.parametrize('alias_kind', ['symlink', 'hardlink'])
    def test_output_alias_cannot_overwrite_source(self, tmp_path, monkeypatch, capsys, alias_kind):
        source, destination = tmp_path / 'page.l.html', tmp_path / 'output.html'
        source.write_text('= Original\n')
        if alias_kind == 'symlink':
            destination.symlink_to(source)
        else:
            os.link(source, destination)
        code, _, err = self._run_cli(monkeypatch, capsys, str(source), '-o', str(destination))
        assert code == 1 and 'overwrite' in err
        assert source.read_text() == '= Original\n'


@pytest.mark.parametrize('statement', ['{% if visible %}', '{# comment #}'])
def test_jinja_statement_does_not_introduce_line_breaks(statement):
    source = 'before\n' + statement + '\nafter'
    assert lhtml.run(source, line_breaks=True) == source


class TestLineBreakRegressions:
    ON = {'line_breaks': True}

    @pytest.mark.parametrize('tag', ['pre', 'textarea'])
    @pytest.mark.parametrize('wrapper', [
        '<script>const s = "<{tag}>";</script>',
        '<!-- <{tag}> -->',
        '<span title="<{tag}>">label</span>',
        '{{ "<{tag}>" }}',
    ])
    def test_fake_preformatted_tag_does_not_disable_following_breaks(self, tag, wrapper):
        prefix = wrapper.replace('{tag}', tag)
        result = lhtml.run(prefix + '\none\ntwo', **self.ON)
        assert result.startswith(prefix)
        assert result.endswith('one<br>\ntwo')

    @pytest.mark.parametrize('tag', ['pre-view', 'textarea-widget'])
    def test_custom_element_is_not_preformatted(self, tag):
        source = f'<{tag}>one\ntwo</{tag}>\nthree\nfour'
        assert lhtml.run(source, **self.ON) == (
            f'<{tag}>one<br>\ntwo</{tag}><br>\nthree<br>\nfour')

    @pytest.mark.parametrize('tag', ['pre', 'textarea', 'PRE', 'TEXTAREA'])
    def test_real_preformatted_block_still_preserves_newlines(self, tag):
        source = f'<{tag}\n class="sample">\none\ntwo\n</{tag}>\nthree\nfour'
        assert lhtml.run(source, **self.ON) == source.replace('three\nfour', 'three<br>\nfour')

    def test_fake_close_in_comment_does_not_end_preformatted_block(self):
        source = '<pre>\n<!-- </pre> -->\none\ntwo\n</pre>\nthree\nfour'
        assert lhtml.run(source, **self.ON) == source.replace('three\nfour', 'three<br>\nfour')

    @pytest.mark.parametrize('statement', [
        '{%\n if visible\n%}',
        '{#\n a comment\n#}',
        '{%-\n set value = "text"\n-%}',
    ])
    def test_multiline_jinja_statement_is_structure(self, statement):
        source = 'one\ntwo\n' + statement + '\nthree\nfour'
        expected = 'one<br>\ntwo\n' + statement + '\nthree<br>\nfour'
        assert lhtml.run(source, **self.ON) == expected

    def test_multiline_jinja_expression_remains_inline(self):
        source = 'one {{\n value\n}}\ntwo'
        assert lhtml.run(source, **self.ON) == 'one {{\n value\n}}<br>\ntwo'


class TestJinjaInUrlsAndHeadings:
    @pytest.mark.parametrize('source, expected', [
        ('img::{{ url }}', '<img src="{{ url }}" alt="{{ url }}">'),
        ('img::{{ base }}/photo__small__.jpg[width:10px]',
         '<img style="width:10px" src="{{ base }}/photo__small__.jpg"'
         ' alt="{{ base }}/photo__small__.jpg">'),
        ('link::{{ url }}[**go**]', '<a href="{{ url }}"><strong>go</strong></a>'),
        ('link::/posts/{{ post.slug }}.html(.nav)[x]',
         '<a class="nav" href="/posts/{{ post.slug }}.html">x</a>'),
        ("link::{{ url_for('page', name='a b') }}[x]",
         "<a href=\"{{ url_for('page', name='a b') }}\">x</a>"),
    ])
    def test_jinja_expression_in_url(self, source, expected):
        assert lhtml.run(source) == expected

    def test_jinja_double_quotes_are_not_escaped_in_attributes(self):
        assert lhtml.run('link::{{ url_for("page") }}[x]') == (
            '<a href="{{ url_for("page") }}">x</a>')
        assert lhtml.run('div::[font-family:{{ font("a") }}; content:"x"] y ::') == (
            '<div style="font-family:{{ font("a") }}; content:&quot;x&quot;"> y </div>')

    def test_jinja_in_video_url(self):
        assert '<source src="{{ base }}/clip.mp4"' in lhtml.run('video::{{ base }}/clip.mp4')

    @pytest.mark.parametrize('source, expected', [
        ('=(.t__x__) Title', '<h1 class="t__x__">Title</h1>\n'),
        ('==(.a**b** #id__1__) **Bold** __it__',
         '<h2 class="a**b**" id="id__1__"><strong>Bold</strong> <em>it</em></h2>\n'),
        ('= Title (.not__class__)', '<h1>Title (.not<em>class</em>)</h1>\n'),
    ])
    def test_heading_classes_are_not_formatted(self, source, expected):
        assert lhtml.run(source) == expected

    @pytest.mark.parametrize('opening', ['{{', '{%'])
    def test_many_unclosed_jinja_delimiters_are_fast(self, opening):
        source = (opening + ' x ') * 20000 + '**b**'
        start = time.perf_counter()
        result = lhtml.run(source)
        assert time.perf_counter() - start < 1
        assert result.endswith('<strong>b</strong>')

    def test_jinja_delimiter_in_string_still_matches(self):
        assert lhtml.run('{{ "{{" }} __a__') == '{{ "{{" }} <em>a</em>'
        assert lhtml.run('{% set x = "{%" %} __a__') == '{% set x = "{%" %} <em>a</em>'


@pytest.mark.parametrize('source, expected', [
    ('videoplay::v.mp4[width:400px;]', '<video autoplay loop muted playsinline style="width:400px;">'),
    ('videoplay::v.mp4(.c)', '<video autoplay loop muted playsinline class="c">'),
    ('videoplay::v.mp4', '<video autoplay loop muted playsinline>'),
    ('video::v.mp4[width:400px;]', '<video style="width:400px;">'),
])
def test_video_opening_tag_spacing(source, expected):
    assert lhtml.run(source).startswith(expected + '\n')


@pytest.mark.parametrize('flag', ['--version', '-V'])
def test_cli_version(flag, monkeypatch, capsys):
    code, out, _ = TestCli._run_cli(None, monkeypatch, capsys, flag)
    assert code == 0
    assert out == f'lhtml {lhtml.__version__}\n'


def test_version_format():
    assert re.fullmatch(r'\d+\.\d+\.\d+', lhtml.__version__)


# ---------------------------------------------------------------------------
# Macros (custom :: tags declared in a configuration)
# ---------------------------------------------------------------------------

MACROS = {
    'small': {'class': 'small'},
    'credit': {'tag': 'span', 'class': 'credit'},
    'aside': {'class': 'aside'},
    'box': {'class': 'box'},
    'gap': {'class': 'gap', 'empty': True, 'variant': ['s', 'm', 'l'], 'default': 'm'},
    'demo': {'tag': 'iframe', 'class': 'demo', 'empty': True, 'url': 'src',
             'attrs': 'frameborder="0"'},
}


def _run_macros(text, macros=MACROS):
    return lhtml.run(text, macros=macros)


class TestMacros:

    def test_container(self):
        assert _run_macros('box::\nx\n::\n') == '<div class="box">\nx\n</div>\n'

    def test_inline_and_other_tag(self):
        assert _run_macros('credit:: Milo ::\n') == '<span class="credit"> Milo </span>\n'

    def test_classes_are_added(self):
        out = _run_macros('aside::(.wide #f)[top:400px;] x ::\n')
        assert out == '<div class="aside wide" id="f" style="top:400px;"> x </div>\n'

    def test_empty_with_variant(self):
        assert _run_macros('gap::\ngap::l\n') == ('<div class="gap gap-m"></div>\n'
                                                  '<div class="gap gap-l"></div>\n')

    def test_unknown_variant_warns(self):
        with pytest.warns(lhtml.LHTMLWarning, match='unknown variant'):
            out = _run_macros('gap::xl\n')
        assert out == '<div class="gap gap-xl"></div>\n'

    def test_url(self):
        out = _run_macros('demo::assets/ik/index.html#d2[height:700px;]\n')
        assert out == ('<iframe class="demo" style="height:700px;" '
                       'src="assets/ik/index.html#d2" frameborder="0"></iframe>\n')

    def test_not_active_inside_inline_code(self):
        assert _run_macros('`box:: gap::`\n') == '<code class="code-inline">box:: gap::</code>\n'

    def test_unknown_without_macros(self):
        assert lhtml.run('gap::\n') == 'gap::\n'

    def test_global_registry_unchanged(self):
        _run_macros('gap::\n')
        assert 'gap' not in lhtml.TAGS

    def test_macros_of_a_file_are_loaded_by_the_caller(self, tmp_path):
        (tmp_path / 'design.yaml').write_text('macros:\n  note: {class: note}\n', encoding='utf-8')
        out = lhtml.run('note:: hi ::\n', macros=lhtml.load_macros(tmp_path / 'design.yaml'))
        assert out.strip() == '<div class="note"> hi </div>'
        with pytest.raises(TypeError, match='load_macros'):
            lhtml.run('x', macros=str(tmp_path / 'design.yaml'))

    def test_later_definition_wins(self):
        out = lhtml.run('box:: x ::\n', macros=lhtml.load_macros([MACROS, {'box': {'class': 'frame'}}]))
        assert out == '<div class="frame"> x </div>\n'

    @pytest.mark.parametrize('macros', [
        {'div': {}}, {'nl': {}}, {'2x': {}}, {'box': {'colour': 'red'}},
        {'box': 'small'}, {'gap': {'variant': True}},
        {'box': {'class': ['a', 'b']}}, {'box': {'url': True}}, {'box': {'url': 'a b'}},
        {'box': {'empty': 'false'}}, {'box': {'tag': 'br', 'empty': False}},
        {'gap': {'class': 'gap', 'variant': [['s']]}}, {'macros': ['box']},
    ])
    def test_invalid_definitions(self, macros):
        with pytest.raises(lhtml.LHTMLMacroError):
            lhtml.run('x\n', macros=macros)

    def test_cli(self, tmp_path, monkeypatch, capsys):
        from lhtml import cli
        (tmp_path / 'm.yaml').write_text('box: {class: box}\n', encoding='utf-8')
        (tmp_path / 'p.l.html').write_text('box:: x ::\n', encoding='utf-8')
        monkeypatch.setattr('sys.argv', ['lhtml', '-m', str(tmp_path / 'm.yaml'),
                                         str(tmp_path / 'p.l.html')])
        cli.main()
        assert capsys.readouterr().out == '<div class="box"> x </div>\n'


class TestMacrosRegressions:

    def test_void_tag(self):
        out = lhtml.run('a rule::\nb\n', macros={'rule': {'tag': 'hr', 'class': 'rule'}})
        assert out == 'a <hr class="rule">\nb\n'

    def test_macros_key_null(self):
        assert lhtml.load_macros({'macros': None}) == {}


class TestMacrosTag:
    """A macro renders the HTML element of its tag, never an LHTML tag (3.0)."""

    def test_img_tag_with_url(self):
        out = lhtml.run('photo::a.png[width:10px;]\n',
                        macros={'photo': {'tag': 'img', 'class': 'photo', 'url': 'src'}})
        assert out == '<img class="photo" style="width:10px;" src="a.png">\n'

    def test_macro_does_not_render_through_another_macro(self):
        out = lhtml.run('a:: x ::\n', macros={'b': {'class': 'b'}, 'a': {'tag': 'b', 'class': 'a'}})
        assert out == '<b class="a"> x </b>\n'

    @pytest.mark.parametrize('field', [{'style': 'color:red'}, {'variant': True}])
    def test_removed_fields(self, field):
        with pytest.raises(lhtml.LHTMLMacroError):
            lhtml.run('x\n', macros={'m': {'class': 'm', **field}})


class TestMacrosRound2:

    def test_variant_closed_inline(self):
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            assert _run_macros('gap::l::\n') == '<div class="gap gap-l"></div>\n'
            out = lhtml.run('box::warn:: x\n', macros={'box': {'class': 'box', 'variant': ['warn']}})
        assert out == '<div class="box box-warn"></div> x\n'

    def test_macros_key(self, tmp_path):
        (tmp_path / 'm.yaml').write_text('macros:\n  note: {class: note}\n', encoding='utf-8')
        assert lhtml.load_macros(str(tmp_path / 'm.yaml')) == {'note': {'class': 'note'}}

    def test_null_removes_macro(self):
        with pytest.warns(lhtml.LHTMLWarning, match='closes nothing: no element is open'):
            out = lhtml.run('box:: x ::\n', macros=lhtml.load_macros([MACROS, {'box': None}]))
        assert out.strip() == 'box:: x ::'

    def test_default_must_be_a_variant(self):
        with pytest.raises(lhtml.LHTMLMacroError):
            lhtml.run('x\n', macros={'gap': {'class': 'gap', 'variant': ['s'], 'default': 'm'}})


class TestMacrosRound3:

    def test_url_on_container(self):
        out = lhtml.run('dx::hello\nx\n::\n', macros={'dx': {'class': 'dx', 'url': 'data-x'}})
        assert out == '<div class="dx" data-x="hello">\nx\n</div>\n'

    def test_url_on_span_closed_inline(self):
        out = lhtml.run('t::Tip:: x\n', macros={'t': {'tag': 'span', 'url': 'title'}})
        assert out == '<span title="Tip"></span> x\n'

    def test_url_other_than_the_handler_attribute(self):
        out = lhtml.run('lazy::a.png\n', macros={'lazy': {'tag': 'img', 'class': 'lazy',
                                                                 'url': 'data-src'}})
        assert out == '<img class="lazy" data-src="a.png">\n'

    def test_design_keys_are_not_special(self):
        with pytest.raises(lhtml.LHTMLMacroError, match="'tokens'"):
            lhtml.run('x\n', macros={'tokens': {'font': {'small': '85%'}}})

    def test_macros_is_reserved(self):
        with pytest.raises(lhtml.LHTMLMacroError, match='reserved'):
            lhtml.run('x\n', macros={'macros': {'macros': {'class': 'm'}}})

    def test_css_is_not_a_field(self):
        with pytest.raises(lhtml.LHTMLMacroError, match='css'):
            lhtml.run('x\n', macros={'box': {'class': 'box', 'css': '.box {}'}})

    def test_describe_macro(self):
        assert lhtml.describe_macro('gap', MACROS['gap']) == {
            'html': '<div class="gap">', 'url': None, 'empty': True, 'variants': ['s', 'm', 'l'],
            'default': 'm', 'doc': None}
        info = lhtml.describe_macro('ext', {'tag': 'a', 'class': 'ext', 'url': 'href'})
        assert (info['html'], info['url'], info['empty']) == ('<a class="ext">', 'href', False)

    @pytest.mark.parametrize('tag', ['nl', 'code', 'include'])
    def test_pseudo_tags_are_rejected(self, tag):
        with pytest.raises(lhtml.LHTMLMacroError, match='not an element'):
            lhtml.run('x\n', macros={'m': {'tag': tag}})

    def test_chained_classes(self):
        assert lhtml.run('div::(.a.b#c) x ::\n') == '<div class="a b" id="c"> x </div>\n'


# ---------------------------------------------------------------------------
# Media resolver (3.0): the caller says which sources a video offers
# ---------------------------------------------------------------------------

class TestMedia:
    def test_sources_given_by_the_caller(self):
        def media(src):
            return [(f'cache/{src}.webm', 'video/webm'), (f'cache/{src}.mp4', 'video/mp4')]
        r = lhtml.run('video::v.mp4\n', media=media)
        assert '<source src="cache/v.mp4.webm" type="video/webm">' in r
        assert '<source src="cache/v.mp4.mp4" type="video/mp4">' in r
        assert 'src="v.mp4"' not in r

    def test_no_source_from_the_caller_writes_the_source(self):
        r = lhtml.run('videoplay::v.mp4\n', media=lambda src: [])
        assert '<source src="v.mp4" type="video/mp4">' in r and 'autoplay loop muted playsinline' in r

    def test_no_file_probed_without_resolver(self, tmp_path):
        variants = tmp_path / 'assets' / 'cache_video_codecs'
        variants.mkdir(parents=True)
        (variants / 'v-h264.mp4').write_bytes(b'')
        r = lhtml.run('video::assets/v.mp4\n')
        assert r.count('<source') == 1 and 'cache_video_codecs' not in r

    def test_resolver_must_be_callable(self):
        with pytest.raises(TypeError):
            lhtml.run('video::v.mp4\n', media='cache/')

    def test_no_front_matter(self):
        r = lhtml.run('---\nmedia: x\n---\nvideo::v.mp4\n')
        assert r.startswith('---\nmedia: x\n---\n') and '<source src="v.mp4"' in r


class TestPositions:
    """A warning or an error carries the line and column of the source where it is."""

    @staticmethod
    def places(text, **meta):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            lhtml.run(text, **meta)
        return [(w.message.line, w.message.column) for w in caught]

    def test_a_tag_after_lines_that_lhtml_adds_or_hides(self):
        # a heading and a list add lines to the text, code and math hide some
        text = '= T\n* a\n* b\ncode::[c]\nx\ny\ncode::[-]\n**b** `c::d` \\(x\ny\\) div::[a:b] text\n'
        assert self.places(text) == [(9, 5)]

    def test_each_warning_of_the_tag_pass(self):
        macros = {'gap': {'tag': 'div', 'class': 'gap', 'variant': ['s'], 'empty': True}}
        assert self.places('x\n  oops ::\ngap::zz\n', macros=macros) == [(2, 8), (3, 1)]
        assert self.places('a div::(.x[b] c\n') == [(1, 3)]            # unclosed bracket
        assert self.places('abc\n::(x') == [(2, 1)]                    # not the word of the line before

    def test_an_unknown_language_where_its_block_starts(self):
        assert self.places('a\n\ncode::[nosuchlang]\nx\ncode::[-]\n') == [(3, 1)]

    @pytest.mark.parametrize('text, place', [
        ('a\n\n  ::# c', (3, 3)),
        ('x\n`a\nb` include::f.txt', (3, 4)),
        ('code::[]\nx\ninclude::f.txt\ncode::[-]\n', (3, 1)),
        ('p\n::[-]', (2, 1)),
        ('z\n<b>\n</b> verbatim::[]', (3, 6)),
    ])
    def test_an_error_where_it_is(self, text, place):
        with pytest.raises(lhtml.LHTMLParseError) as error:
            lhtml.run(text)
        assert (error.value.line, error.value.column) == place

    def test_cli_prints_file_line_column(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / 'p.l.html'
        f.write_text('x\n  ::# no\n')
        code, _, err = TestCli._run_cli(self, monkeypatch, capsys, str(f))
        assert code == 1 and err.startswith(f'{f}:2:3: error: ::# comments were removed')


# ---------------------------------------------------------------------------
# The output of the command (lhtml/diagnostics.py)
# ---------------------------------------------------------------------------

class TestCommandOutput:
    _run_cli = TestCli._run_cli

    def test_a_destination_under_a_file_is_refused_without_traceback(self, tmp_path, monkeypatch, capsys):
        a, b = tmp_path / 'a.l.html', tmp_path / 'b.l.html'
        a.write_text('A\n')
        b.write_text('B\n')
        (tmp_path / 'f').write_text('')
        code, _, err = self._run_cli(monkeypatch, capsys, str(a), str(b), '-o', str(tmp_path / 'f/sub') + '/')
        assert code == 1 and 'is a file' in err and 'nothing written' in err and 'Traceback' not in err
        assert (tmp_path / 'f').read_text() == ''

    def test_stdout_holds_the_html_only(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / 'a.l.html'
        f.write_text('x\n::\n')
        code, out, err = self._run_cli(monkeypatch, capsys, str(f))
        assert code == 0 and out == 'x\n::\n'
        assert err == f'{f}:2:1: warning: this :: closes nothing: no element is open (near \'::\')\n'

    def test_writing_files_ends_with_a_summary(self, tmp_path, monkeypatch, capsys):
        a, b = tmp_path / 'a.l.html', tmp_path / 'b.l.html'
        a.write_text('x\n::\n')
        b.write_text('B\n')
        out = str(tmp_path / 'out') + '/'
        code, _, err = self._run_cli(monkeypatch, capsys, str(a), str(b), '-o', out)
        assert code == 0 and err.splitlines()[-1] in ('2 converted · 1 warning', '2 converted, 1 warning')
        code, _, err = self._run_cli(monkeypatch, capsys, '-q', str(b), '-o', out)
        assert err == ''
        code, _, err = self._run_cli(monkeypatch, capsys, '-v', str(b), '-o', out)
        assert f'{b} ' in err and str(tmp_path / 'out' / 'b.html') in err

    def test_a_file_not_converted_is_counted(self, tmp_path, monkeypatch, capsys):
        bad, good = tmp_path / 'bad.l.html', tmp_path / 'good.l.html'
        bad.write_bytes(b'caf\xe9\n')
        good.write_text('ok\n')
        code, _, err = self._run_cli(monkeypatch, capsys, str(bad), str(good), '-o', str(tmp_path / 'o') + '/')
        assert code == 1 and err.splitlines()[-1] in ('1 converted · 1 failed', '1 converted, 1 failed')


    def test_two_outputs_that_are_one_file_are_refused(self, tmp_path, monkeypatch, capsys):
        a, b = tmp_path / 'a.l.html', tmp_path / 'b.l.html'
        a.write_text('A\n')
        b.write_text('B\n')
        (tmp_path / 'out').mkdir()
        (tmp_path / 'out/a.html').write_text('old\n')
        os.link(tmp_path / 'out/a.html', tmp_path / 'out/b.html')
        code, _, err = self._run_cli(monkeypatch, capsys, str(a), str(b), '-o', str(tmp_path / 'out') + '/')
        assert code == 1 and 'would both be written to' in err and 'nothing written' in err
        assert (tmp_path / 'out/a.html').read_text() == 'old\n'

    def test_an_error_shows_its_line(self, tmp_path, monkeypatch, capsys):
        from lhtml import cli
        f = tmp_path / 'a.l.html'
        f.write_text('x\ninclude::header.html\n')
        reported = []
        real = cli.Reporter.report
        monkeypatch.setattr(cli.Reporter, 'report', lambda self, d, source=None: reported.append((d, source))
                            or real(self, d, source))
        code, _, err = self._run_cli(monkeypatch, capsys, str(f))
        [(diagnostic, source)] = reported
        assert code == 1 and (diagnostic.line, diagnostic.column) == (2, 1) and source == 'x\ninclude::header.html\n'


    def test_a_macros_file_is_an_input(self, tmp_path, monkeypatch, capsys):
        (tmp_path / 'm.yaml').write_text('x: {tag: span}\n')
        (tmp_path / 'a.l.html').write_text('= A\n')
        code, _, err = self._run_cli(monkeypatch, capsys, '-m', str(tmp_path / 'm.yaml'), str(tmp_path / 'a.l.html'),
                                     '-o', str(tmp_path / 'm.yaml'))
        assert code == 1 and 'nothing written' in err and (tmp_path / 'm.yaml').read_text() == 'x: {tag: span}\n'

    def test_a_macros_file_problem_is_one_line_with_its_place(self, tmp_path, monkeypatch, capsys):
        (tmp_path / 'ok.yaml').write_text('x: {class: x}\n')
        (tmp_path / 'bad.yaml').write_text('a: [\n')
        (tmp_path / 'nu.yaml').write_bytes(b'\xff\xfe\n')
        (tmp_path / 'a.l.html').write_text('A\n')
        code, _, err = self._run_cli(monkeypatch, capsys, '-m', str(tmp_path / 'ok.yaml'), '-m',
                                     str(tmp_path / 'bad.yaml'), str(tmp_path / 'a.l.html'))
        assert code == 1 and err.startswith(f'{tmp_path / "bad.yaml"}:2:1: error: invalid YAML') and err.count('\n') == 1
        code, _, err = self._run_cli(monkeypatch, capsys, '-m', str(tmp_path / 'nu.yaml'), str(tmp_path / 'a.l.html'))
        assert code == 1 and err == f'{tmp_path / "nu.yaml"}: error: the macros file is not UTF-8\n'

    def test_an_empty_output_name_is_a_wrong_use(self, tmp_path, monkeypatch, capsys):
        (tmp_path / 'a.l.html').write_text('A\n')
        assert self._run_cli(monkeypatch, capsys, str(tmp_path / 'a.l.html'), '-o', '')[0] == 2

    def test_no_stdout_or_stderr_is_no_traceback(self, tmp_path, monkeypatch, capsys):
        (tmp_path / 'a.l.html').write_text('x ::\n')
        monkeypatch.setattr('sys.stdout', None)
        code, _, err = self._run_cli(monkeypatch, capsys, str(tmp_path / 'a.l.html'))
        assert code == 1 and 'cannot write the standard output' in err
        from lhtml.diagnostics import Diagnostic, Reporter
        Reporter(None).report(Diagnostic('p', 'warning', 'm'))      # a closed stderr: nothing written


class TestDiagnostics:
    @staticmethod
    def shown(source, line, column, **options):
        import io
        from lhtml.diagnostics import Diagnostic, Reporter
        stream = io.StringIO()
        reporter = Reporter(stream, rich=True, color=False, **options)
        reporter.report(Diagnostic('p.l.html', 'warning', 'm', line, column), source)
        return stream.getvalue()

    def test_an_excerpt_underlines_the_word_at_the_place(self):
        assert self.shown('a\n  div::(.note) x\n', 2, 3) == (
            'p.l.html:2:3: warning: m\n'
            '  2 | ' + '  div::(.note) x\n'
            '    | ' + '  ^^^^^^^^^^^^\n'
            '\n')

    def test_with_its_excerpt_a_message_quotes_nothing(self):
        import io
        from lhtml.diagnostics import Diagnostic, Reporter
        stream = io.StringIO()
        Reporter(stream, rich=True, color=False).report(
            Diagnostic('p', 'warning', "div:: is never closed (near 'div::(.n)')", 1, 1), 'div::(.n)\n')
        assert stream.getvalue().splitlines()[0] == 'p:1:1: warning: div:: is never closed'
        stream = io.StringIO()                  # a log: the whole message
        Reporter(stream, rich=False).report(Diagnostic('p', 'warning', "x (near 'y')", 1, 1), 'y\n')
        assert stream.getvalue() == "p:1:1: warning: x (near 'y')\n"

    def test_a_quote_on_another_line_stays(self):
        import io
        from lhtml.diagnostics import Diagnostic, Reporter
        stream = io.StringIO()
        Reporter(stream, rich=True, color=False).report(
            Diagnostic('p', 'warning', "this :: closes nothing (near 'span::(.a)')", 2, 4), 'span::(.a)\na ::\n')
        assert stream.getvalue().splitlines()[0].endswith("(near 'span::(.a)')")

    def test_a_stream_that_cannot_write_a_character_gets_its_escape_underlined(self):
        import io
        from lhtml.diagnostics import Diagnostic, Reporter

        class Ascii(io.StringIO):
            encoding = 'ascii'
        stream = Ascii()
        Reporter(stream, rich=True, color=False).report(Diagnostic('p', 'warning', 'm', 1, 1), 'div::(.\xe9)\n')
        lines = stream.getvalue().splitlines()
        assert lines[1].endswith('div::(.\\xe9)') and lines[2].endswith('^' * len('div::(.\\xe9)'))

    def test_the_underline_follows_tabs_and_wide_characters(self):
        lines = self.shown('\t日本 div:: x\n', 1, 5).splitlines()
        assert lines[1].endswith('\t日本 div:: x')
        assert lines[2].endswith('\t     ^^^^^')

    def test_a_long_line_is_cut_around_the_place(self):
        lines = self.shown('a' * 300 + ' div:: ' + 'b' * 300 + '\n', 1, 302).splitlines()
        assert lines[1].count('…') == 2 and 'div::' in lines[1] and len(lines[1]) < 120
        assert lines[2].index('^') == lines[1].index('div::')

    def test_colors_follow_the_terminal_and_no_color(self, monkeypatch):
        import io
        from lhtml.diagnostics import Reporter

        class Terminal(io.StringIO):
            encoding = 'utf-8'

            def isatty(self):
                return True
        monkeypatch.delenv('NO_COLOR', raising=False)
        monkeypatch.delenv('FORCE_COLOR', raising=False)
        monkeypatch.setenv('TERM', 'xterm')
        assert Reporter(Terminal()).color and not Reporter(io.StringIO()).color
        monkeypatch.setenv('NO_COLOR', '1')
        assert not Reporter(Terminal()).color
        monkeypatch.delenv('NO_COLOR')
        monkeypatch.setenv('FORCE_COLOR', '1')
        assert Reporter(io.StringIO()).color
        assert not Reporter(io.StringIO()).rich      # a log: one line each
